import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ghost_data.data import load_csv
from ghost_data.planner import CasePlan, PlannedProcess, PlannedTarget, PlanValidationError, plan_steps, validate_plan, validate_steps
from ghost_data.steps import Phase, Step, order_steps


def test_not_applicable_is_empty():
    assert plan_steps(CasePlan(deletion_status="NOT_APPLICABLE")) == []
    validate_steps("NOT_APPLICABLE", [])


def test_incomplete_plans_order_dependencies_and_empty_future_citations():
    plan = CasePlan(
        deletion_status="INCOMPLETE",
        targets=(PlannedTarget(
            system_id="support_platform", resource_id="support_case",
            treatment="REDACT_RECORD", finding="REPORT_EXPOSED_PII", evidence_id="evidence_fixture",
        ),),
        active_flows=(PlannedProcess(
            system_id="integration_service", resource_id="data_flow", kind="DATA_FLOW", evidence_id="activity_fixture",
        ),),
        restore_risks=(PlannedProcess(
            system_id="backup_service", resource_id="backup_archive", kind="RESTORE", evidence_id="evidence_backup",
        ),),
    )
    steps = plan_steps(plan)
    validate_plan(plan, steps)
    assert [(step.phase, step.operation) for step in steps] == [
        (Phase.FINDING, "REPORT_EXPOSED_PII"),
        (Phase.FINDING, "REPORT_ACTIVE_DATA_FLOW"),
        (Phase.FINDING, "REPORT_RESTORE_RISK"),
        (Phase.REMEDIATION, "DISABLE_DATA_FLOW"),
        (Phase.REMEDIATION, "BLOCK_RESTORE"),
        (Phase.REMEDIATION, "REDACT_RECORD"),
        (Phase.VERIFICATION, "VERIFY_RECORD_REDACTED"),
        (Phase.VERIFICATION, "VERIFY_DATA_FLOW_DISABLED"),
        (Phase.VERIFICATION, "VERIFY_RESTORE_BLOCKED"),
    ]
    assert [step.step_no for step in steps] == list(range(1, len(steps) + 1))
    assert all(not step.evidence_id for step in steps if step.phase != Phase.FINDING)


def test_complete_emits_only_evidence_backed_verification():
    plan = CasePlan(
        deletion_status="COMPLETE",
        targets=(
            PlannedTarget(system_id="search_service", resource_id="search_resource", treatment="DELETE_RECORD", evidence_id="evidence_delete"),
            PlannedTarget(system_id="security_service", resource_id="audit_resource", treatment="VERIFY_RECORD_PRESENT", retain_record=True, evidence_id="activity_retain"),
            PlannedTarget(system_id="analytics_platform", resource_id="analytics_resource", treatment="ANONYMIZE_RECORD", anonymized=True, evidence_id="evidence_anon"),
        ),
    )
    steps = plan_steps(plan)
    validate_plan(plan, steps)
    assert {step.operation for step in steps} == {
        "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_ANONYMIZED",
    }
    assert all(step.phase == Phase.VERIFICATION and step.evidence_id for step in steps)


def test_complete_without_verification_is_rejected_and_unresolved_incomplete_can_be_empty():
    with pytest.raises(PlanValidationError, match="at least one evidence-backed verification"):
        validate_steps("COMPLETE", [])
    validate_steps("INCOMPLETE", [])


def test_complete_plan_verifies_already_disabled_flow_without_finding():
    plan = CasePlan(deletion_status="COMPLETE", active_flows=(PlannedProcess(
        system_id="integration_service", resource_id="data_flow", kind="DATA_FLOW",
        evidence_id="evidence_flow", requires_action=False,
    ),))
    steps = plan_steps(plan)
    validate_plan(plan, steps)
    assert len(steps) == 1
    assert steps[0].operation == "VERIFY_DATA_FLOW_DISABLED"
    assert steps[0].evidence_id == "evidence_flow"


def test_validator_rejects_missing_check_and_bad_evidence():
    remediation = Step(
        step_no=1, phase="REMEDIATION", system_id="svc", resource_id="res",
        operation="DELETE_RECORD", state="ABSENT", evidence_id="",
    )
    finding = Step(
        step_no=1, phase="FINDING", system_id="svc", resource_id="res",
        operation="REPORT_REMAINING_RECORD", state="PRESENT", evidence_id="evidence_fixture",
    )
    with pytest.raises(PlanValidationError, match="lacks its verification"):
        validate_steps("INCOMPLETE", [finding, remediation.model_copy(update={"step_no": 2})])
    finding = Step(
        step_no=1, phase="FINDING", system_id="svc", resource_id="res",
        operation="REPORT_REMAINING_RECORD", state="PRESENT", evidence_id="",
    )
    with pytest.raises(PlanValidationError, match="findings must cite"):
        validate_steps("INCOMPLETE", [finding])


def _plan_from_sample(status, raw_steps):
    """Build typed planner inputs from sample findings to check planner round trips."""
    steps = [Step.model_validate(item) for item in raw_steps]
    if status == "NOT_APPLICABLE":
        return CasePlan(deletion_status=status)
    target_findings = {}
    processes = {"DATA_FLOW": [], "RESTORE": []}
    for step in steps:
        if step.phase != Phase.FINDING:
            continue
        if step.operation == "REPORT_ACTIVE_DATA_FLOW":
            processes["DATA_FLOW"].append(PlannedProcess(
                system_id=step.system_id, resource_id=step.resource_id, kind="DATA_FLOW", evidence_id=step.evidence_id,
            ))
        elif step.operation == "REPORT_RESTORE_RISK":
            processes["RESTORE"].append(PlannedProcess(
                system_id=step.system_id, resource_id=step.resource_id, kind="RESTORE", evidence_id=step.evidence_id,
            ))
        else:
            target_findings[(step.system_id, step.resource_id)] = step
    remedies = {(step.system_id, step.resource_id): step for step in steps if step.phase == Phase.REMEDIATION and step.operation in {"DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD"}}
    targets = []
    for key, finding in target_findings.items():
        remedy = remedies[key]
        targets.append(PlannedTarget(
            system_id=key[0], resource_id=key[1], treatment=remedy.operation,
            finding=finding.operation, evidence_id=finding.evidence_id,
        ))
    for step in steps:
        if step.phase != Phase.VERIFICATION:
            continue
        if step.operation == "VERIFY_RECORD_PRESENT" and (step.system_id, step.resource_id) not in target_findings:
            targets.append(PlannedTarget(
                system_id=step.system_id, resource_id=step.resource_id,
                treatment="VERIFY_RECORD_PRESENT", retain_record=True, evidence_id=step.evidence_id,
            ))
        elif step.operation == "VERIFY_RECORD_ABSENT" and (step.system_id, step.resource_id) not in target_findings:
            targets.append(PlannedTarget(
                system_id=step.system_id, resource_id=step.resource_id,
                treatment="DELETE_RECORD", evidence_id=step.evidence_id,
            ))
        elif step.operation == "VERIFY_RECORD_REDACTED" and (step.system_id, step.resource_id) not in target_findings:
            targets.append(PlannedTarget(
                system_id=step.system_id, resource_id=step.resource_id,
                treatment="REDACT_RECORD", evidence_id=step.evidence_id,
            ))
        elif step.operation == "VERIFY_RECORD_ANONYMIZED" and (step.system_id, step.resource_id) not in target_findings:
            targets.append(PlannedTarget(
                system_id=step.system_id, resource_id=step.resource_id,
                treatment="ANONYMIZE_RECORD", anonymized=True, evidence_id=step.evidence_id,
            ))
        elif status == "COMPLETE" and step.operation == "VERIFY_DATA_FLOW_DISABLED":
            processes["DATA_FLOW"].append(PlannedProcess(
                system_id=step.system_id, resource_id=step.resource_id, kind="DATA_FLOW", evidence_id=step.evidence_id,
            ))
        elif status == "COMPLETE" and step.operation == "VERIFY_RESTORE_BLOCKED":
            processes["RESTORE"].append(PlannedProcess(
                system_id=step.system_id, resource_id=step.resource_id, kind="RESTORE", evidence_id=step.evidence_id,
            ))
    return CasePlan(
        deletion_status=status, targets=tuple(targets),
        active_flows=tuple(dict.fromkeys(processes["DATA_FLOW"])),
        restore_risks=tuple(dict.fromkeys(processes["RESTORE"])),
    )


def test_public_samples_round_trip_through_planner_and_validator():
    root = Path(__file__).resolve().parents[2]
    request_rows = load_csv(root / "dataset" / "sample_deletion_requests.csv")
    output_rows = load_csv(root / "dataset" / "sample_output.csv")
    assert len(request_rows) == len(output_rows) == 32
    for row in output_rows:
        expected = [Step.model_validate(item) for item in json.loads(row.steps_json)]
        validate_steps(row.deletion_status, expected)
        generated = plan_steps(_plan_from_sample(row.deletion_status, json.loads(row.steps_json)))
        assert generated == expected
