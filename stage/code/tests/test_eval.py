import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATION = REPO_ROOT / "evaluation"
if not EVALUATION.is_dir():
    EVALUATION = REPO_ROOT / "code" / "evaluation"
sys.path.insert(0, str(EVALUATION))

from run_eval import evaluate, main
from ghost_data.data import OutputRow, load_csv


def _step(number, operation, resource):
    return {
        "step_no": number,
        "phase": "VERIFICATION",
        "system_id": "fixture_service",
        "resource_id": resource,
        "operation": operation,
        "state": "ABSENT",
        "evidence_id": "fixture_evidence",
    }


def _row(case_suffix, status, steps):
    return OutputRow(
        case_id="fixture_" + case_suffix,
        deletion_status=status,
        steps_json=json.dumps(steps),
    )


def test_metrics_include_multiset_steps_fields_and_lcs_sequence():
    reference = [_row("a", "COMPLETE", [
        _step(1, "VERIFY_RECORD_ABSENT", "resource_a"),
        _step(2, "VERIFY_RECORD_ABSENT", "resource_b"),
        _step(3, "VERIFY_RECORD_ABSENT", "resource_c"),
    ])]
    prediction = [_row("a", "COMPLETE", [
        _step(1, "VERIFY_RECORD_ABSENT", "resource_a"),
        _step(2, "VERIFY_RECORD_ABSENT", "resource_c"),
    ])]

    result = evaluate(reference, prediction)

    assert result["status_accuracy"] == 1.0
    assert result["step_precision"] == 1.0
    assert result["step_recall"] == 2 / 3
    assert result["step_f1"] == 0.8
    assert result["sequence_exact_accuracy"] == 0.0
    assert result["sequence_lcs_reference_recall"] == 2 / 3
    assert result["sequence_lcs_normalized_similarity"] == 2 / 3
    assert result["field_accuracy"]["resource_id"] == 2 / 3
    assert result["diffs"][0].sample_row == 1


def test_empty_prediction_file_fails_the_case_id_threshold(tmp_path):
    root = Path(__file__).resolve().parents[2]
    empty_predictions = tmp_path / "output.csv"
    empty_predictions.write_text("case_id,deletion_status,steps_json\n", encoding="utf-8")
    report_path = tmp_path / "evaluation_report.md"

    result = main([
        "--predictions", str(empty_predictions),
        "--reference", str(root / "dataset" / "sample_output.csv"),
        "--report", str(report_path),
    ])

    assert result == 2
    assert not report_path.exists()


def test_evaluator_allows_exactly_half_the_expected_case_ids(tmp_path, capsys):
    root = Path(__file__).resolve().parents[2]
    reference_rows = load_csv(root / "dataset" / "sample_output.csv", OutputRow)
    reference = tmp_path / "reference.csv"
    predictions = tmp_path / "predictions.csv"
    report_path = tmp_path / "evaluation_report.md"
    for path, rows in ((reference, reference_rows), (predictions, reference_rows[:len(reference_rows) // 2])):
        path.write_text(
            "case_id,deletion_status,steps_json\n"
            + "".join(
                f'{row.case_id},{row.deletion_status},"{row.steps_json.replace(chr(34), chr(34) * 2)}"\n'
                for row in rows
            ),
            encoding="utf-8",
        )

    result = main([
        "--predictions", str(predictions),
        "--reference", str(reference),
        "--report", str(report_path),
    ])

    assert result == 0
    assert "Matched expected case IDs: 16 / 32" in report_path.read_text(encoding="utf-8")
    assert "Evaluation failed" not in capsys.readouterr().err


def test_evaluator_rejects_fewer_than_half_the_expected_case_ids(tmp_path, capsys):
    root = Path(__file__).resolve().parents[2]
    reference_rows = load_csv(root / "dataset" / "sample_output.csv", OutputRow)
    reference = tmp_path / "reference.csv"
    predictions = tmp_path / "predictions.csv"
    report_path = tmp_path / "evaluation_report.md"
    reference.write_text(
        "case_id,deletion_status,steps_json\n"
        + "".join(
            f'{row.case_id},{row.deletion_status},"{row.steps_json.replace(chr(34), chr(34) * 2)}"\n'
            for row in reference_rows
        ),
        encoding="utf-8",
    )
    predictions.write_text(
        "case_id,deletion_status,steps_json\n"
        + "".join(
            f'{row.case_id},{row.deletion_status},"{row.steps_json.replace(chr(34), chr(34) * 2)}"\n'
            for row in reference_rows[:len(reference_rows) // 2 - 1]
        ),
        encoding="utf-8",
    )

    result = main([
        "--predictions", str(predictions),
        "--reference", str(reference),
        "--report", str(report_path),
    ])

    assert result == 2
    assert "15 of 32 expected case IDs" in capsys.readouterr().err
    assert not report_path.exists()


def test_perfect_prediction_has_no_diffs_and_all_metrics_are_perfect():
    rows = [_row("a", "NOT_APPLICABLE", [])]
    result = evaluate(rows, rows)
    assert result["status_accuracy"] == 1.0
    assert result["sequence_exact_accuracy"] == 1.0
    assert result["step_precision"] == result["step_recall"] == result["step_f1"] == 1.0
    assert result["diffs"] == []


def test_step_and_field_metrics_match_by_key_but_sequence_metrics_remain_positional():
    reference = [_row("a", "COMPLETE", [
        _step(1, "VERIFY_RECORD_ABSENT", "resource_a"),
        _step(2, "VERIFY_RECORD_ABSENT", "resource_b"),
    ])]
    prediction = [_row("a", "COMPLETE", [
        _step(1, "VERIFY_RECORD_ABSENT", "resource_b"),
        _step(2, "VERIFY_RECORD_ABSENT", "resource_a"),
    ])]
    result = evaluate(reference, prediction)
    assert result["step_precision"] == result["step_recall"] == result["step_f1"] == 1.0
    assert result["field_accuracy"]["resource_id"] == 1.0
    assert result["field_accuracy"]["step_no"] == 0.0
    assert result["sequence_exact_accuracy"] == 0.0
    assert result["sequence_lcs_reference_recall"] == 0.5
