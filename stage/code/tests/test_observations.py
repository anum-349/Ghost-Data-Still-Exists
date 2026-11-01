import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ghost_data.data import EvidenceFile
from ghost_data.observations import (
    CachedImageEvidenceReader,
    parse_evidence_file,
    parse_manifest_once,
    map_categories_to_rules,
    write_coverage_report,
)
from ghost_data.data import load_csv
from ghost_data.observations import Observation, ObservationIndex


CAPTURED = datetime(2026, 1, 1, tzinfo=timezone.utc)
TEST_DOMAIN = ".".join(("invalid", "test"))


def fixture_email(local: str) -> str:
    return local + "@" + TEST_DOMAIN


def manifest_row(file_id: str, path: str) -> EvidenceFile:
    return EvidenceFile(file_id=file_id, file_path=path, origin="fixture", captured_at=CAPTURED)


def test_category_mapping_uses_policy_categories_and_logs_unmapped_types(tmp_path):
    rules = load_csv(Path(__file__).resolve().parents[2] / "dataset" / "deletion_rules.csv")
    rule = next(item for item in rules if "profile" in item.data_category.casefold())
    known = Observation(file_id="f1", captured_at=CAPTURED, system_id="account_service",
        resource_id="account_fixture", data_category="", observed_resource_type="",
        source_table="customer_profiles")
    unknown = Observation(file_id="f2", captured_at=CAPTURED, system_id="misc_service",
        resource_id="unclassified_fixture", data_category="", observed_resource_type="", source_table="")
    result = map_categories_to_rules(ObservationIndex([known, unknown], []), rules, unmapped_log=tmp_path / "unmapped.jsonl")
    assert result.observations[0].data_category == rule.data_category
    assert result.observations[0].data_category_source == "rules_token_match"
    assert result.observations[1].data_category == ""
    assert '"reason": "unmapped"' in (tmp_path / "unmapped.jsonl").read_text(encoding="utf-8")


@pytest.mark.parametrize("table_field", ["customer_profiles", "customer_profile"])
def test_profile_collection_maps_to_user_profile_not_tombstone(table_field):
    rules = load_csv(Path(__file__).resolve().parents[2] / "dataset" / "deletion_rules.csv")
    known = Observation(file_id="f_profile", captured_at=CAPTURED, system_id="account_service",
        resource_id="account_fixture", data_category="", observed_resource_type="",
        source_table=table_field)
    result = map_categories_to_rules(ObservationIndex([known], []), rules)
    assert result.observations[0].data_category == "USER_PROFILE"


def test_account_prefix_alone_does_not_map_to_tombstone():
    rules = load_csv(Path(__file__).resolve().parents[2] / "dataset" / "deletion_rules.csv")
    known = Observation(file_id="f_account", captured_at=CAPTURED, system_id="account_service",
        resource_id="account_fixture", data_category="", observed_resource_type="",
        source_table="customer_accounts")
    result = map_categories_to_rules(ObservationIndex([known], []), rules)
    assert result.observations[0].data_category != "ACCOUNT_TOMBSTONE"


class FakeImageReader:
    def __init__(self):
        self.calls = 0

    def extract_text(self, image_path: Path) -> str:
        self.calls += 1
        return f"resource_id=account_321 system_id=account_service email={fixture_email('user')} enabled=true"


def test_json_fixture_normalizes_identifiers_and_states(tmp_path):
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps({"system_id": "analytics_platform", "resource_id": "analytics_321", "source_resource_id": "account_321", "data_category": "ANALYTICS_PROFILE", "email": None, "email_hash": "", "user_id": "user_321", "state": "ANONYMIZED", "anonymized": True, "identifiable": False}), encoding="utf-8")
    observations, coverage = parse_evidence_file(manifest_row("e_json", path.name), tmp_path)
    assert len(observations) == 1
    obs = observations[0]
    assert obs.system_id == "analytics_platform"
    assert obs.identifiers_present["user_id"] == ["user_321"]
    assert set(obs.identifiers_cleared) == {"email", "email_hash"}
    assert obs.resource_references == {"source_resource_id": ["account_321"]}
    assert obs.captured_at.utcoffset().total_seconds() == 0
    assert obs.anonymized is True and obs.identifiable is False
    assert coverage.stores == ["analytics_platform"]


def test_sql_fixture_loads_tables_and_extracts_json_rows(tmp_path):
    path = tmp_path / "fixture.sql"
    path.write_text(
        "-- untrusted snapshot header\n/* captured database export */\n"
        "CREATE TABLE customer_profiles (id INTEGER, payload TEXT);\n"
        "INSERT INTO customer_profiles VALUES (1, '{\"resource_id\":\"account_123\",\"email\":\"" + fixture_email("person") + "\",\"exists\":true}');\n",
        encoding="utf-8",
    )
    observations, coverage = parse_evidence_file(manifest_row("e_sql", path.name), tmp_path)
    assert "customer_profiles" in coverage.tables
    assert "account_service" in coverage.stores
    assert any(item.resource_id == "account_123" for item in observations)
    with pytest.raises(ValueError, match="unsupported SQL"):
        path.write_text("DROP TABLE customer_profiles;", encoding="utf-8")
        parse_evidence_file(manifest_row("e_sql", path.name), tmp_path)
    with pytest.raises(sqlite3.DatabaseError):
        path.write_text("CREATE TABLE unsafe (value TEXT CHECK(random() > 0));", encoding="utf-8")
        parse_evidence_file(manifest_row("e_sql", path.name), tmp_path)


@pytest.mark.parametrize("extension", [".log", ".txt"])
def test_line_record_fixtures_parse_flags_and_identifiers(tmp_path, extension):
    path = tmp_path / ("fixture" + extension)
    path.write_text(
        "resource_id=backup_23 system_id=backup_service data_category=BACKUP_ARCHIVE "
        "user_id=user_23 enabled=false restore_blocked=true deleted_at=2026-01-01T00:00:00Z\n",
        encoding="utf-8",
    )
    observations, _ = parse_evidence_file(manifest_row("e_line", path.name), tmp_path)
    assert len(observations) == 1
    obs = observations[0]
    assert obs.enabled_active is False
    assert obs.restore_blocked is True
    assert obs.deletion_marker is True
    assert obs.identifiers_present["user_id"] == ["user_23"]


def test_text_records_inherit_identifiers_across_shared_trace_only(tmp_path):
    path = tmp_path / "correlated.log"
    path.write_text(
        "trace_id=trace-fixture resource_id=account_fixture event=profile_lookup_completed rows=0 http_status=404\n"
        "trace_id=trace-fixture event=profile_lookup_started lookup_key=" + fixture_email("person") + "\n"
        "trace_id=trace-fixture pool=account_service_store event=connection_acquired\n"
        "trace_id=unrelated event=lookup_started lookup_key=" + fixture_email("other") + "\n",
        encoding="utf-8",
    )
    observations, _ = parse_evidence_file(manifest_row("e_trace", path.name), tmp_path)
    linked = next(item for item in observations if item.resource_id == "account_fixture")
    assert any(
        item.identifier_type == "email" and item.value == fixture_email("person")
        for item in linked.inherited_identifiers
    )
    assert any("shared_trace_id=trace-fixture" in item.provenance for item in linked.inherited_identifiers)
    store_name = next(item for item in observations if item.resource_id == "account_service_store")
    assert store_name.inherited_identifiers == []


def test_json_context_inherits_enclosing_lookup_and_correlated_sibling(tmp_path):
    path = tmp_path / "context.json"
    path.write_text(json.dumps({
        "lookup_key": fixture_email("parent"),
        "nested": {"resource_id": "account_parent"},
        "records": [
            {"resource_id": "account_sibling", "trace_id": "trace-fixture"},
            {"trace_id": "trace-fixture", "email": fixture_email("sibling")},
            {"trace_id": "trace-unrelated", "email": fixture_email("unrelated")},
        ],
        "paired_resource": {"resource_id": "account_object_sibling", "trace_id": "object-fixture"},
        "paired_lookup": {"trace_id": "object-fixture", "email": fixture_email("object")},
        "typed_lookup": {
            "lookup_key": "Fixture Name", "lookup_type": "full_name",
            "profile": {"resource_id": "account_typed_lookup"},
        },
    }), encoding="utf-8")
    observations, _ = parse_evidence_file(manifest_row("e_context", path.name), tmp_path)
    by_resource = {item.resource_id: item for item in observations}
    parent = by_resource["account_parent"]
    sibling = by_resource["account_sibling"]
    assert any(item.value == fixture_email("parent") for item in parent.inherited_identifiers)
    assert any(item.value == fixture_email("sibling") for item in sibling.inherited_identifiers)
    assert not any(item.value == fixture_email("unrelated") for item in sibling.inherited_identifiers)
    assert any("shared_trace_id=trace-fixture" in item.provenance for item in sibling.inherited_identifiers)
    object_sibling = by_resource["account_object_sibling"]
    assert any(item.value == fixture_email("object") for item in object_sibling.inherited_identifiers)
    assert any("shared_trace_id=object-fixture" in item.provenance for item in object_sibling.inherited_identifiers)
    typed_lookup = by_resource["account_typed_lookup"]
    assert any(
        item.identifier_type == "name" and item.value == "Fixture Name"
        for item in typed_lookup.inherited_identifiers
    )


def test_support_message_order_context_is_detected_from_message_excerpt(tmp_path):
    path = tmp_path / "support.json"
    path.write_text(json.dumps({
        "resource_id": "support_321", "data_category": "SUPPORT_MESSAGE",
        "customer_reference": "user_321", "message_excerpt": "Customer followed up about an order update.",
    }), encoding="utf-8")
    observations, _ = parse_evidence_file(manifest_row("support_context", path.name), tmp_path)
    assert observations[0].shared_context is True


def test_pdf_fixture_uses_injected_text_extractor(tmp_path):
    path = tmp_path / "fixture.pdf"
    path.write_bytes(b"synthetic PDF fixture")
    observations, _ = parse_evidence_file(
        manifest_row("e_pdf", path.name), tmp_path,
        pdf_extractor=lambda _: f"resource_id=support_7 system_id=support_platform email={fixture_email('reader')}",
    )
    assert observations[0].resource_id == "support_7"
    assert observations[0].identifiers_present["email"] == [fixture_email("reader")]


def test_png_uses_pluggable_reader_with_content_hash_cache(tmp_path):
    image = tmp_path / "fixture.png"
    image.write_bytes(b"synthetic image bytes")
    base_reader = FakeImageReader()
    cached = CachedImageEvidenceReader(base_reader, tmp_path / "ocr-cache")
    file = manifest_row("e_png", image.name)
    first, _ = parse_evidence_file(file, tmp_path, image_reader=cached)
    second, _ = parse_evidence_file(file, tmp_path, image_reader=cached)
    assert first == second
    assert first[0].resource_id == "account_321"
    assert base_reader.calls == 1
    image.write_bytes(b"different image bytes")
    parse_evidence_file(file, tmp_path, image_reader=cached)
    assert base_reader.calls == 2
    with pytest.raises(ValueError, match="image reader"):
        parse_evidence_file(file, tmp_path)


def test_manifest_is_parsed_once_and_indexes_are_built(tmp_path):
    path = tmp_path / "snapshot_records.json"
    path.write_text(json.dumps([{"resource_id": "search_9", "email": fixture_email("person")}]), encoding="utf-8")
    item = manifest_row("e_one", path.name)
    index = parse_manifest_once([item], tmp_path)
    assert index.by_resource_id["search_9"]
    assert index.by_identifier[("email", fixture_email("person"))]
    assert index.store_is_covered("e_one", "search_service")
    report = tmp_path / "coverage.md"
    write_coverage_report(index, report)
    assert "search_service" in report.read_text(encoding="utf-8")


def test_manifest_records_one_file_error_and_continues(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"resource_id": "search_10", "email": fixture_email("ok")}), encoding="utf-8")
    bad = tmp_path / "bad.sql"
    bad.write_text("DROP TABLE disallowed;", encoding="utf-8")
    errors = tmp_path / ".local" / "evidence_errors.jsonl"
    index = parse_manifest_once(
        [manifest_row("good_file", good.name), manifest_row("bad_file", bad.name)],
        tmp_path, error_log_path=errors,
    )
    assert len(index.observations) == 1
    assert index.unreadable_files["bad_file"].startswith("ValueError:")
    error_record = json.loads(errors.read_text(encoding="utf-8").strip())
    assert error_record["file_id"] == "bad_file"
    assert "unsupported SQL" in error_record["error"]


def test_evidence_paths_must_stay_within_dataset_root(tmp_path):
    with pytest.raises(ValueError, match="escapes dataset root"):
        parse_evidence_file(manifest_row("e_outside", "../escape.json"), tmp_path)
