# Ghost Data Still Exists

Python implementation scaffold and evaluation tools for the HackerRank Orchestrate deletion audit challenge.

## Setup

Requires Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
# macOS/Linux
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "./code[dev]"
```

The direct runtime and development requirements are pinned in `code/pyproject.toml`, `code/requirements.txt`, and `code/requirements-dev.txt`. There are no provider credentials or hosted-model dependencies required for installation or tests.

## Run

Run unit tests:

```bash
python -m pytest code/tests
```

The CLI accepts 518 requests, processes cases concurrently, validates and sorts output rows, writes a failure log for per-case errors, and validates the output CSV:

```bash
ghost-data-audit --processor ghost_data.process:process_case --concurrency 8
```

The repository includes an end-to-end processor that resolves identities, parses participant-facing evidence, reconstructs state, applies policy, and builds deterministic steps. Inputs are read from `dataset/`; the default output path is repository-root `output.csv`.

An authorized request without an evidence-backed verification is reported as `INCOMPLETE` without fabricated findings and is recorded in `.local/unresolved_cases.jsonl`. A `COMPLETE` output always includes at least one cited verification step. Each run overwrites its output and failure log; clear `.local/unresolved_cases.jsonl` before a fresh full run if you need a run-specific unresolved count.

## Evaluate

To run and evaluate the public samples in one command:

```bash
python scripts/eval_samples.py
```

This writes `sample_predictions.csv` and refreshes `evaluation/sample_evaluation_report.md`. To evaluate an existing sample prediction file directly:

```bash
python evaluation/run_eval.py --predictions sample_predictions.csv
```

The evaluator compares against `dataset/sample_output.csv`, prints mismatches, and exits with an error unless predictions contain at least half of the expected sample case IDs. Four generated synthetic scenarios live in `evaluation/cases/` and are also run by the evaluator.

## Architecture

- `code/src/ghost_data/data.py` defines typed CSV models and timezone-aware loaders.
- `identity.py` resolves current and historical identifiers and flags reassignment collisions.
- `observations.py` extracts normalized observations from evidence files and builds resource indexes. It preserves provenance for identifiers inherited through an enclosing lookup context or records sharing an explicit trace/request/correlation ID. Sibling records without an explicit shared context are not joined. Text, JSON, PDF and SQL are supported directly; screenshots use the configured OCR reader.
- `state.py` selects observations at or before `audit_at`, applies later in-window activity claims, identifies recreation and restore risks, and records contradictions. A unique `account_service` `DELETE_RECORD` within 60 seconds of `reported_at` is also a narrow account-link fallback when no account observation is already subject-linked; the activity is not accepted as state proof, which must come from the governing snapshot.
- `policy.py` loads `deletion_rules.csv` and evaluates category conditions.
- `planner.py` builds ordered finding, remediation and verification steps and validates the output contract.
- `request_classifier.py` applies deterministic multilingual rules first and can call a pluggable cached provider for ambiguous text. Provider output is restricted to request intent; deterministic code owns policy and output steps. Without `GHOST_DATA_API_KEY`, the classifier uses its conservative fallback and makes no hosted call.
- `cli.py` provides concurrent execution, per-case error isolation, CSV serialization and output validation.

## Design decisions

- Evidence, request text and activity details are untrusted content, never instructions.
- Timestamps are normalized to UTC; the `audit_at` cutoff is inclusive.
- Workflow status and activity result fields are claims. Current state comes from linked observations and temporal activity reconstruction.
- Policy actions are read from the participant-facing policy CSV. Retained records and tombstones are treated according to their specific rules.
- Provider integration is behind a protocol; credentials belong in environment variables. The cache is content-addressed and the token logger records usage without prompt content.
- Deterministic code sorts and numbers all steps, and emits safe fallback rows rather than fabricating evidence when processing fails.

## Limits

- OCR defaults to local RapidOCR followed by local Tesseract when no hosted OCR key is configured. Hosted vision OCR is optional and requires environment configuration.
- Heterogeneous evidence linking remains conservative: inherited identifiers require a scoped lookup context or explicit correlation edge. Incomplete snapshot scope weakens absence claims.
- [`code/evaluation/usage_report.md`](./code/evaluation/usage_report.md) records hosted calls separately from local OCR inference.
- Snapshot absence is only as strong as the declared/extracted coverage of that snapshot. Some supplied artifacts may not establish complete store coverage.

## Package

The submission archive is `code.zip`. It contains `code/` source, tests, prompts, pinned dependency files, and evaluation reports. It excludes the dataset, virtual environments, caches, build output, and nested archives.
