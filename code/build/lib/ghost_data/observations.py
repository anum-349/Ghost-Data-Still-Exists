"""One-pass evidence parsing into normalized, indexed observations.

Evidence text is untrusted data. SQL is restricted to CREATE TABLE and INSERT
statements in an isolated in-memory SQLite connection; no evidence text is
passed to a shell or interpreted as policy/instructions.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .data import EvidenceFile


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_id: str
    captured_at: datetime
    system_id: str
    resource_id: str
    data_category: str
    data_category_source: str = "explicit"
    identifiers_present: dict[str, list[str]] = Field(default_factory=dict)
    identifiers_cleared: list[str] = Field(default_factory=list)
    exists: bool | None = None
    enabled_active: bool | None = None
    restore_blocked: bool | None = None
    anonymized: bool | None = None
    identifiable: bool | None = None
    deletion_marker: bool | None = None
    shared_context: bool | None = None
    belongs_only_to_subject: bool | None = None
    attributable: bool | None = None
    within_retention: bool | None = None
    retention_until: datetime | None = None
    legal_hold_active: bool | None = None
    restore_access_blockable: bool | None = None
    restore_allowed: bool | None = None
    deletion_blocked: bool | None = None
    scheduled: bool | None = None
    source_table: str = ""
    excerpt: str = ""

    @field_validator("captured_at")
    @classmethod
    def capture_time_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("retention_until")
    @classmethod
    def retention_time_is_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retention_until must be timezone-aware")
        return value.astimezone(timezone.utc)


class FileCoverage(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_id: str
    file_path: str
    captured_at: datetime
    tables: list[str] = Field(default_factory=list)
    stores: list[str] = Field(default_factory=list)
    observations: int = 0
    is_snapshot: bool = False

    @field_validator("captured_at")
    @classmethod
    def capture_time_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    def covers_store(self, system_id: str) -> bool:
        return self.is_snapshot and system_id in self.stores


class ImageEvidenceReader(Protocol):
    """Pluggable OCR/VLM interface. Return extracted visible text only."""

    def extract_text(self, image_path: Path) -> str: ...


class CachedImageEvidenceReader:
    """Cache image-reader output by SHA-256 of image bytes, not filename."""

    def __init__(self, reader: ImageEvidenceReader, cache_dir: Path) -> None:
        self.reader = reader
        self.cache_dir = cache_dir

    def extract_text(self, image_path: Path) -> str:
        digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        cache_file = self.cache_dir / f"{digest}.txt"
        if cache_file.is_file():
            return cache_file.read_text(encoding="utf-8")
        text = self.reader.extract_text(image_path)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, encoding="utf-8", newline="\n")
        return text


class ObservationIndex:
    def __init__(self, observations: list[Observation], coverage: list[FileCoverage]) -> None:
        self.observations = observations
        self.coverage = {item.file_id: item for item in coverage}
        by_identifier: dict[tuple[str, str], list[Observation]] = defaultdict(list)
        by_resource: dict[str, list[Observation]] = defaultdict(list)
        for observation in observations:
            by_resource[observation.resource_id].append(observation)
            for kind, values in observation.identifiers_present.items():
                for value in values:
                    by_identifier[(kind, normalize_identifier(kind, value))].append(observation)
        self.by_identifier = dict(by_identifier)
        self.by_resource_id = dict(by_resource)

    def store_is_covered(self, file_id: str, system_id: str) -> bool:
        coverage = self.coverage.get(file_id)
        return bool(coverage and coverage.covers_store(system_id))


IDENTIFIER_KEYS = {
    "email": "email", "email_address": "email", "phone": "phone", "phone_number": "phone",
    "name": "name", "full_name": "name", "email_hash": "email_hash", "user_id": "user_id",
    "owner_user_id": "user_id", "stable_user_id": "user_id", "subject_reference": "stable_reference",
    "customer_reference": "stable_reference",
}
RESOURCE_RE = re.compile(r"\b(?:account|search|analytics|support|export|backup|audit_record|data_flow|tombstone|marketing|object|cache|delivery|notification|user)_[A-Za-z0-9_-]+\b", re.I)
EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}(?![\w.-])", re.I)
HASH_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)")
SYSTEM_NAMES = {
    "account": "account_service", "profile": "account_service", "search": "search_service",
    "analytics": "analytics_platform", "support": "support_platform", "export": "export_service",
    "backup": "backup_service", "audit": "security_service", "security": "security_service",
    "data_flow": "integration_service", "connector": "integration_service", "tombstone": "identity_service",
    "identity": "identity_service", "marketing": "marketing_platform", "object": "object_storage",
    "cache": "cache_service", "delivery": "email_delivery_service", "notification": "notification_service",
}


def normalize_identifier(kind: str, value: str) -> str:
    if kind == "phone":
        return re.sub(r"\D", "", value)
    if kind in {"email", "email_hash", "user_id", "stable_reference"}:
        return value.casefold().strip()
    return " ".join(value.casefold().split())


def _system(resource: str, hint: str = "") -> str:
    for prefix, system in SYSTEM_NAMES.items():
        if prefix in (resource + " " + hint).casefold():
            return system
    if hint.endswith("_service") or hint.endswith("_platform") or hint == "object_storage":
        return hint
    return ""


def _resource(obj: dict, text: str = "") -> str:
    for key in ("resource_id", "resourceId", "record_id"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            return value
    found = RESOURCE_RE.search(text)
    return found.group(0) if found else ""


def _category(record: dict, resource: str, table: str, raw: str, file_path: str) -> tuple[str, str]:
    explicit = record.get("data_category") or record.get("category") or record.get("resource_type")
    if isinstance(explicit, str) and explicit:
        return explicit.upper(), "explicit"
    structural = " ".join((resource, table, file_path)).casefold().replace("-", "_")
    text = raw[:2000].casefold().replace("-", "_")
    # Map evidence vocabulary to the policy categories; required actions and
    # conditions themselves always come from deletion_rules.csv.
    for marker, category in (
        ("tombstone", "ACCOUNT_TOMBSTONE"),
        ("legal_hold", "LEGAL_HOLD_RECORD"),
        ("legal hold", "LEGAL_HOLD_RECORD"),
        ("backup", "BACKUP_ARCHIVE"),
        ("telemetry", "PRODUCT_TELEMETRY"),
        ("analytics", "ANALYTICS_PROFILE"),
        ("search", "SEARCH_INDEX_ENTRY"),
        ("cache", "CACHE_ENTRY"),
        ("attachment", "SUPPORT_ATTACHMENT"),
        ("email_delivery", "EMAIL_DELIVERY_LOG"),
        ("delivery_log", "EMAIL_DELIVERY_LOG"),
        ("support", "SUPPORT_MESSAGE"),
        ("audit", "SECURITY_AUDIT_LOG"),
        ("security", "SECURITY_AUDIT_LOG"),
        ("export", "USER_EXPORT"),
        ("marketing", "MARKETING_PROFILE"),
        ("secondary_identifier", "SECONDARY_IDENTIFIER"),
        ("profile", "USER_PROFILE"),
        ("account", "USER_PROFILE"),
    ):
        if marker in structural:
            return category, "resource_or_store"
    for marker, category in (("email delivery", "EMAIL_DELIVERY_LOG"), ("support attachment", "SUPPORT_ATTACHMENT"), ("support message", "SUPPORT_MESSAGE"), ("legal hold", "LEGAL_HOLD_RECORD")):
        if marker in text:
            return category, "text"
    return "", "unknown"


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [str(value)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return []


def _record_observation(
    *, file: EvidenceFile, resource: str, record: dict, raw: str, system_hint: str = "", table: str = "",
) -> Observation:
    identifiers: dict[str, list[str]] = defaultdict(list)
    cleared: set[str] = set()
    for key, value in record.items():
        kind = IDENTIFIER_KEYS.get(str(key).casefold())
        if not kind:
            continue
        if value is None or value == "":
            cleared.add(kind)
        else:
            for text in _strings(value):
                if text not in identifiers[kind]:
                    identifiers[kind].append(text)
    # Extract direct identifiers from raw text when the source uses free-form records.
    for email in EMAIL_RE.findall(raw):
        if email not in identifiers["email"]:
            identifiers["email"].append(email)
    for digest in HASH_RE.findall(raw):
        if digest not in identifiers["email_hash"]:
            identifiers["email_hash"].append(digest)
    category, category_source = _category(record, resource, table or str(record.get("collection") or record.get("collection_name") or ""), raw, file.file_path)
    state_text = " ".join(str(record.get(key, "")) for key in ("state", "status", "result", "restore_state", "deletion_state")).casefold()
    exists = _bool_value(record.get("exists"))
    if exists is None:
        if re.search(r"\b(not found|absent|deleted|missing)\b", state_text): exists = False
        elif re.search(r"\b(found|present|active|identifiable|anonymized|redacted)\b", state_text): exists = True
        elif Path(file.file_path).suffix.casefold() in {".sql", ".json"}: exists = True
    enabled = _bool_value(record.get("enabled"))
    if enabled is None:
        active_state = str(record.get("state") or record.get("status") or "").casefold()
        if active_state in {"active", "enabled", "scheduled", "running"}: enabled = True
        elif active_state in {"inactive", "disabled", "blocked", "stopped"}: enabled = False
    restore_blocked = _bool_value(record.get("restore_blocked"))
    if restore_blocked is None and "restore" in state_text:
        restore_blocked = "block" in state_text or "disabled" in state_text
    anonymized = _bool_value(record.get("anonymized"))
    if anonymized is None and "anonymized" in state_text: anonymized = True
    identifiable = _bool_value(record.get("identifiable"))
    if identifiable is None and "identifiable" in state_text: identifiable = True
    if identifiable is None and anonymized is True: identifiable = False
    if anonymized is None and identifiable is True: anonymized = False
    deletion_marker = _bool_value(record.get("deletion_marker"))
    if deletion_marker is None:
        if "deleted" in record:
            deletion_marker = _bool_value(record.get("deleted"))
        if deletion_marker is None:
            marker = record.get("deleted_at")
            if marker not in (None, "", False): deletion_marker = True
    shared_context = _first_bool(record, "shared_context", "shared_customer_context", "shared_agent_context", "shared_order_context")
    if shared_context is None and any(record.get(key) not in (None, "", False) for key in ("agent_id", "agent_name", "order_id", "shared_customer_id")):
        shared_context = True
    belongs_only = _first_bool(record, "belongs_only_to_subject", "subject_only", "attachment_belongs_only_to_subject")
    attributable = _first_bool(record, "attributable", "still_attributable", "user_linked", "identifiable")
    within_retention = _first_bool(record, "within_retention", "retention_active", "within_retention_period")
    legal_hold = _first_bool(record, "legal_hold_active", "hold_active", "active_legal_hold")
    if legal_hold is None:
        hold_state = str(record.get("legal_hold_status") or record.get("hold_status") or "").casefold()
        if hold_state in {"active", "held", "in_force"}: legal_hold = True
        elif hold_state in {"released", "inactive", "expired", "none"}: legal_hold = False
    restore_blockable = _first_bool(record, "restore_access_blockable", "restore_blockable", "can_block_restore")
    restore_allowed = _first_bool(record, "restore_allowed", "restore_access_allowed", "restore_enabled")
    deletion_blocked = _first_bool(record, "deletion_blocked", "deletion_block_applied", "restore_deletion_block")
    scheduled = _first_bool(record, "scheduled", "schedule_enabled", "recurring", "job_scheduled")
    retention_until = _first_datetime(record, "retention_until", "retain_until", "retention_expires_at", "expires_at")
    inferred_system = str(
        record.get("system_id") or record.get("system") or record.get("data_store")
        or record.get("origin_system") or record.get("target_system") or record.get("source_system")
        or system_hint or _system(resource, table)
    )
    return Observation(
        file_id=file.file_id, captured_at=file.captured_at,
        system_id=inferred_system, resource_id=resource, data_category=category,
        data_category_source=category_source,
        identifiers_present=dict(identifiers), identifiers_cleared=sorted(cleared),
        exists=exists, enabled_active=enabled, restore_blocked=restore_blocked,
        anonymized=anonymized, identifiable=identifiable, deletion_marker=deletion_marker,
        shared_context=shared_context, belongs_only_to_subject=belongs_only,
        attributable=attributable, within_retention=within_retention,
        retention_until=retention_until, legal_hold_active=legal_hold,
        restore_access_blockable=restore_blockable, restore_allowed=restore_allowed,
        deletion_blocked=deletion_blocked, scheduled=scheduled,
        source_table=table, excerpt=raw[:1000],
    )


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool): return value
    if isinstance(value, (int, float)) and value in (0, 1): return bool(value)
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in {"true", "yes", "1", "active", "enabled", "blocked", "anonymized", "deleted"}: return True
        if text in {"false", "no", "0", "inactive", "disabled", "unblocked", "identifiable"}: return False
    return None


def _first_bool(record: dict, *keys: str) -> bool | None:
    for key in keys:
        if key in record:
            parsed = _bool_value(record[key])
            if parsed is not None:
                return parsed
    return None


def _first_datetime(record: dict, *keys: str) -> datetime | None:
    for key in keys:
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            continue
        return parsed.astimezone(timezone.utc)
    return None


def _extract_json_records(value: object, file: EvidenceFile, hint: str = "") -> tuple[list[Observation], set[str]]:
    observations: list[Observation] = []
    stores: set[str] = set()
    if isinstance(value, dict):
        local_hint = str(value.get("system_id") or value.get("system") or value.get("data_store") or value.get("origin_system") or hint)
        store = local_hint if local_hint.endswith(("_service", "_platform")) or local_hint == "object_storage" else _system("", local_hint)
        if store:
            stores.add(store)
        resource = _resource(value)
        if resource:
            observation = _record_observation(
                file=file, resource=resource, record=value, raw=json.dumps(value, ensure_ascii=False, sort_keys=True),
                system_hint=local_hint, table=str(value.get("collection") or ""),
            )
            observations.append(observation)
            if observation.system_id: stores.add(observation.system_id)
        for key, child in value.items():
            child_hint = key if key.endswith(("_service", "_platform")) or key == "object_storage" else local_hint
            children, child_stores = _extract_json_records(child, file, child_hint)
            observations.extend(children); stores.update(child_stores)
    elif isinstance(value, list):
        for child in value:
            children, child_stores = _extract_json_records(child, file, hint)
            observations.extend(children); stores.update(child_stores)
    return observations, stores


def _safe_sql_snapshot(path: Path, file: EvidenceFile) -> tuple[list[Observation], set[str], list[str]]:
    source = path.read_text(encoding="utf-8", errors="replace")
    # SQLite's statement splitter is not exposed, use complete_statement while
    # retaining semicolon-terminated input and reject every non-read-data DDL/DML.
    statements: list[str] = []
    buffer = ""
    for line in source.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = re.sub(
                r"(?s)^\s*(?:(?:--[^\n]*(?:\n|$))|(?:/\*.*?\*/\s*))*", "", buffer
            ).strip()
            buffer = ""
            if statement: statements.append(statement)
    trailing = re.sub(r"(?s)(?:--[^\n]*(?:\n|$)|/\*.*?\*/\s*)", "", buffer).strip()
    if trailing:
        raise ValueError(f"incomplete SQL statement in {path.name}")
    connection = sqlite3.connect(":memory:")
    try:
        forbidden_actions = {
            sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_DROP_TRIGGER,
            sqlite3.SQLITE_CREATE_VIEW, sqlite3.SQLITE_DROP_VIEW,
            sqlite3.SQLITE_CREATE_VTABLE, sqlite3.SQLITE_DROP_VTABLE,
            sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_PRAGMA,
        }
        def authorize(action, arg1, arg2, database, trigger):
            if action == sqlite3.SQLITE_FUNCTION and str(arg2 or arg1).casefold() == "json_valid":
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY if action in forbidden_actions else sqlite3.SQLITE_OK
        connection.set_authorizer(authorize)
        for statement in statements:
            if re.match(r"(?is)^\s*(BEGIN(?:\s+TRANSACTION)?|COMMIT|END|ROLLBACK)\s*;?\s*$", statement):
                continue
            if re.match(r"(?is)^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\b", statement):
                continue
            if not re.match(r"(?is)^\s*(CREATE\s+TABLE|INSERT\s+(?:OR\s+\w+\s+)?INTO)\b", statement):
                if re.match(r"(?is)^\s*(--|/\*|PRAGMA)\b", statement):
                    continue
                raise ValueError(f"unsupported SQL statement in evidence file {path.name}")
            if statement.lstrip().casefold().startswith("insert") and (
                not re.search(r"(?is)\bVALUES\b", statement)
                or re.search(r"(?is)\bSELECT\b", statement)
            ):
                raise ValueError(f"only literal INSERT ... VALUES rows are allowed in {path.name}")
            connection.execute(statement)
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        observations: list[Observation] = []
        stores: set[str] = set()
        for table in tables:
            quoted_table = '"' + table.replace('"', '""') + '"'
            cursor = connection.execute(f"SELECT * FROM {quoted_table} LIMIT 0")
            columns = [column[0] for column in cursor.description or []]
            store = _system("", table)
            if store: stores.add(store)
            for row in connection.execute(f"SELECT * FROM {quoted_table}"):
                record = dict(zip(columns, row))
                raw = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
                nested_count = 0
                # Records often live as JSON text within a single snapshot column.
                for value in list(record.values()):
                    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
                        try:
                            parsed = json.loads(value)
                        except json.JSONDecodeError:
                            continue
                        nested, nested_stores = _extract_json_records(parsed, file, table)
                        nested_count += len(nested)
                        observations.extend(nested); stores.update(nested_stores)
                resource = _resource(record, raw)
                if resource and not nested_count:
                    item = _record_observation(file=file, resource=resource, record=record, raw=raw, table=table)
                    observations.append(item)
                    if item.system_id: stores.add(item.system_id)
        return observations, stores, tables
    finally:
        connection.close()


def _record_from_line(line: str) -> dict:
    try:
        value = json.loads(line)
        if isinstance(value, dict): return value
    except json.JSONDecodeError:
        pass
    result = {}
    # Simpler scanner for common key=value records while preserving quoted values.
    for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s,;|]+)", line):
        result[match.group(1)] = match.group(2).strip("\"'")
    for kind, pattern in (("email", EMAIL_RE), ("email_hash", HASH_RE), ("phone", PHONE_RE)):
        vals = pattern.findall(line)
        if vals: result.setdefault(kind, vals[0])
    return result


def _parse_text(text: str, file: EvidenceFile, *, source: str = "text") -> tuple[list[Observation], set[str]]:
    observations: list[Observation] = []
    stores: set[str] = set()
    for line in text.splitlines():
        record = _record_from_line(line)
        resource = _resource(record, line)
        if not resource: continue
        hint = str(record.get("system_id") or record.get("system") or "")
        item = _record_observation(file=file, resource=resource, record=record, raw=line, system_hint=hint)
        observations.append(item)
        if item.system_id: stores.add(item.system_id)
    return observations, stores


def extract_pdf_text(path: Path) -> str:
    result = subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True, capture_output=True, text=True, encoding="utf-8")
    return result.stdout


def _json_is_snapshot(value: object, filename: str) -> bool:
    if any(term in filename.casefold() for term in ("snapshot", "replica", "inventory")):
        return True
    marker_names = {"snapshot_at", "snapshot_time", "snapshot_scope", "captured_at", "capture_time"}
    def contains_marker(item: object) -> bool:
        if isinstance(item, dict):
            return bool(marker_names.intersection(key.casefold() for key in item)) or any(contains_marker(child) for child in item.values())
        if isinstance(item, list):
            return any(contains_marker(child) for child in item)
        return False
    return contains_marker(value)


def parse_evidence_file(
    file: EvidenceFile,
    dataset_root: Path,
    *,
    image_reader: ImageEvidenceReader | None = None,
    pdf_extractor=extract_pdf_text,
) -> tuple[list[Observation], FileCoverage]:
    root = dataset_root.resolve()
    path = (root / file.file_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"evidence path escapes dataset root: {file.file_id}")
    extension = path.suffix.casefold()
    tables: list[str] = []
    is_snapshot = False
    if extension == ".sql":
        observations, stores, tables = _safe_sql_snapshot(path, file)
        is_snapshot = True
    elif extension == ".json":
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            root_value = json.loads(text)
            observations, stores = _extract_json_records(root_value, file)
            is_snapshot = _json_is_snapshot(root_value, path.name)
        except json.JSONDecodeError:
            observations, stores = _parse_text(text, file, source="json-lines")
    elif extension == ".pdf":
        observations, stores = _parse_text(pdf_extractor(path), file, source="pdf")
    elif extension == ".png":
        if image_reader is None:
            raise ValueError(f"an image reader is required to parse {file.file_id}")
        observations, stores = _parse_text(image_reader.extract_text(path), file, source="image-ocr")
    elif extension in {".log", ".txt"}:
        observations, stores = _parse_text(path.read_text(encoding="utf-8", errors="replace"), file, source=extension[1:])
    else:
        raise ValueError(f"unsupported evidence extension: {extension}")
    coverage = FileCoverage(
        file_id=file.file_id, file_path=file.file_path,
        captured_at=file.captured_at,
        tables=sorted(set(tables)), stores=sorted(stores), observations=len(observations), is_snapshot=is_snapshot,
    )
    return observations, coverage


def parse_manifest_once(
    manifest: list[EvidenceFile], dataset_root: Path, *, image_reader: ImageEvidenceReader | None = None,
) -> ObservationIndex:
    """Parse each manifest path once and build identifier/resource indexes."""
    observations: list[Observation] = []
    coverage: list[FileCoverage] = []
    seen: set[str] = set()
    seen_paths: set[str] = set()
    for item in manifest:
        if item.file_id in seen:
            raise ValueError(f"duplicate evidence file_id: {item.file_id}")
        resolved_path = str((dataset_root.resolve() / item.file_path).resolve())
        if resolved_path in seen_paths:
            raise ValueError(f"evidence path is listed more than once: {item.file_path}")
        seen.add(item.file_id)
        seen_paths.add(resolved_path)
        parsed, report = parse_evidence_file(item, dataset_root, image_reader=image_reader)
        observations.extend(parsed)
        coverage.append(report)
    return ObservationIndex(observations, coverage)


def write_coverage_report(index: ObservationIndex, path: Path) -> None:
    """Write snapshot table/store coverage; store absence requires this coverage."""
    rows = ["# Evidence Snapshot Coverage", "", "A store can support an absence claim only when the artifact is identified as a snapshot and has an extracted table or explicit records mapped to that store. Evidence content is treated as untrusted data.", "", "| file_id | captured_at | snapshot | tables | stores | observations |", "|---|---|---|---|---|---:|"]
    for file_id, item in sorted(index.coverage.items()):
        captured = item.captured_at.isoformat().replace("+00:00", "Z")
        rows.append(f"| {file_id} | {captured} | {item.is_snapshot} | {', '.join(item.tables) or '(none)'} | {', '.join(item.stores) or '(none)'} | {item.observations} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
