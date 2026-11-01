# Model usage report

## Current full-dataset run

The current code was run against all 518 requests and wrote the repository-root `output.csv`. The hosted-model API key was absent for this run, so no hosted model or provider was called. Request classification used the deterministic rule-based classifier; OCR, where needed, runs locally through RapidOCR.

| Provider / component | Model | Calls | Input tokens | Output tokens | Total tokens | Estimated cost |
|---|---|---:|---:|---:|---:|---:|
| Hosted classifier / vision provider | None | 0 | 0 | 0 | 0 | $0.00 |
| Local OCR | RapidOCR (local inference/cache) | Local only | N/A | N/A | N/A | $0.00 hosted cost |
| **Overall hosted usage** |  | **0** | **0** | **0** | **0** | **$0.00** |

There were no hosted-model input or output tokens and no provider usage log for this run. Local OCR token usage and hosted-token pricing do not apply.

## Per-request totals

| Requests | Average hosted calls | Average input tokens | Average output tokens | Average total tokens | Average estimated cost |
|---:|---:|---:|---:|---:|---:|
| 518 | 0 | 0 | 0 | 0 | $0.00 |

## Run result

- Output rows: 518
- `COMPLETE`: 75
- `INCOMPLETE`: 441
- `NOT_APPLICABLE`: 2
- Unresolved cases recorded in `.local/unresolved_cases.jsonl`: 52
- Case failures: 0
- No hosted-provider pricing assumptions were needed.
