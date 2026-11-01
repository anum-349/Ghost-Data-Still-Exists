# Ghost Data Still Exists implementation

Requires Python 3.11 or newer. From this directory:

```bash
python -m venv .venv
# Activate .venv using your platform's activation command.
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e .
python -m pytest
```

The application dependency and test runner are pinned in `requirements.txt`, `requirements-dev.txt`, and `pyproject.toml`. Build tooling is pinned in the `pyproject.toml` build-system section.

## Running the CLI

From the repository root after installing the package:

```bash
ghost-data-audit --processor your_package.audit:process_case --concurrency 8
```

The processor accepts a typed `DeletionRequest` and returns an `OutputRow`. The CLI runs all requests with a concurrency limit, writes sorted and quoted `output.csv`, validates row count/IDs/JSON, and isolates per-case failures to `.local/case_failures.jsonl` with safe `INCOMPLETE` fallback rows.

There is no production end-to-end processor configured in this package yet. The command-line installation and unit tests are runnable from a clean clone; generating evidence-backed challenge predictions requires an application-supplied processor. Without one, the CLI will write fallback rows and exit nonzero; do not submit those as predictions.

## Evaluation

From the repository root, run `python code/evaluation/run_eval.py --predictions output.csv`. The evaluator uses the public sample set and generated synthetic cases and writes `code/evaluation/evaluation_report.md`.

## Components and decisions

The package separates typed input loading, historical identity resolution, evidence parsing, point-in-time state reconstruction, policy evaluation, deterministic step planning, provider-backed intent classification, and CLI serialization. Evidence/request text is untrusted. Model output may classify intent only; deterministic code applies policy and constructs the steps. All timestamps are timezone-aware UTC and use an inclusive audit cutoff. Activity outcomes and workflow statuses are claims, not proof of state.

The policy engine loads `deletion_rules.csv`. Evidence parsing supports text, JSON, PDF and SQLite-compatible SQL exports; image parsing requires an injected OCR reader. Model integrations implement the vendor-neutral provider protocol and read any needed credentials from environment variables. The usage report does not currently contain totals because this checkout has no verified full-dataset prediction run and no attributable provider usage log.

See the repository-level `README.md` for setup, architecture, design decisions, limitations, evaluation instructions, and packaging notes.
# OCR and optional model configuration

PNG evidence is read once during index construction. The default OCR chain is API vision (when `GHOST_DATA_API_KEY` is set), RapidOCR, then Tesseract. Set `GHOST_DATA_OCR_BACKEND` to `auto`, `api`, `rapidocr`, or `tesseract` to choose the starting backend. Configure API settings with `GHOST_DATA_API_BASE` and `GHOST_DATA_VISION_MODEL`, or point `GHOST_DATA_TESSERACT` to a local executable. OCR text is cached by image content under `GHOST_DATA_OCR_CACHE` (default `.local/ocr_cache`) and dumped for review to `.local/ocr_dump.txt`. Unreadable evidence is logged with its `file_id` to `.local/evidence_errors.jsonl`, and ingestion continues. Per-case exceptions are logged separately with type, redacted message, and traceback summary. Ambiguous request classification uses the optional API key and `GHOST_DATA_CLASSIFIER_MODEL`; actual model token counts are appended to `GHOST_DATA_TOKEN_LOG` (default `.local/token_usage.jsonl`). Credentials are only read from the environment.
