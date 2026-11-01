"""Application wiring: build indexes once, then process each request."""
from __future__ import annotations

import json
import os
import threading
import urllib.request
from pathlib import Path

from .data import DeletionRequest, OutputRow, load_csv
from .cache import CachedProvider, DiskResponseCache
from .identity import IdentityIndex
from .observations import CachedImageEvidenceReader, map_categories_to_rules, parse_manifest_once
from .planner import CasePlan, PlannedProcess, PlannedTarget, plan_steps, validate_plan
from .policy import PolicyAction
from .provider import ModelResponse, TokenLogger, TokenUsage
from .request_classifier import RequestClassifier
from .state import CaseStateAnalyzer
from .steps import serialize_steps
from .vision import FallbackImageReader


class OpenAICompatibleProvider:
    """Small OpenAI-compatible JSON chat provider; key is read only from env."""
    name = "openai-compatible"
    def __init__(self) -> None:
        self.key = os.environ["GHOST_DATA_API_KEY"]
        self.base = os.environ.get("GHOST_DATA_API_BASE", "https://api.openai.com/v1").rstrip("/")
    def complete(self, request):
        body = json.dumps({"model": request.model, "messages": [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_content}],
            "temperature": 0, "response_format": {"type": "json_object"}}).encode()
        req = urllib.request.Request(self.base + "/chat/completions", data=body,
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as response:
            payload = json.loads(response.read())
        usage = payload.get("usage", {})
        return ModelResponse(content=payload["choices"][0]["message"]["content"],
            usage=TokenUsage(input_tokens=usage.get("prompt_tokens", 0), output_tokens=usage.get("completion_tokens", 0)),
            provider=self.name, model=request.model)


class CaseProcessor:
    def __init__(self, dataset: Path, *, classifier: RequestClassifier | None = None) -> None:
        self.dataset = dataset.resolve()
        self.unresolved_log_path = self.dataset.parent / ".local" / "unresolved_cases.jsonl"
        self._unresolved_log_lock = threading.Lock()
        if classifier is None and os.environ.get("GHOST_DATA_API_KEY"):
            model = os.environ.get("GHOST_DATA_CLASSIFIER_MODEL", "gpt-4o-mini")
            provider = CachedProvider(OpenAICompatibleProvider(),
                DiskResponseCache(Path(os.environ.get("GHOST_DATA_LLM_CACHE", str(dataset.parent / ".local" / "llm_cache")))),
                TokenLogger(Path(os.environ.get("GHOST_DATA_TOKEN_LOG", str(dataset.parent / ".local" / "token_usage.jsonl")))))
            classifier = RequestClassifier(provider, model=model)
        self.classifier = classifier or RequestClassifier()
        self.identities = IdentityIndex(
            load_csv(self.dataset / "user_identities.csv"),
            load_csv(self.dataset / "user_audit_log.csv"),
        )
        self.activities = load_csv(self.dataset / "system_activity.csv")
        self.rules = load_csv(self.dataset / "deletion_rules.csv")
        manifest = load_csv(self.dataset / "evidence_files.csv")
        cache = Path(os.environ.get("GHOST_DATA_OCR_CACHE", str(self.dataset.parent / ".local" / "ocr_cache")))
        reader = CachedImageEvidenceReader(FallbackImageReader(), cache)
        error_log = Path(os.environ.get("GHOST_DATA_EVIDENCE_ERRORS", str(dataset.parent / ".local" / "evidence_errors.jsonl")))
        parsed = parse_manifest_once(manifest, self.dataset, image_reader=reader, error_log_path=error_log)
        self.observations = map_categories_to_rules(
            parsed, self.rules,
            unmapped_log=Path(os.environ.get("GHOST_DATA_UNMAPPED_TYPES", str(dataset.parent / ".local" / "unmapped_resource_types.jsonl"))),
        )
        dump_path = Path(os.environ.get("GHOST_DATA_OCR_DUMP", str(dataset.parent / ".local" / "ocr_dump.txt")))
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        blocks = []
        for item in manifest:
            if Path(item.file_path).suffix.casefold() != ".png":
                continue
            image_path = (self.dataset / item.file_path).resolve()
            text = reader.text_by_path.get(image_path)
            if text is None:
                text = f"[UNREADABLE: {self.observations.unreadable_files.get(item.file_id, 'OCR text unavailable')} ]"
            blocks.append(f"===== {item.file_id} =====\n{text}")
        dump_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8", newline="\n")
        self.analyzer = CaseStateAnalyzer(self.observations, self.activities, self.rules)

    def _log_unresolved(self, request: DeletionRequest, reason: str) -> None:
        record = json.dumps({
            "case_id": request.case_id,
            "audit_at": request.audit_at.isoformat(),
            "reason": reason,
        }, sort_keys=True)
        self.unresolved_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._unresolved_log_lock:
            with self.unresolved_log_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(record + "\n")

    def process_case(self, request: DeletionRequest) -> OutputRow:
        classification = self.classifier.classify(request.request_text)
        if not classification.requests_deletion:
            return OutputRow(case_id=request.case_id, deletion_status="NOT_APPLICABLE", steps_json="[]")
        subject = self.identities.resolve(request)
        if subject.user_id is None:
            raise ValueError("request identity could not be resolved unambiguously")
        findings = self.analyzer.analyze(request, subject)
        # One ordered collection of linked resource decisions drives every
        # finding, proposed treatment, and verification emitted by the planner.
        targets: list[PlannedTarget] = []
        timing_linked_resources = {
            edge.target_resource
            for edge in findings.link_edges
            if edge.edge_type == "reported_at_proximity"
        }
        explicitly_referenced_resources = {
            edge.target_resource
            for edge in findings.link_edges
            if edge.edge_type == "explicit_resource_reference"
        }
        flow_map = {item.resource_id: item for item in (
            PlannedProcess(system_id=next((r.system_id for r in findings.resources if r.resource_id == rid), "integration_service"),
                resource_id=rid, kind="DATA_FLOW", evidence_id=next((e.value for r in findings.resources if r.resource_id == rid for e in r.evidence if e.kind in {"file_id", "activity_id"}), ""), requires_action=True)
            for rid in findings.active_data_flows)}
        restore_map = {item.resource_id: item for item in (
            PlannedProcess(system_id=next((r.system_id for r in findings.resources if r.resource_id == rid), "backup_service"),
                resource_id=rid, kind="RESTORE", evidence_id=next((e.value for r in findings.resources if r.resource_id == rid for e in r.evidence if e.kind in {"file_id", "activity_id"}), ""), requires_action=True)
            for rid in findings.restore_risks)}
        for resource in findings.resources:
            observations = [o for o in self.observations.by_resource_id.get(resource.resource_id, [])
                           if o.file_id in {e.value for e in resource.evidence if e.kind == "file_id"}]
            if resource.state == "UNKNOWN":
                continue
            if not observations:
                coverage_evidence = next(
                    (
                        evidence.value for evidence in resource.evidence
                        if evidence.kind == "file_id" and evidence.role == "covered_store_absence"
                    ),
                    None,
                )
                if (
                    resource.state == "ABSENT"
                    and coverage_evidence
                    and resource.resource_id in (
                        timing_linked_resources | explicitly_referenced_resources
                    )
                ):
                    targets.append(PlannedTarget(
                        system_id=resource.system_id,
                        resource_id=resource.resource_id,
                        treatment="DELETE_RECORD",
                        evidence_id=coverage_evidence,
                    ))
                continue
            # Include only observations at the selected governing capture time.
            governing = [o for o in observations if o.captured_at == resource.captured_at]
            evidence_id = governing[0].file_id if governing else observations[0].file_id
            if resource.resource_id.casefold().startswith("data_flow_"):
                known = flow_map.get(resource.resource_id)
                if known is None and any(obs.enabled_active is False for obs in governing):
                    flow_map[resource.resource_id] = PlannedProcess(
                        system_id=resource.system_id, resource_id=resource.resource_id, kind="DATA_FLOW",
                        evidence_id=evidence_id, requires_action=False,
                    )
                continue
            if resource.data_category == "BACKUP_ARCHIVE" and any(
                obs.restore_blocked is True or obs.deletion_blocked is True or obs.restore_allowed is False for obs in governing
            ):
                restore_map.setdefault(resource.resource_id, PlannedProcess(
                    system_id=resource.system_id, resource_id=resource.resource_id, kind="RESTORE",
                    evidence_id=evidence_id, requires_action=False,
                ))
                continue
            violation = None
            treatment = None
            retain = False
            anonymized = False
            for observation in governing:
                if observation.data_category not in self.analyzer.policy.rules:
                    continue
                decision = self.analyzer.policy.evaluate(observation, subject=subject, at=request.audit_at)
                retain = retain or decision.retain_record
                anonymized = anonymized or observation.anonymized is True
                direct_identifiers = {"name", "email", "phone", "email_hash"}.intersection(observation.identifiers_present)
                if decision.action == PolicyAction.DELETE:
                    treatment = "DELETE_RECORD"
                    if resource.state == "PRESENT": violation = PolicyAction.DELETE
                elif decision.action == PolicyAction.REDACT:
                    treatment = "REDACT_RECORD"
                    if resource.state == "PRESENT" and direct_identifiers:
                        violation = PolicyAction.REDACT
                    retain = True
                elif decision.action == PolicyAction.ANONYMIZE:
                    treatment = "ANONYMIZE_RECORD"
                    if resource.state == "PRESENT" and observation.anonymized is not True:
                        violation = PolicyAction.ANONYMIZE
                elif decision.action == PolicyAction.BLOCK_RESTORE:
                    # Restore is modeled as a process state and planned in the
                    # same case plan's process collection, never as a record finding.
                    treatment = None
                elif decision.action == PolicyAction.RETAIN:
                    treatment = "VERIFY_RECORD_PRESENT"
                    retain = True
            if violation is not None:
                treatment = {
                    PolicyAction.DELETE: "DELETE_RECORD",
                    PolicyAction.REDACT: "REDACT_RECORD",
                    PolicyAction.ANONYMIZE: "ANONYMIZE_RECORD",
                }[violation]
            if violation == PolicyAction.DELETE:
                finding = "REPORT_REMAINING_RECORD"
            elif violation in {PolicyAction.REDACT, PolicyAction.ANONYMIZE}:
                finding = "REPORT_EXPOSED_PII"
            else:
                finding = None
            if treatment is None:
                continue
            targets.append(PlannedTarget(
                system_id=resource.system_id, resource_id=resource.resource_id,
                treatment=treatment, finding=finding, evidence_id=evidence_id,
                retain_record=retain, anonymized=anonymized,
            ))
        flows = tuple(flow_map.values())
        restores = tuple(restore_map.values())
        incomplete = any(item.finding for item in targets) or any(item.requires_action for item in flows + restores)
        plan = CasePlan(deletion_status="INCOMPLETE" if incomplete else "COMPLETE", targets=tuple(targets), active_flows=flows, restore_risks=restores)
        steps = plan_steps(plan)
        if not incomplete and not any(
            step.phase == "VERIFICATION" and step.evidence_id for step in steps
        ):
            reason = (
                "no_linked_resources"
                if not findings.resources and not findings.active_data_flows and not findings.restore_risks
                else "no_evidence_backed_verification"
            )
            self._log_unresolved(request, reason)
            return OutputRow(case_id=request.case_id, deletion_status="INCOMPLETE", steps_json="[]")
        validate_plan(plan, steps)
        return OutputRow(case_id=request.case_id, deletion_status=plan.deletion_status, steps_json=serialize_steps(steps))


_DEFAULT_PROCESSOR: CaseProcessor | None = None

def process_case(request: DeletionRequest) -> OutputRow:
    """Default CLI entry point; its heavy participant-data index is built once."""
    global _DEFAULT_PROCESSOR
    if _DEFAULT_PROCESSOR is None:
        dataset = Path(os.environ.get("GHOST_DATASET", Path(__file__).resolve().parents[3] / "dataset"))
        _DEFAULT_PROCESSOR = CaseProcessor(dataset)
    return _DEFAULT_PROCESSOR.process_case(request)
