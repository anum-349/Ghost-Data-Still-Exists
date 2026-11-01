import csv
import json
import threading
import time
from pathlib import Path

import pytest

from ghost_data.cli import run_cases, validate_output_file
from ghost_data.data import DeletionRequest, OutputRow, load_csv


DATASET = Path(__file__).resolve().parents[2] / "dataset"


def _complete_row(request: DeletionRequest) -> OutputRow:
    payload = [{
        "step_no": 1,
        "phase": "VERIFICATION",
        "system_id": "account_service",
        "resource_id": "resource_fixture",
        "operation": "VERIFY_RECORD_ABSENT",
        "state": "ABSENT",
        "evidence_id": "evidence_fixture",
    }]
    return OutputRow(
        case_id=request.case_id,
        deletion_status="COMPLETE",
        steps_json=json.dumps(payload),
    )


def test_run_cases_writes_sorted_quoted_csv_and_limits_concurrency(tmp_path):
    requests = load_csv(DATASET / "deletion_requests.csv", DeletionRequest)
    guard = threading.Lock()
    active = 0
    max_active = 0

    def processor(request):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.001)
        result = _complete_row(request)
        with guard:
            active -= 1
        return result

    output = tmp_path / "output.csv"
    failures_path = tmp_path / ".local" / "failures.jsonl"
    rows, failures = run_cases(
        requests, processor, output_path=output, failure_log_path=failures_path, concurrency=5,
    )

    assert len(rows) == 518 and failures == []
    assert max_active <= 5 and max_active > 1
    assert [row.case_id for row in rows] == sorted(request.case_id for request in requests)
    checked = validate_output_file(output, {request.case_id for request in requests})
    assert len(checked) == 518
    with output.open("r", encoding="utf-8", newline="") as stream:
        raw_rows = list(csv.DictReader(stream))
    assert raw_rows[0]["steps_json"].startswith('[{"step_no": 1')
    assert json.loads(raw_rows[0]["steps_json"])[0]["operation"] == "VERIFY_RECORD_ABSENT"
    assert failures_path.read_text(encoding="utf-8") == ""


def test_case_errors_emit_safe_fallback_and_are_logged_without_crashing(tmp_path):
    requests = load_csv(DATASET / "deletion_requests.csv", DeletionRequest)
    failing_request = requests[0]

    def processor(request):
        if request.case_id == failing_request.case_id:
            raise RuntimeError("synthetic failure")
        return OutputRow(case_id=request.case_id, deletion_status="NOT_APPLICABLE", steps_json="[]")

    output = tmp_path / "output.csv"
    failure_path = tmp_path / ".local" / "failures.jsonl"
    rows, failures = run_cases(
        requests, processor, output_path=output, failure_log_path=failure_path, concurrency=4,
    )

    assert len(rows) == 518
    assert len(failures) == 1
    fallback = next(row for row in rows if row.case_id == failing_request.case_id)
    assert fallback.deletion_status == "INCOMPLETE" and fallback.steps_json == "[]"
    logged = json.loads(failure_path.read_text(encoding="utf-8").strip())
    assert logged["case_id"] == failing_request.case_id
    assert logged["error_type"] == "RuntimeError"
    assert "synthetic failure" in logged["error"]
    assert ":processor" in logged["traceback_summary"]


def test_duplicate_input_ids_fail_before_work(tmp_path):
    request = load_csv(DATASET / "deletion_requests.csv", DeletionRequest)[0]
    with pytest.raises(ValueError, match="duplicate case_ids"):
        run_cases(
            [request, request], lambda _request: _complete_row(request),
            output_path=tmp_path / "out.csv", failure_log_path=tmp_path / "failures.jsonl",
        )


def test_output_validator_rejects_invalid_json_and_duplicate_ids(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_text(
        'case_id,deletion_status,steps_json\nfixture,NOT_APPLICABLE,"not-json"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid steps_json"):
        validate_output_file(path, {"fixture"})

    path.write_text(
        'case_id,deletion_status,steps_json\nfixture,NOT_APPLICABLE,[]\nfixture,NOT_APPLICABLE,[]\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate case_ids"):
        validate_output_file(path, {"fixture", "another_fixture"})


def test_output_validator_rejects_complete_without_evidence_backed_verification(tmp_path):
    path = tmp_path / "invalid_complete.csv"
    path.write_text(
        "case_id,deletion_status,steps_json\nfixture,COMPLETE,[]\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="COMPLETE requires at least one evidence-backed verification"):
        validate_output_file(path, {"fixture"})
