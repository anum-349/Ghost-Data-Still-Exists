import json

import pytest
from pydantic import ValidationError

from ghost_data.data import load_csv
from ghost_data.steps import Phase, Step, order_steps, serialize_steps


def make_step(phase, operation, state, system="svc", resource="res", number=1):
    return Step(
        step_no=number, phase=phase, system_id=system, resource_id=resource,
        operation=operation, state=state, evidence_id="evidence",
    )


def test_valid_phase_operation_state_combinations():
    for phase, operation, state in [
        ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
        ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
        ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
        ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
        ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
        ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
        ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
        ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
        ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
        ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
        ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
        ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
        ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
        ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
        ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
    ]:
        make_step(phase, operation, state)


@pytest.mark.parametrize("phase,operation,state", [
    ("FINDING", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "DELETE_RECORD", "PRESENT"),
    ("VERIFICATION", "REPORT_RESTORE_RISK", "ACTIVE"),
])
def test_invalid_combinations_are_rejected(phase, operation, state):
    with pytest.raises(ValidationError):
        make_step(phase, operation, state)


def test_sort_key_uses_phase_operation_then_plain_string_ids():
    steps = [
        make_step("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT", "z", "r"),
        make_step("FINDING", "REPORT_EXPOSED_PII", "PRESENT", "z", "r"),
        make_step("FINDING", "REPORT_REMAINING_RECORD", "PRESENT", "z", "r"),
        make_step("FINDING", "REPORT_REMAINING_RECORD", "PRESENT", "a", "z"),
        make_step("FINDING", "REPORT_REMAINING_RECORD", "PRESENT", "a", "A"),
    ]
    ordered = order_steps(steps)
    assert [(s.phase, s.operation, s.system_id, s.resource_id) for s in ordered] == [
        (Phase.FINDING, "REPORT_REMAINING_RECORD", "a", "A"),
        (Phase.FINDING, "REPORT_REMAINING_RECORD", "a", "z"),
        (Phase.FINDING, "REPORT_REMAINING_RECORD", "z", "r"),
        (Phase.FINDING, "REPORT_EXPOSED_PII", "z", "r"),
        (Phase.VERIFICATION, "VERIFY_RECORD_PRESENT", "z", "r"),
    ]
    assert [s.step_no for s in ordered] == list(range(1, 6))


def test_serialization_is_json_array_with_exact_step_fields():
    step = make_step("FINDING", "REPORT_REMAINING_RECORD", "PRESENT")
    decoded = json.loads(serialize_steps([step]))
    assert decoded == [step.model_dump(mode="json")]
    assert set(decoded[0]) == {
        "step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"
    }


def test_sample_outputs_follow_spec_sort_order():
    for row in load_csv(__import__("pathlib").Path(__file__).resolve().parents[2] / "dataset" / "sample_output.csv"):
        parsed = json.loads(row.steps_json)
        steps = [Step.model_validate(item) for item in parsed]
        expected = order_steps(steps)
        assert [(s.phase, s.operation, s.system_id, s.resource_id) for s in steps] == [
            (s.phase, s.operation, s.system_id, s.resource_id) for s in expected
        ]
