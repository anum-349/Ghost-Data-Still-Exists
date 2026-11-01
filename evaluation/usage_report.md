# Model usage report

## Final full-dataset run status

No verifiable full-dataset run producing the submission `output.csv` is present in this checkout, so token counts and costs cannot be aggregated for such a run.

- Expected input: `dataset/deletion_requests.csv` (518 requests).
- Submission output: root `output.csv` is absent. `dataset/output.csv` is the header-only template (0 data rows), not a run output.
- Usage log: no provider usage JSONL was found in the configured/local run artifacts. The application logger writes one JSONL row per provider response with provider, model, input/output tokens, and cache-hit status.
- Run configuration: the CLI accepts a `--processor module.path:callable`; no processor is configured by default. Its default execution would emit safe `INCOMPLETE` fallbacks for all cases and exit with failures, which would not establish a valid final prediction run.

## Usage and cost totals

| Provider | Model | Provider calls | Input tokens | Output tokens | Total tokens | Estimated cost |
|---|---|---:|---:|---:|---:|---:|
| Not verifiable | Not verifiable | n/a | n/a | n/a | n/a | n/a |
| **Overall** |  | **n/a** | **n/a** | **n/a** | **n/a** | **n/a** |

Per-request token and cost averages are also **n/a**: there is no verified completed run or usage log to aggregate, and no valid request denominator tied to an output artifact. No pricing assumptions are applied.

## Verification required to complete this report

After configuring and running the case processor for all 518 requests, preserve the generated usage JSONL alongside the run and verify that its run identifier/time window corresponds to the same invocation that wrote root `output.csv`. Then aggregate provider/model call counts and token totals from those records, calculate averages across 518 requests, and estimate cost using documented rates for the exact model versions used. The current usage log schema does not record a run ID or output checksum, so future runs should also record these (or preserve an external run manifest) to establish an auditable output-to-usage link.
