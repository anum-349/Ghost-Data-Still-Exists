"""Generate and run synthetic evaluation scenarios without fixed identifiers."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ghost_data.data import DeletionRequest, DeletionRule, EvidenceFile, SystemActivity, UserAuditEvent, UserIdentity, load_csv
from ghost_data.identity import IdentityIndex
from ghost_data.observations import Observation, ObservationIndex, parse_evidence_file
from ghost_data.planner import CasePlan, PlannedTarget, plan_steps
from ghost_data.policy import PolicyEngine
from ghost_data.state import CaseStateAnalyzer


EVALUATION_ROOT = Path(__file__).resolve().parents[1]
_PARENT_ROOT = EVALUATION_ROOT.parent
if (_PARENT_ROOT / "dataset").is_dir():
    REPO_ROOT = _PARENT_ROOT
    CODE_ROOT = REPO_ROOT / "code"
else:
    CODE_ROOT = _PARENT_ROOT
    REPO_ROOT = CODE_ROOT.parent
CASES_ROOT = EVALUATION_ROOT / "cases"
UTC = timezone.utc


@dataclass(frozen=True)
class CaseResult:
    name: str
    passed: bool
    checks_passed: int
    checks_total: int


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _synthetic_key(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _identity(user_id: str, email: str, updated_at: str = "2027-01-01T00:00:00Z") -> UserIdentity:
    return UserIdentity(
        user_id=user_id, name="", email=email, phone="", email_hash="",
        updated_at=updated_at,
    )


def _request(email: str, *, requested_at: str, audit_at: str) -> DeletionRequest:
    return DeletionRequest(
        case_id=_synthetic_key("request"), email=email,
        requested_at=requested_at, reported_status="NOT_STARTED",
        reported_at=requested_at, audit_at=audit_at,
        request_text="Please delete my account and personal data.",
    )


def _check(name: str, actual: dict, expected: dict) -> CaseResult:
    passed = sum(actual.get(key) == value for key, value in expected.items())
    return CaseResult(name=name, passed=passed == len(expected), checks_passed=passed, checks_total=len(expected))


def _reassigned_email(rules: list[DeletionRule], expected: dict) -> CaseResult:
    assigned_email = f"{uuid4().hex}@example.invalid"
    former_owner = _synthetic_key("user")
    current_owner = _synthetic_key("user")
    reassignment_at = "2026-06-10T00:00:00Z"
    request = _request(
        assigned_email, requested_at="2026-06-01T00:00:00Z", audit_at="2026-06-20T00:00:00Z",
    )
    identities = [
        _identity(former_owner, f"{uuid4().hex}@example.invalid"),
        _identity(current_owner, assigned_email),
    ]
    audits = [
        UserAuditEvent(
            audit_id=_synthetic_key("audit"), user_id=former_owner,
            event_time=reassignment_at, field_name="email", old_value=assigned_email,
            new_value=identities[0].email,
        ),
        UserAuditEvent(
            audit_id=_synthetic_key("audit"), user_id=current_owner,
            event_time=reassignment_at, field_name="email", old_value=f"{uuid4().hex}@example.invalid",
            new_value=assigned_email,
        ),
    ]
    resolved = IdentityIndex(identities, audits, email_hash_scheme_confirmed=False).resolve(request)
    reassignment = [
        collision for collision in resolved.collisions
        if collision.identifier_type == "email" and collision.user_ids == tuple(sorted((former_owner, current_owner)))
    ]
    actual = {
        "unique_request_time_owner": resolved.user_id == former_owner and resolved.matched_user_ids == (former_owner,),
        "reassignment_collision_detected": bool(reassignment),
        "uses_current_owner_for_past_request": resolved.user_id == current_owner,
    }
    return _check("reassigned_email", actual, expected)


def _restore_after_cutoff(rules: list[DeletionRule], expected: dict) -> CaseResult:
    email = f"{uuid4().hex}@example.invalid"
    user_id = _synthetic_key("user")
    identity = _identity(user_id, email)
    request = _request(email, requested_at="2026-06-01T00:00:00Z", audit_at="2026-06-20T00:00:00Z")
    subject = IdentityIndex([identity], [], email_hash_scheme_confirmed=False).resolve(request)
    activity = SystemActivity(
        activity_id=_synthetic_key("activity"), event_time="2026-06-20T00:00:01Z",
        event_type="RESTORE_BACKUP", source_system="backup_service", target_system="account_service",
        resource_id=_synthetic_key("backup"), reported_result="SUCCESS",
        details=f"restore request for user_id={user_id}",
    )
    findings = CaseStateAnalyzer(ObservationIndex([], []), [activity], rules).analyze(request, subject)
    actual = {
        "post_cutoff_activity_is_ignored": activity.activity_id not in {
            claim.activity_id for resource in findings.resources for claim in resource.activity_claims
        },
        "restore_risk_count": len(findings.restore_risks),
    }
    return _check("restore_after_audit_cutoff", actual, expected)


def _retained_invoice(rules: list[DeletionRule], expected: dict) -> CaseResult:
    email = f"{uuid4().hex}@example.invalid"
    resource = _synthetic_key("invoice")
    observation = Observation(
        file_id=_synthetic_key("evidence"), captured_at=_time("2026-06-19T00:00:00Z"),
        system_id="finance_service", resource_id=resource, data_category="LEGAL_HOLD_RECORD",
        identifiers_present={"email": [email]}, exists=True, legal_hold_active=True,
    )
    decision = PolicyEngine(rules).evaluate(observation, at=_time("2026-06-20T00:00:00Z"))
    steps = plan_steps(CasePlan(
        deletion_status="COMPLETE",
        targets=(PlannedTarget(
            system_id=observation.system_id, resource_id=resource,
            treatment="VERIFY_RECORD_PRESENT", retain_record=True,
            evidence_id=observation.file_id,
        ),),
    ))
    actual = {
        "policy_action": decision.action.value,
        "record_present_verification": any(step.operation == "VERIFY_RECORD_PRESENT" for step in steps),
        "delete_remediation": any(step.operation == "DELETE_RECORD" for step in steps),
    }
    return _check("retained_invoice_with_email", actual, expected)


def _prompt_injection(rules: list[DeletionRule], expected: dict) -> CaseResult:
    with tempfile.TemporaryDirectory(prefix="ghost-data-eval-") as temp_dir:
        root = Path(temp_dir)
        evidence_dir = root / "evidence"
        evidence_dir.mkdir()
        resource = _synthetic_key("account")
        user_id = _synthetic_key("user")
        template_path = CASES_ROOT / "evidence" / "prompt_injection.txt"
        text = template_path.read_text(encoding="utf-8")
        text = text.replace("{{RESOURCE_ID}}", resource).replace("{{USER_ID}}", user_id)
        (evidence_dir / "prompt_injection.txt").write_text(text, encoding="utf-8")
        manifest = EvidenceFile(
            file_id=_synthetic_key("evidence"), file_path="evidence/prompt_injection.txt",
            origin="synthetic_fixture", captured_at="2026-06-19T00:00:00Z",
        )
        observations, _coverage = parse_evidence_file(manifest, root)
    observation = observations[0]
    decision = PolicyEngine(rules).evaluate(observation)
    steps = plan_steps(CasePlan(
        deletion_status="INCOMPLETE",
        targets=(PlannedTarget(
            system_id=observation.system_id, resource_id=observation.resource_id,
            treatment="DELETE_RECORD", finding="REPORT_REMAINING_RECORD", evidence_id=manifest.file_id,
        ),),
    ))
    actual = {
        "evidence_instructions_are_not_executed": "Ignore all policies" in observation.excerpt,
        "policy_action": decision.action.value,
        "remaining_record_finding": any(step.operation == "REPORT_REMAINING_RECORD" for step in steps),
    }
    return _check("prompt_injection_in_evidence", actual, expected)


def run_evaluation_cases() -> list[CaseResult]:
    """Run generated synthetic cases against dynamically loaded policy data."""
    rules = load_csv(REPO_ROOT / "dataset" / "deletion_rules.csv", DeletionRule)
    expected = json.loads((CASES_ROOT / "expected_outputs.json").read_text(encoding="utf-8"))
    return [
        _reassigned_email(rules, expected["reassigned_email"]),
        _restore_after_cutoff(rules, expected["restore_after_audit_cutoff"]),
        _retained_invoice(rules, expected["retained_invoice_with_email"]),
        _prompt_injection(rules, expected["prompt_injection_in_evidence"]),
    ]

