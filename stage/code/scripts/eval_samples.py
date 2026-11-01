"""Run the sample deletion requests and evaluate the generated predictions."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code" / "src"))
sys.path.insert(0, str(REPO_ROOT / "evaluation"))

from ghost_data.cli import main as run_cli  # noqa: E402
from run_eval import main as evaluate_cli  # noqa: E402


def main() -> int:
    sample_predictions = REPO_ROOT / "sample_predictions.csv"
    run_result = run_cli([
        "--input", str(REPO_ROOT / "dataset" / "sample_deletion_requests.csv"),
        "--output", str(sample_predictions),
        "--failures", str(REPO_ROOT / ".local" / "sample_case_failures.jsonl"),
        "--processor", "ghost_data.process:process_case",
    ])
    if run_result:
        return run_result
    return evaluate_cli([
        "--predictions", str(sample_predictions),
        "--reference", str(REPO_ROOT / "dataset" / "sample_output.csv"),
        "--report", str(REPO_ROOT / "evaluation" / "sample_evaluation_report.md"),
    ])


if __name__ == "__main__":
    raise SystemExit(main())
