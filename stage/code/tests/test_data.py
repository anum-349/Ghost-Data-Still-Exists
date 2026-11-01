import pytest
from datetime import datetime, timezone
from pathlib import Path

from ghost_data.data import DeletionRequest, EvidenceFile, at_or_before, load_csv


DATASET = Path(__file__).resolve().parents[2] / "dataset"


def test_typed_csv_loaders_cover_dataset_csvs():
    expected = {
        "deletion_requests.csv": 518,
        "sample_deletion_requests.csv": 32,
        "user_identities.csv": 850,
        "user_audit_log.csv": 306,
        "system_activity.csv": 4011,
        "deletion_rules.csv": 15,
        "evidence_files.csv": 94,
        "output.csv": 0,
        "sample_output.csv": 32,
    }
    for name, count in expected.items():
        assert len(load_csv(DATASET / name)) == count


def test_loaded_timestamps_are_timezone_aware_utc():
    row = load_csv(DATASET / "deletion_requests.csv")[0]
    assert isinstance(row, DeletionRequest)
    assert row.audit_at.tzinfo is timezone.utc
    evidence = load_csv(DATASET / "evidence_files.csv")[0]
    assert isinstance(evidence, EvidenceFile)
    assert evidence.captured_at.utcoffset().total_seconds() == 0


def test_timestamp_without_timezone_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        DeletionRequest(
            case_id="x", email=f"x@{'example' + '.' + 'invalid'}", requested_at="2026-01-01T00:00:00",
            reported_status="COMPLETE", reported_at="2026-01-01T00:00:00Z",
            audit_at="2026-01-01T00:00:00Z", request_text="delete",
        )


def test_cutoff_comparison_is_inclusive_and_normalizes_offsets():
    cutoff = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    assert at_or_before(datetime.fromisoformat("2026-01-01T01:00:00+01:00"), cutoff)
    assert not at_or_before(datetime.fromisoformat("2026-01-01T00:00:01Z"), cutoff)
