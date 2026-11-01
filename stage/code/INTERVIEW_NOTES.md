# Interview notes: Ghost Data Still Exists

## Architecture

The runner loads deletion requests, identity history, policy, activity, and the evidence manifest once. `IdentityIndex` reconstructs current and historical identifier intervals and flags collisions. Evidence parsers normalize text, JSON, PDF, SQL, and OCR output into observations. `CaseStateAnalyzer` links observations to a subject, selects evidence at or before `audit_at`, reconstructs state, and identifies active sync and restore risks. `PolicyEngine` reads treatments from the participant-facing rules CSV. The planner creates deterministically ordered and numbered steps, and the CLI validates and writes the output CSV.

Context linking is evidence-scoped. A resource record may inherit typed identifiers from an enclosing lookup context or a sibling record with an explicit shared trace, request, or correlation key. Each inherited identifier retains its source provenance. Records that merely share a broad export envelope, resource-number pattern, or nearby timestamp are not linked.

## Where is the AI?

The core audit decisions are deterministic and testable: identity resolution, policy treatment, state selection, remediation ordering, and `steps_json` serialization are code-owned. OCR is an ML edge: RapidOCR runs locally for screenshot text, with Tesseract as a local fallback. An optional hosted classifier can handle ambiguous request intent, but it is not allowed to decide policy, state, or output steps. No hosted model was called in the final full-dataset run; the classifier used its deterministic fallback and the OCR path was local.

Evidence and request text are untrusted data, never instructions. Provider credentials, if a hosted optional adapter is selected, come only from environment variables.

## Evaluation snapshot

The final sample run processed all 32 public cases. Aggregate metrics were unchanged from the pre-change baseline: status accuracy 78.12% → 78.12%; step precision/recall/F1 65.98% / 33.16% / 44.14% → 65.98% / 33.16% / 44.14%; exact sequence accuracy 3.12%; mean LCS similarity 28.51%. The context-link change added five resource links on the public samples; all five matched expected resource IDs (5 true positives, 0 false positives). The account lookup JSON records lacked a shared identifier edge, so they were intentionally not linked based on neighboring service records.

The final 518-case output contains 84 `COMPLETE`, 432 `INCOMPLETE`, and 2 `NOT_APPLICABLE` rows. There are 121 unresolved cases. The `COMPLETE` step-count histogram is 65 with one step, 6 with two, 12 with four, and 1 with five. No `COMPLETE` row has an empty step array. These are measured run results, not claims of hidden-golden accuracy.

## Design tradeoffs and limits

1. **Deterministic policy and steps:** This keeps decisions auditable and repeatable, while ambiguous facts can remain unresolved rather than receiving fabricated findings.
2. **Conservative request intent:** Clear multilingual deletion, decline, access, and correction requests are handled by rules. Without a configured provider, ambiguous text follows the conservative fallback; optional provider output remains limited to intent.
3. **Historical identity:** Current and historical identifiers are checked against validity intervals at evidence capture time, with reassignment collisions guarded against.
4. **Point-in-time state:** Only evidence and events available by the inclusive `audit_at` cutoff are considered. Workflow and activity results are claims, not proof.
5. **Coverage limits:** An absence conclusion requires a snapshot that declares coverage of the relevant store. A present or absent record in an incomplete extract cannot establish the whole store's state.
6. **Conservative context edges:** Explicit lookup and correlation references can connect artifacts; broad sibling collections and shared numbering patterns cannot.

## Likely questions

**How do you handle changed or reassigned email addresses?** Build each subject's identity history from audit events into half-open validity intervals. Resolve the request against its submission time and check the evidence identifier against its capture time. If ownership overlaps, do not choose arbitrarily.

**How are remediation steps ordered?** Stop active data flows and block unsafe restores before changing dependent records. Then handle downstream copies before their source when the dependency requires it. Each proposed treatment receives a matching future verification.

**Why did the output retain unresolved cases?** A missing linked resource or incomplete snapshot cannot safely support a fabricated finding or a `COMPLETE` claim. Those cases are recorded in `.local/unresolved_cases.jsonl` for follow-up.

**How was the solution tested?** The full unit suite passes. The sample command evaluates against the public `sample_output.csv` and reports status, step, field, and sequence metrics. The evaluator also runs four additional generated synthetic scenarios.
