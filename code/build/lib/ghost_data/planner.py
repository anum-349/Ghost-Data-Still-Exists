"""Deterministic step planning and contract validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .steps import Phase, Step, order_steps


class PlannedTarget(BaseModel):
    """Policy and evidence facts needed to plan one resource's output steps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    system_id: str
    resource_id: str
    treatment: Literal["DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD", "VERIFY_RECORD_PRESENT"]
    finding: Literal["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII"] | None = None
    evidence_id: str = ""
    retain_record: bool = False
    anonymized: bool = False


class PlannedProcess(BaseModel):
    """A sync/export process or restore path and its cited evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    system_id: str
    resource_id: str
    kind: Literal["DATA_FLOW", "RESTORE"]
    evidence_id: str = ""


class CasePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    deletion_status: Literal["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]
    targets: tuple[PlannedTarget, ...] = ()
    active_flows: tuple[PlannedProcess, ...] = ()
    restore_risks: tuple[PlannedProcess, ...] = ()


class PlanValidationError(ValueError):
    """Raised when generated steps violate ordering or evidence contracts."""


def plan_steps(plan: CasePlan) -> list[Step]:
    """Build sorted steps; remediation and future checks never cite evidence."""
    if plan.deletion_status == "NOT_APPLICABLE":
        return []

    steps: list[Step] = []

    def add(phase: Phase, system: str, resource: str, operation: str, state: str, evidence: str) -> None:
        steps.append(Step(
            step_no=1, phase=phase, system_id=system, resource_id=resource,
            operation=operation, state=state, evidence_id=evidence,
        ))

    complete = plan.deletion_status == "COMPLETE"
    if not complete:
        for item in plan.targets:
            if item.finding:
                add(Phase.FINDING, item.system_id, item.resource_id, item.finding, "PRESENT", item.evidence_id)
        for item in plan.active_flows:
            add(Phase.FINDING, item.system_id, item.resource_id, "REPORT_ACTIVE_DATA_FLOW", "ACTIVE", item.evidence_id)
        for item in plan.restore_risks:
            add(Phase.FINDING, item.system_id, item.resource_id, "REPORT_RESTORE_RISK", "ACTIVE", item.evidence_id)

        for item in plan.active_flows:
            add(Phase.REMEDIATION, item.system_id, item.resource_id, "DISABLE_DATA_FLOW", "DISABLED", "")
        for item in plan.restore_risks:
            add(Phase.REMEDIATION, item.system_id, item.resource_id, "BLOCK_RESTORE", "BLOCKED", "")
        for item in plan.targets:
            if item.finding:
                operation = item.treatment
                state = {"DELETE_RECORD": "ABSENT", "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED"}.get(operation)
                if state is None:
                    raise PlanValidationError(f"{operation} cannot remediate a finding")
                add(Phase.REMEDIATION, item.system_id, item.resource_id, operation, state, "")

    # Complete cases cite their current governing proof. Incomplete cases
    # describe future checks and therefore leave evidence_id empty.
    for item in plan.targets:
        if item.finding:
            verification = {
                "DELETE_RECORD": ("VERIFY_RECORD_ABSENT", "ABSENT"),
                "REDACT_RECORD": ("VERIFY_RECORD_REDACTED", "REDACTED"),
                "ANONYMIZE_RECORD": ("VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
            }.get(item.treatment)
        elif item.retain_record or item.treatment == "VERIFY_RECORD_PRESENT":
            verification = ("VERIFY_RECORD_PRESENT", "PRESENT")
        elif item.treatment == "DELETE_RECORD":
            verification = ("VERIFY_RECORD_ABSENT", "ABSENT")
        elif item.treatment == "REDACT_RECORD":
            verification = ("VERIFY_RECORD_REDACTED", "REDACTED")
        elif item.treatment == "ANONYMIZE_RECORD" or item.anonymized:
            verification = ("VERIFY_RECORD_ANONYMIZED", "ANONYMIZED")
        else:
            verification = None
        if verification:
            evidence = item.evidence_id if complete else ""
            add(Phase.VERIFICATION, item.system_id, item.resource_id, *verification, evidence)

    for item in plan.active_flows:
        add(Phase.VERIFICATION, item.system_id, item.resource_id, "VERIFY_DATA_FLOW_DISABLED", "DISABLED", "" if not complete else item.evidence_id)
    for item in plan.restore_risks:
        add(Phase.VERIFICATION, item.system_id, item.resource_id, "VERIFY_RESTORE_BLOCKED", "BLOCKED", "" if not complete else item.evidence_id)

    return order_steps(steps)


def validate_steps(status: str, steps: list[Step]) -> None:
    """Validate sequence numbering, phase/operation ordering and citations."""
    if status not in {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}:
        raise PlanValidationError(f"invalid deletion_status {status!r}")
    if status == "NOT_APPLICABLE":
        if steps:
            raise PlanValidationError("NOT_APPLICABLE must have no steps")
        return
    if [step.step_no for step in steps] != list(range(1, len(steps) + 1)):
        raise PlanValidationError("step_no values must be consecutive from 1")
    if order_steps(steps) != steps:
        raise PlanValidationError("steps do not follow the required sort key")
    if status == "COMPLETE":
        if not steps:
            raise PlanValidationError("COMPLETE must include evidence-backed verification")
        if any(step.phase != Phase.VERIFICATION for step in steps):
            raise PlanValidationError("COMPLETE may contain verification steps only")
        if any(not step.evidence_id for step in steps):
            raise PlanValidationError("COMPLETE verification steps must cite governing evidence")
        return
    if any(step.phase == Phase.FINDING and not step.evidence_id for step in steps):
        raise PlanValidationError("INCOMPLETE findings must cite evidence")
    if any(step.phase != Phase.FINDING and step.evidence_id for step in steps):
        raise PlanValidationError("INCOMPLETE remediation and verification evidence_id must be empty")
    if not any(step.phase == Phase.FINDING for step in steps):
        raise PlanValidationError("INCOMPLETE must include at least one finding")
    remediations = {(s.system_id, s.resource_id, s.operation) for s in steps if s.phase == Phase.REMEDIATION}
    finding_to_remedy = {
        "REPORT_REMAINING_RECORD": {"DELETE_RECORD"},
        "REPORT_EXPOSED_PII": {"REDACT_RECORD", "ANONYMIZE_RECORD"},
        "REPORT_ACTIVE_DATA_FLOW": {"DISABLE_DATA_FLOW"},
        "REPORT_RESTORE_RISK": {"BLOCK_RESTORE"},
    }
    for finding in (step for step in steps if step.phase == Phase.FINDING):
        valid = finding_to_remedy[finding.operation]
        if not any((finding.system_id, finding.resource_id, operation) in remediations for operation in valid):
            raise PlanValidationError(f"finding {finding.operation} lacks an applicable remediation")
    verification_for = {
        "DISABLE_DATA_FLOW": "VERIFY_DATA_FLOW_DISABLED",
        "BLOCK_RESTORE": "VERIFY_RESTORE_BLOCKED",
        "DELETE_RECORD": "VERIFY_RECORD_ABSENT",
        "REDACT_RECORD": "VERIFY_RECORD_REDACTED",
        "ANONYMIZE_RECORD": "VERIFY_RECORD_ANONYMIZED",
    }
    checks = {(s.system_id, s.resource_id, s.operation) for s in steps if s.phase == Phase.VERIFICATION}
    for system, resource, operation in remediations:
        check = verification_for.get(operation)
        if check and (system, resource, check) not in checks:
            raise PlanValidationError(f"remediation {operation} lacks its verification")


def validate_plan(plan: CasePlan, steps: list[Step]) -> None:
    """Validate the output contract and that every plan item was emitted."""
    validate_steps(plan.deletion_status, steps)
    expected = plan_steps(plan)
    if steps != expected:
        raise PlanValidationError("steps do not cover the supplied findings, remediations, and verification targets")

