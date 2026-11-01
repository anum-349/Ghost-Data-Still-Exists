"""Validated output-step schema, ordering, and deterministic serialization."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Phase(StrEnum):
    FINDING = "FINDING"
    REMEDIATION = "REMEDIATION"
    VERIFICATION = "VERIFICATION"


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_no: int
    phase: Phase
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str

    @model_validator(mode="after")
    def operation_matches_phase_and_state(self) -> "Step":
        allowed = {
            Phase.FINDING: {
                "REPORT_REMAINING_RECORD": "PRESENT",
                "REPORT_EXPOSED_PII": "PRESENT",
                "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
                "REPORT_RESTORE_RISK": "ACTIVE",
            },
            Phase.REMEDIATION: {
                "DISABLE_DATA_FLOW": "DISABLED",
                "BLOCK_RESTORE": "BLOCKED",
                "DELETE_RECORD": "ABSENT",
                "REDACT_RECORD": "REDACTED",
                "ANONYMIZE_RECORD": "ANONYMIZED",
            },
            Phase.VERIFICATION: {
                "VERIFY_RECORD_ABSENT": "ABSENT",
                "VERIFY_RECORD_PRESENT": "PRESENT",
                "VERIFY_RECORD_REDACTED": "REDACTED",
                "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
                "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
                "VERIFY_RESTORE_BLOCKED": "BLOCKED",
            },
        }
        expected_state = allowed[self.phase].get(self.operation)
        if expected_state is None:
            raise ValueError(f"operation {self.operation!r} is not valid in {self.phase.value}")
        if self.state != expected_state:
            raise ValueError(
                f"{self.operation} in {self.phase.value} requires state {expected_state!r}"
            )
        if self.step_no < 1:
            raise ValueError("step_no must be positive")
        return self


PHASE_ORDER = (Phase.FINDING, Phase.REMEDIATION, Phase.VERIFICATION)
OPERATION_ORDER: dict[Phase, tuple[str, ...]] = {
    Phase.FINDING: (
        "REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK",
    ),
    Phase.REMEDIATION: (
        "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD",
    ),
    Phase.VERIFICATION: (
        "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED",
        "VERIFY_RECORD_ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED",
    ),
}


def step_sort_key(step: Step) -> tuple[int, int, str, str]:
    """Problem-statement order; system/resource use ordinary string ordering."""
    return (
        PHASE_ORDER.index(step.phase),
        OPERATION_ORDER[step.phase].index(step.operation),
        step.system_id,
        step.resource_id,
    )


def order_steps(steps: list[Step]) -> list[Step]:
    ordered = sorted(steps, key=step_sort_key)
    return [step.model_copy(update={"step_no": index}) for index, step in enumerate(ordered, 1)]


def serialize_steps(steps: list[Step]) -> str:
    """Serialize steps as compact JSON; caller must pass already ordered steps."""
    return json.dumps([step.model_dump(mode="json") for step in steps], separators=(",", ":"), ensure_ascii=False)
