"""Concurrent dataset runner, failure-safe CSV writer, and output validator."""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from .data import DeletionRequest, OutputRow, load_csv
from .planner import validate_steps
from .steps import Step


CaseProcessor = Callable[[DeletionRequest], OutputRow]
OUTPUT_COLUMNS = ("case_id", "deletion_status", "steps_json")
def _safe_fallback(request: DeletionRequest) -> OutputRow:
    # No finding is fabricated when a case could not be analyzed.
    return OutputRow(case_id=request.case_id, deletion_status="INCOMPLETE", steps_json="[]")


def _safe_error_summary(error: Exception) -> str:
    # Arbitrary exception text may echo request content, identifiers, or secrets.
    if isinstance(error, ValidationError):
        return "processor output failed schema validation"
    if isinstance(error, (ValueError, TypeError)):
        return "processor output failed validation"
    return "case processor raised an exception"


def _validate_processed_row(request: DeletionRequest, row: OutputRow) -> None:
    if row.case_id != request.case_id:
        raise ValueError("processor returned an output row for a different request")
    if row.deletion_status not in {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}:
        raise ValueError("processor returned an invalid deletion_status")
    try:
        payload = json.loads(row.steps_json)
    except json.JSONDecodeError as exc:
        raise ValueError("processor returned invalid steps_json") from exc
    if not isinstance(payload, list):
        raise ValueError("steps_json must be a JSON array")
    steps = [Step.model_validate(item) for item in payload]
    validate_steps(row.deletion_status, steps)


def validate_output_file(path: Path, expected_case_ids: set[str]) -> list[OutputRow]:
    """Check schema, row count, case coverage, uniqueness, and JSON syntax."""
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != OUTPUT_COLUMNS:
            raise ValueError(f"output columns must be exactly {OUTPUT_COLUMNS!r}")
        rows = [OutputRow.model_validate(item) for item in reader]
    if len(rows) != len(expected_case_ids):
        raise ValueError(f"expected {len(expected_case_ids)} output rows, found {len(rows)}")
    ids = [row.case_id for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("output contains duplicate case_ids")
    if set(ids) != expected_case_ids:
        raise ValueError("output case_ids do not match the request set")
    for row in rows:
        if row.deletion_status not in {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}:
            raise ValueError(f"invalid deletion_status for output row {row.case_id!r}")
        try:
            payload = json.loads(row.steps_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid steps_json for output row {row.case_id!r}") from exc
        if not isinstance(payload, list):
            raise ValueError(f"steps_json must be an array for output row {row.case_id!r}")
    return rows


def run_cases(
    requests: list[DeletionRequest],
    processor: CaseProcessor,
    *,
    output_path: Path,
    failure_log_path: Path,
    concurrency: int = 8,
) -> tuple[list[OutputRow], list[dict[str, str]]]:
    """Run requests concurrently, isolating each exception into a safe row."""
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    request_ids = [item.case_id for item in requests]
    if len(set(request_ids)) != len(request_ids):
        raise ValueError("input requests contain duplicate case_ids")

    results: dict[str, OutputRow] = {}
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="deletion-case") as pool:
        futures = {pool.submit(processor, item): item for item in requests}
        for future in as_completed(futures):
            request = futures[future]
            try:
                row = future.result()
                if not isinstance(row, OutputRow):
                    row = OutputRow.model_validate(row)
                _validate_processed_row(request, row)
            except Exception as exc:
                row = _safe_fallback(request)
                failures.append({
                    "case_id": request.case_id,
                    "error_type": type(exc).__name__,
                    "error": _safe_error_summary(exc),
                })
            results[request.case_id] = row

    ordered = [results[case_id] for case_id in sorted(results)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=output_path.parent, delete=False) as stream:
        temp_output = Path(stream.name)
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(row.model_dump() for row in ordered)
    temp_output.replace(output_path)

    failure_log_path.parent.mkdir(parents=True, exist_ok=True)
    with failure_log_path.open("w", encoding="utf-8", newline="\n") as stream:
        for failure in sorted(failures, key=lambda item: item["case_id"]):
            stream.write(json.dumps(failure, ensure_ascii=False, sort_keys=True) + "\n")

    validated = validate_output_file(output_path, set(request_ids))
    return validated, failures


def _load_processor(spec: str) -> CaseProcessor:
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("processor must use module.path:callable syntax")
    processor = getattr(importlib.import_module(module_name), attribute)
    if not callable(processor):
        raise TypeError("configured processor is not callable")
    return processor


def _unconfigured_processor(request: DeletionRequest) -> OutputRow:
    raise RuntimeError("no case processor configured; supply --processor module.path:callable")


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Run the deletion audit for every request in the dataset.")
    parser.add_argument("--dataset", type=Path, default=repo_root / "dataset")
    parser.add_argument("--output", type=Path, default=repo_root / "output.csv")
    parser.add_argument("--failures", type=Path, default=repo_root / ".local" / "case_failures.jsonl")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--processor", help="case function as importable module.path:callable")
    args = parser.parse_args(argv)
    try:
        requests = load_csv(args.dataset / "deletion_requests.csv", DeletionRequest)
        if len(requests) != 518:
            raise ValueError(f"expected 518 requests, found {len(requests)}")
        processor = _load_processor(args.processor) if args.processor else _unconfigured_processor
        rows, failures = run_cases(
            requests, processor, output_path=args.output,
            failure_log_path=args.failures, concurrency=args.concurrency,
        )
    except Exception as exc:
        print(f"Run failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"Wrote {len(rows)} output rows to {args.output}; {len(failures)} case failures logged to {args.failures}.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
