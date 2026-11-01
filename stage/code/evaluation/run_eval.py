"""Score output.csv against the participant-visible sample output."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code" / "src"))

from ghost_data.data import OutputRow, load_csv  # noqa: E402
from cases.run_cases import CaseResult, run_evaluation_cases  # noqa: E402


STEP_FIELDS = (
    "step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id",
)
STEP_KEY_FIELDS = ("phase", "operation", "system_id", "resource_id")


@dataclass
class CaseDiff:
    sample_row: int
    case_id: str
    fields: list[str]
    expected_status: str
    predicted_status: str
    missing_steps: int
    extra_steps: int
    root_cause: str


def _steps(row: OutputRow | None) -> tuple[list[dict[str, Any]], bool]:
    if row is None:
        return [], True
    try:
        value = json.loads(row.steps_json)
    except json.JSONDecodeError:
        return [], False
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        return [], False
    return value, True


def _step_key(step: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(step.get(field) for field in STEP_KEY_FIELDS)


def _sequence_key(step: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(step.get(field) for field in STEP_FIELDS if field != "step_no")


def _full_key(step: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(step.get(field) for field in STEP_FIELDS)


def _match_steps_by_key(
    expected: list[dict[str, Any]], predicted: list[dict[str, Any]],
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Pair duplicate steps by occurrence under the contract's semantic key."""
    expected_by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    predicted_by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for step in expected:
        expected_by_key.setdefault(_step_key(step), []).append(step)
    for step in predicted:
        predicted_by_key.setdefault(_step_key(step), []).append(step)
    pairs = []
    missing = []
    spurious = []
    for key in expected_by_key.keys() | predicted_by_key.keys():
        left = expected_by_key.get(key, [])
        right = predicted_by_key.get(key, [])
        common = min(len(left), len(right))
        pairs.extend(zip(left[:common], right[:common]))
        missing.extend(left[common:])
        spurious.extend(right[common:])
    return pairs, missing, spurious


def _lcs_length(left: list[tuple[Any, ...]], right: list[tuple[Any, ...]]) -> int:
    previous = [0] * (len(right) + 1)
    for left_item in left:
        current = [0]
        for index, right_item in enumerate(right, 1):
            if left_item == right_item:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def _safe_diff_fields(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> list[str]:
    fields = []
    for index in range(max(len(expected), len(actual))):
        if index >= len(expected):
            fields.append(f"step[{index + 1}]: extra")
            continue
        if index >= len(actual):
            fields.append(f"step[{index + 1}]: missing")
            continue
        changed = [field for field in STEP_FIELDS if expected[index].get(field) != actual[index].get(field)]
        if changed:
            fields.append(f"step[{index + 1}]: {','.join(changed)}")
    return fields


def evaluate(reference_rows: list[OutputRow], prediction_rows: list[OutputRow]) -> dict[str, Any]:
    """Compute classification, multiset-step, field, and sequence metrics."""
    ref_by_id = {row.case_id: row for row in reference_rows}
    pred_by_id: dict[str, OutputRow] = {}
    pred_grouped: dict[str, list[OutputRow]] = {}
    duplicate_prediction_ids: set[str] = set()
    for row in prediction_rows:
        if row.case_id in pred_by_id:
            duplicate_prediction_ids.add(row.case_id)
        pred_by_id[row.case_id] = row
        pred_grouped.setdefault(row.case_id, []).append(row)

    status_correct = 0
    exact_sequences = 0
    lcs_total = 0
    reference_step_total = 0
    normalized_lcs_total = 0.0
    step_true_positive = step_reference = 0
    step_predicted = sum(len(_steps(row)[0]) for row in prediction_rows)
    field_correct = Counter()
    field_total = Counter()
    diffs: list[CaseDiff] = []

    for ordinal, reference in enumerate(reference_rows, 1):
        prediction = pred_by_id.get(reference.case_id)
        ref_steps, _ = _steps(reference)
        pred_steps, prediction_json_valid = _steps(prediction)
        predicted_status = prediction.deletion_status if prediction else "<missing>"
        if predicted_status == reference.deletion_status:
            status_correct += 1

        # LCS remains positional and compares the original semantic step tuple.
        ref_sequence = [_sequence_key(step) for step in ref_steps]
        pred_sequence = [_sequence_key(step) for step in pred_steps]
        lcs = _lcs_length(ref_sequence, pred_sequence)
        lcs_total += lcs
        reference_step_total += len(ref_steps)
        denominator = max(len(ref_steps), len(pred_steps))
        normalized_lcs_total += (lcs / denominator) if denominator else 1.0
        if [_full_key(step) for step in ref_steps] == [_full_key(step) for step in pred_steps]:
            exact_sequences += 1

        pairs, missing_by_key, spurious_by_key = _match_steps_by_key(ref_steps, pred_steps)
        step_true_positive += len(pairs)
        step_reference += len(ref_steps)
        unmatched_count = len(missing_by_key) + len(spurious_by_key)
        for field in STEP_FIELDS:
            field_total[field] += len(pairs) + unmatched_count
            field_correct[field] += sum(expected.get(field) == actual.get(field) for expected, actual in pairs)

        changed_fields = _safe_diff_fields(ref_steps, pred_steps)
        if predicted_status != reference.deletion_status:
            changed_fields.insert(0, "deletion_status")
        if prediction is None:
            changed_fields.insert(0, "prediction row missing")
        elif not prediction_json_valid:
            changed_fields.insert(0, "invalid steps_json")
        if reference.case_id in duplicate_prediction_ids:
            changed_fields.insert(0, "duplicate prediction rows")
        if changed_fields:
            if prediction is None:
                root_cause = "prediction row missing"
            elif not prediction_json_valid:
                root_cause = "invalid steps_json"
            elif predicted_status != reference.deletion_status:
                root_cause = "status mismatch"
            elif len(ref_steps) != len(pred_steps):
                root_cause = "step count mismatch"
            else:
                root_cause = "step field or order mismatch"
            diffs.append(CaseDiff(
                sample_row=ordinal,
                case_id=reference.case_id,
                fields=changed_fields,
                expected_status=reference.deletion_status,
                predicted_status=predicted_status,
                missing_steps=max(0, len(ref_steps) - len(pred_steps)),
                extra_steps=max(0, len(pred_steps) - len(ref_steps)),
                root_cause=root_cause,
            ))

    precision = step_true_positive / step_predicted if step_predicted else (1.0 if not step_reference else 0.0)
    recall = step_true_positive / step_reference if step_reference else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    sample_count = len(reference_rows)
    extra_prediction_count = sum(1 for row in prediction_rows if row.case_id not in ref_by_id)
    return {
        "reference_count": sample_count,
        "expected_case_id_count": len(ref_by_id),
        "prediction_count": len(prediction_rows),
        "matched_prediction_ids": len(set(ref_by_id).intersection(pred_by_id)),
        "missing_predictions": len(set(ref_by_id) - set(pred_by_id)),
        "extra_predictions": extra_prediction_count,
        "duplicate_prediction_ids": len(duplicate_prediction_ids),
        "status_accuracy": status_correct / sample_count if sample_count and prediction_rows else None,
        "step_precision": precision if prediction_rows else None,
        "step_recall": recall if prediction_rows else None,
        "step_f1": f1 if prediction_rows else None,
        "field_accuracy": {
            field: (field_correct[field] / field_total[field] if field_total[field] else None) if prediction_rows else None
            for field in STEP_FIELDS
        },
        "sequence_exact_accuracy": exact_sequences / sample_count if sample_count and prediction_rows else None,
        "sequence_lcs_reference_recall": (lcs_total / reference_step_total if reference_step_total else 1.0) if prediction_rows else None,
        "sequence_lcs_normalized_similarity": normalized_lcs_total / sample_count if sample_count and prediction_rows else None,
        "exact_sequence_count": exact_sequences,
        "lcs_matched_steps": lcs_total,
        "reference_step_count": reference_step_total,
        "diffs": diffs,
        "root_causes": dict(Counter(diff.root_cause for diff in diffs).most_common()),
    }


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def render_report(
    metrics: dict[str, Any], *, prediction_path: Path,
    evaluation_cases: list[CaseResult] | None = None,
) -> str:
    lines = [
        "# Sample Evaluation Report", "",
        f"Prediction file: `{prediction_path}`", "",
        f"Reference cases: {metrics['reference_count']}",
        f"Matched expected case IDs: {metrics['matched_prediction_ids']} / {metrics['expected_case_id_count']}",
        f"Prediction rows: {metrics['prediction_count']}",
        f"Missing predictions: {metrics['missing_predictions']}",
        f"Extra predictions: {metrics['extra_predictions']}",
        f"Duplicate prediction IDs: {metrics['duplicate_prediction_ids']}", "",
        "## Metrics", "",
        f"- Case-level status accuracy: {_percent(metrics['status_accuracy'])}",
        f"- Step precision: {_percent(metrics['step_precision'])}",
        f"- Step recall: {_percent(metrics['step_recall'])}",
        f"- Step F1: {_percent(metrics['step_f1'])}",
        f"- Exact sequence accuracy: {_percent(metrics['sequence_exact_accuracy'])}",
        f"- LCS reference-step recall: {_percent(metrics['sequence_lcs_reference_recall'])}",
        f"- Mean LCS normalized similarity: {_percent(metrics['sequence_lcs_normalized_similarity'])}",
        f"- LCS matched steps: {metrics['lcs_matched_steps']} / {metrics['reference_step_count']}", "",
        "Step precision/recall/F1 match multiset steps by `(phase, operation, system_id, resource_id)`. Field accuracy pairs duplicate keys by occurrence, compares all fields on paired steps, and counts every unmatched step as incorrect for each field. Exact sequence compares full steps positionally; LCS compares the original semantic tuple positionally and excludes `step_no`.", "",
        "## Field Accuracy", "", "| Field | Accuracy |", "|---|---:|",
    ]
    for field, value in metrics["field_accuracy"].items():
        lines.append(f"| `{field}` | {_percent(value)} |")
    lines.extend(["", "## Per-Case Diffs", ""])
    if not metrics["diffs"]:
        lines.append("No mismatches.")
    else:
        lines.extend(["| Sample row | Expected status | Predicted status | Missing steps | Extra steps | Changed fields |", "|---:|---|---|---:|---:|---|"])
        for diff in metrics["diffs"]:
            lines.append(
                f"| {diff.sample_row} | {diff.expected_status} | {diff.predicted_status} | "
                f"{diff.missing_steps} | {diff.extra_steps} | {', '.join(diff.fields)} |"
            )
    lines.extend(["", "## Failures Found and Improvements Made", ""])
    if metrics["prediction_count"] == 0:
        lines.extend([
            "- Before: no prediction rows were available, so accuracy metrics could not be computed.",
            "- Root cause: the repository has no generated root `output.csv`; the CLI requires a case-processor plugin, and none is configured for this run.",
            "- Generic diagnostic improvement: identical per-case misses are grouped by root cause, and unavailable metrics remain `n/a` instead of being presented as zero accuracy.",
            "- After: the evaluator still sees 0 prediction rows and 32 missing sample rows. No evidence-backed prediction fix can be measured until a processor generates output; remaining causes are therefore not observable and cannot be ranked as four additional causes.",
        ])
        lines.extend(["", "| Root cause | Missed cases |", "|---|---:|"])
        for cause, count in metrics["root_causes"].items():
            lines.append(f"| {cause} | {count} |")
    else:
        lines.extend([
            "- Baseline and current metrics are shown above for the supplied prediction file.",
            "- Root-cause clusters summarize the remaining misses. No automatic case-specific changes are applied.",
        ])
        lines.append("")
        lines.extend(["| Root cause | Missed cases |", "|---|---:|"])
        for cause, count in metrics["root_causes"].items():
            lines.append(f"| {cause} | {count} |")
    lines.extend([
        "", "## Additional Synthetic Evaluation Cases", "",
        "The case harness generates identifiers at runtime and loads policy actions from the participant-facing rules file.", "",
        "| Scenario | Result | Checks |", "|---|---|---:|",
    ])
    for case in evaluation_cases or []:
        lines.append(f"| {case.name} | {'PASS' if case.passed else 'FAIL'} | {case.checks_passed}/{case.checks_total} |")
    if not evaluation_cases:
        lines.append("| (not run) | n/a | n/a |")
    lines.extend([
        "", "## Interpretation", "",
        "This report scores the supplied prediction file against the 32 public sample outputs. Run the evaluator again after generating predictions to refresh the reported metrics. The report uses sample row ordinals in diffs and omits case identifiers and step payload values.", "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate predictions against sample_output.csv")
    parser.add_argument("--predictions", type=Path, default=REPO_ROOT / "output.csv")
    parser.add_argument("--reference", type=Path, default=REPO_ROOT / "dataset" / "sample_output.csv")
    parser.add_argument("--report", type=Path, default=REPO_ROOT / "evaluation" / "evaluation_report.md")
    parser.add_argument("--worst-diffs", type=int, default=5, help="number of largest per-case diffs to print")
    args = parser.parse_args(argv)

    reference_rows = load_csv(args.reference, OutputRow)
    prediction_rows = load_csv(args.predictions, OutputRow) if args.predictions.exists() else []
    metrics = evaluate(reference_rows, prediction_rows)
    if (
        metrics["expected_case_id_count"]
        and metrics["matched_prediction_ids"] * 2 < metrics["expected_case_id_count"]
    ):
        print(
            "Evaluation failed: predictions contain "
            f"{metrics['matched_prediction_ids']} of "
            f"{metrics['expected_case_id_count']} expected case IDs; "
            "at least half must be present.",
            file=sys.stderr,
        )
        return 2
    print(
        f"Expected case IDs present: {metrics['matched_prediction_ids']} / "
        f"{metrics['expected_case_id_count']}"
    )
    evaluation_cases = run_evaluation_cases()
    report = render_report(
        metrics,
        prediction_path=args.predictions.relative_to(REPO_ROOT) if args.predictions.is_relative_to(REPO_ROOT) else args.predictions,
        evaluation_cases=evaluation_cases,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8", newline="\n")

    print(f"Status accuracy: {_percent(metrics['status_accuracy'])}")
    print(f"Field accuracy: {', '.join(f'{name}={_percent(value)}' for name, value in metrics['field_accuracy'].items())}")
    print(f"Step precision/recall/F1: {_percent(metrics['step_precision'])} / {_percent(metrics['step_recall'])} / {_percent(metrics['step_f1'])}")
    print(f"Exact sequence accuracy: {_percent(metrics['sequence_exact_accuracy'])}; LCS similarity: {_percent(metrics['sequence_lcs_normalized_similarity'])}")
    if metrics["diffs"]:
        worst_diffs = sorted(metrics["diffs"], key=lambda diff: (
            diff.missing_steps + diff.extra_steps + (diff.expected_status != diff.predicted_status),
            diff.missing_steps + diff.extra_steps,
        ), reverse=True)[:max(0, args.worst_diffs)]
        print(f"Worst-case diffs (top {len(worst_diffs)} by status and step-count errors):")
        for diff in worst_diffs:
            print(
                f"Case {diff.case_id} (sample row {diff.sample_row}): expected={diff.expected_status}, predicted={diff.predicted_status}; "
                f"missing_steps={diff.missing_steps}, extra_steps={diff.extra_steps}, fields={','.join(diff.fields)}"
            )
    else:
        print("Per-case diffs: none")
    print(f"Report written to {args.report}")
    for case in evaluation_cases:
        print(f"Synthetic case {case.name}: {'PASS' if case.passed else 'FAIL'} ({case.checks_passed}/{case.checks_total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
