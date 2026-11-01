"""Typed, read-only loaders for participant-facing CSV inputs."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, field_validator


class CsvModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(timezone.utc)


class DeletionRequest(CsvModel):
    case_id: str
    email: str
    requested_at: datetime
    reported_status: str
    reported_at: datetime
    audit_at: datetime
    request_text: str

    _timestamps = field_validator("requested_at", "reported_at", "audit_at")(_utc)


class UserIdentity(CsvModel):
    user_id: str
    name: str
    email: str
    phone: str
    email_hash: str
    updated_at: datetime

    _updated_at = field_validator("updated_at")(_utc)


class UserAuditEvent(CsvModel):
    audit_id: str
    user_id: str
    event_time: datetime
    field_name: str
    old_value: str
    new_value: str

    _event_time = field_validator("event_time")(_utc)


class SystemActivity(CsvModel):
    activity_id: str
    event_time: datetime
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str

    _event_time = field_validator("event_time")(_utc)


class DeletionRule(CsvModel):
    rule_id: str
    data_category: str
    condition: str
    required_action: str


class EvidenceFile(CsvModel):
    file_id: str
    file_path: str
    origin: str
    captured_at: datetime

    _captured_at = field_validator("captured_at")(_utc)


class OutputRow(CsvModel):
    case_id: str
    deletion_status: str
    steps_json: str


M = TypeVar("M", bound=CsvModel)


CSV_MODELS: dict[str, type[CsvModel]] = {
    "deletion_requests.csv": DeletionRequest,
    "sample_deletion_requests.csv": DeletionRequest,
    "user_identities.csv": UserIdentity,
    "user_audit_log.csv": UserAuditEvent,
    "system_activity.csv": SystemActivity,
    "deletion_rules.csv": DeletionRule,
    "evidence_files.csv": EvidenceFile,
    "output.csv": OutputRow,
    "sample_output.csv": OutputRow,
}


def load_csv(path: Path, model: type[M] | None = None) -> list[M]:
    """Load a known dataset CSV, validating every row against its Pydantic model."""
    selected = model or CSV_MODELS.get(path.name)
    if selected is None:
        raise ValueError(f"no CSV schema registered for {path.name!r}")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return [selected.model_validate(row) for row in csv.DictReader(stream)]


def at_or_before(timestamp: datetime, cutoff: datetime) -> bool:
    """Inclusive, timezone-normalized temporal eligibility comparison."""
    return _utc(timestamp) <= _utc(cutoff)
