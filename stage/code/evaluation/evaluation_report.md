# Sample Evaluation Report

Prediction file: `sample_predictions.csv`

Reference cases: 32
Matched expected case IDs: 32 / 32
Prediction rows: 32
Missing predictions: 0
Extra predictions: 0
Duplicate prediction IDs: 0

## Metrics

- Case-level status accuracy: 78.12%
- Step precision: 68.25%
- Step recall: 44.56%
- Step F1: 53.92%
- Exact sequence accuracy: 6.25%
- LCS reference-step recall: 43.01%
- Mean LCS normalized similarity: 33.98%
- LCS matched steps: 83 / 193

Step precision/recall/F1 match multiset steps by `(phase, operation, system_id, resource_id)`. Field accuracy pairs duplicate keys by occurrence, compares all fields on paired steps, and counts every unmatched step as incorrect for each field. Exact sequence compares full steps positionally; LCS compares the original semantic tuple positionally and excludes `step_no`.

## Field Accuracy

| Field | Accuracy |
|---|---:|
| `step_no` | 18.88% |
| `phase` | 36.91% |
| `system_id` | 36.91% |
| `resource_id` | 36.91% |
| `operation` | 36.91% |
| `state` | 36.91% |
| `evidence_id` | 35.62% |

## Per-Case Diffs

| Sample row | Expected status | Predicted status | Missing steps | Extra steps | Changed fields |
|---:|---|---|---:|---:|---|
| 2 | COMPLETE | INCOMPLETE | 1 | 0 | deletion_status, step[1]: missing |
| 3 | COMPLETE | INCOMPLETE | 0 | 1 | deletion_status, step[1]: phase,operation,state, step[2]: phase,system_id,resource_id,operation,state,evidence_id, step[3]: system_id,resource_id,operation,state,evidence_id, step[4]: extra |
| 4 | COMPLETE | INCOMPLETE | 2 | 0 | deletion_status, step[1]: missing, step[2]: missing |
| 5 | INCOMPLETE | INCOMPLETE | 3 | 0 | step[1]: missing, step[2]: missing, step[3]: missing |
| 7 | INCOMPLETE | INCOMPLETE | 4 | 0 | step[1]: missing, step[2]: missing, step[3]: missing, step[4]: missing |
| 8 | INCOMPLETE | INCOMPLETE | 1 | 0 | step[3]: system_id,resource_id, step[4]: missing |
| 9 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[3]: system_id,resource_id,operation,state, step[4]: missing, step[5]: missing |
| 10 | INCOMPLETE | COMPLETE | 2 | 0 | deletion_status, step[1]: phase,system_id,resource_id,operation,state,evidence_id, step[2]: phase,operation,state,evidence_id, step[3]: missing, step[4]: missing |
| 11 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[1]: system_id,resource_id, step[2]: system_id,resource_id,operation, step[3]: operation, step[4]: system_id,resource_id,operation,state, step[5]: system_id,resource_id,operation,state, step[7]: operation,state, step[11]: system_id,resource_id,operation,state, step[12]: system_id,resource_id,operation,state, step[13]: missing, step[14]: missing |
| 12 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[1]: operation, step[2]: operation,state, step[3]: system_id,resource_id,operation,state, step[4]: missing, step[5]: missing |
| 13 | INCOMPLETE | INCOMPLETE | 0 | 1 | step[1]: system_id,resource_id, step[2]: system_id,resource_id, step[3]: phase,system_id,resource_id,operation,state,evidence_id, step[4]: system_id,resource_id, step[5]: phase,system_id,resource_id,operation, step[6]: phase,system_id,resource_id,operation, step[7]: system_id,resource_id, step[8]: system_id,resource_id,operation,state, step[9]: extra |
| 14 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[1]: system_id,resource_id,operation,state, step[2]: system_id,resource_id,operation,state, step[4]: missing, step[5]: missing |
| 15 | INCOMPLETE | NOT_APPLICABLE | 5 | 0 | deletion_status, step[1]: missing, step[2]: missing, step[3]: missing, step[4]: missing, step[5]: missing |
| 16 | INCOMPLETE | INCOMPLETE | 1 | 0 | step[1]: system_id,resource_id, step[2]: system_id,resource_id, step[3]: system_id,resource_id, step[4]: system_id,resource_id, step[5]: system_id,resource_id, step[6]: system_id,resource_id, step[7]: missing |
| 17 | INCOMPLETE | INCOMPLETE | 5 | 0 | step[1]: missing, step[2]: missing, step[3]: missing, step[4]: missing, step[5]: missing |
| 18 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[2]: system_id,resource_id,operation, step[3]: system_id,resource_id, step[7]: operation,state, step[9]: system_id,resource_id, step[10]: system_id,resource_id, step[11]: system_id,resource_id,operation,state, step[12]: system_id,resource_id,operation,state, step[13]: missing, step[14]: missing |
| 19 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[2]: operation, step[4]: operation,state, step[5]: system_id,resource_id, step[6]: system_id,resource_id, step[7]: missing, step[8]: missing |
| 20 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[5]: system_id,resource_id, step[6]: system_id,resource_id,operation,state, step[7]: missing, step[8]: missing |
| 21 | COMPLETE | INCOMPLETE | 3 | 0 | deletion_status, step[1]: missing, step[2]: missing, step[3]: missing |
| 22 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[1]: system_id, step[2]: system_id, step[3]: system_id, step[4]: system_id, step[5]: system_id,resource_id, step[6]: system_id,resource_id,operation,state, step[7]: missing, step[8]: missing |
| 23 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[5]: system_id,resource_id, step[6]: system_id,resource_id, step[7]: missing, step[8]: missing |
| 24 | INCOMPLETE | INCOMPLETE | 4 | 0 | step[1]: system_id,resource_id, step[2]: phase,operation,state,evidence_id, step[3]: phase,system_id,resource_id,operation, step[4]: missing, step[5]: missing, step[6]: missing, step[7]: missing |
| 25 | COMPLETE | INCOMPLETE | 3 | 0 | deletion_status, step[1]: missing, step[2]: missing, step[3]: missing |
| 26 | COMPLETE | COMPLETE | 3 | 0 | step[1]: system_id,resource_id,operation,state, step[2]: system_id,resource_id,operation,state, step[3]: system_id,resource_id,operation,state, step[4]: missing, step[5]: missing, step[6]: missing |
| 27 | COMPLETE | COMPLETE | 3 | 0 | step[1]: system_id,resource_id,operation,state, step[2]: system_id,resource_id,operation,state, step[3]: system_id,resource_id,operation,state, step[4]: missing, step[5]: missing, step[6]: missing |
| 28 | COMPLETE | COMPLETE | 3 | 0 | step[1]: system_id,resource_id,operation,state, step[2]: system_id,resource_id,operation,state, step[3]: system_id,resource_id,operation,state, step[4]: missing, step[5]: missing, step[6]: missing |
| 29 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[9]: system_id,resource_id, step[10]: system_id,resource_id,operation,state, step[11]: system_id,resource_id,operation,state, step[12]: system_id,resource_id,operation,state, step[13]: missing, step[14]: missing |
| 30 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[2]: system_id,resource_id,operation, step[3]: system_id,resource_id, step[7]: operation,state, step[9]: system_id,resource_id, step[10]: system_id,resource_id, step[11]: system_id,resource_id,operation,state, step[12]: system_id,resource_id,operation,state, step[13]: missing, step[14]: missing |
| 31 | COMPLETE | COMPLETE | 2 | 0 | step[1]: system_id,resource_id,operation,state, step[2]: missing, step[3]: missing |
| 32 | INCOMPLETE | INCOMPLETE | 2 | 0 | step[3]: system_id,resource_id,operation,state, step[4]: missing, step[5]: missing |

## Failures Found and Improvements Made

- Baseline and current metrics are shown above for the supplied prediction file.
- Root-cause clusters summarize the remaining misses. No automatic case-specific changes are applied.

| Root cause | Missed cases |
|---|---:|
| step count mismatch | 23 |
| status mismatch | 7 |

## Additional Synthetic Evaluation Cases

The case harness generates identifiers at runtime and loads policy actions from the participant-facing rules file.

| Scenario | Result | Checks |
|---|---|---:|
| reassigned_email | PASS | 3/3 |
| restore_after_audit_cutoff | PASS | 2/2 |
| retained_invoice_with_email | PASS | 3/3 |
| prompt_injection_in_evidence | PASS | 3/3 |

## Interpretation

This report scores the supplied prediction file against the 32 public sample outputs. Run the evaluator again after generating predictions to refresh the reported metrics. The report uses sample row ordinals in diffs and omits case identifiers and step payload values.
