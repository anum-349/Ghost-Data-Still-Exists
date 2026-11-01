# DATA_NOTES

Read-only inventory of the participant-facing files under `dataset/`. CSV sample values are the first five records in file order; values in `case_id`, `email`, answer fields, and embedded email-like strings are redacted to honor the repository hard rules. The blank output template has headers but no data rows. No dataset files were modified.

## `deletion_requests.csv`

- Data rows: 518
- Schema (7 columns): `case_id, email, requested_at, reported_status, reported_at, audit_at, request_text`
- Sample rows (up to five, in source order; sensitive identifier/answer values redacted):

```json
{"case_id": "[REDACTED]", "email": "[REDACTED]", "requested_at": "2026-07-16T08:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-07-18T02:00:00Z", "audit_at": "2026-07-19T13:00:00Z", "request_text": "Please close my account and process the associated personal-data deletion. Please handle any copies that fall within the scope of the deletion request. Please confirm when the review is complete."}
{"case_id": "[REDACTED]", "email": "[REDACTED]", "requested_at": "2026-09-24T08:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-26T02:00:00Z", "audit_at": "2026-09-27T13:00:00Z", "request_text": "I would like the account associated with this address to be erased. Please handle any copies that fall within the scope of the deletion request. Please contact me if you need information to verify the request."}
{"case_id": "[REDACTED]", "email": "[REDACTED]", "requested_at": "2026-08-30T03:00:00Z", "reported_status": "NOT_STARTED", "reported_at": "2026-08-31T21:00:00Z", "audit_at": "2026-09-02T08:00:00Z", "request_text": "Please close my account and process the associated personal-data deletion. Please check the records connected to the account before confirming completion. Please contact me if you need information to verify the request."}
{"case_id": "[REDACTED]", "email": "[REDACTED]", "requested_at": "2026-09-07T12:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-09T12:00:00Z", "audit_at": "2026-10-01T12:00:00Z", "request_text": "Please close my account and process the associated personal-data deletion. Please review the account data that is eligible for deletion or de-identification. Please send a confirmation after the process finishes."}
{"case_id": "[REDACTED]", "email": "[REDACTED]", "requested_at": "2026-09-06T12:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-09T12:00:00Z", "audit_at": "2026-10-01T12:00:00Z", "request_text": "I want to close this account and have its associated personal data deleted. Please apply the request across the systems covered by your deletion policy. Please let me know once the request has been reviewed."}
```

## `deletion_rules.csv`

- Data rows: 15
- Schema (4 columns): `rule_id, data_category, condition, required_action`
- Sample rows (up to five, in source order; sensitive identifier/answer values redacted):

```json
{"rule_id": "rule_01", "data_category": "USER_PROFILE", "condition": "Always", "required_action": "DELETE"}
{"rule_id": "rule_02", "data_category": "SECONDARY_IDENTIFIER", "condition": "Always", "required_action": "DELETE"}
{"rule_id": "rule_03", "data_category": "SEARCH_INDEX_ENTRY", "condition": "Always", "required_action": "DELETE"}
{"rule_id": "rule_04", "data_category": "CACHE_ENTRY", "condition": "Always", "required_action": "DELETE"}
{"rule_id": "rule_05", "data_category": "SUPPORT_MESSAGE", "condition": "Conversation contains shared customer, agent, or order context that must be retained", "required_action": "REDACT"}
```

## `evidence_files.csv`

- Data rows: 94
- Schema (4 columns): `file_id, file_path, origin, captured_at`
- Sample rows (up to five, in source order; sensitive identifier/answer values redacted):

```json
{"file_id": "evidence_01", "file_path": "evidence/logs/service_events_ap_south_20260915.log", "origin": "central_observability_export", "captured_at": "2026-09-15T11:59:39Z"}
{"file_id": "evidence_02", "file_path": "evidence/records/customer_data_snapshot_bundle_20260917.json", "origin": "records_assurance_snapshot_bundle", "captured_at": "2026-09-17T12:00:00Z"}
{"file_id": "evidence_03", "file_path": "evidence/records/customer_account_handover_20261001.txt", "origin": "customer_account_service", "captured_at": "2026-10-01T12:00:00Z"}
{"file_id": "evidence_04", "file_path": "evidence/images/account_admin_console_20260926.png", "origin": "account_admin_portal", "captured_at": "2026-09-26T11:00:00Z"}
{"file_id": "evidence_05", "file_path": "evidence/databases/customer_data_read_replica_20260921.sql", "origin": "customer_data_read_replica_capture", "captured_at": "2026-09-21T10:00:00Z"}
```

## `output.csv`

- Data rows: 0
- Schema (3 columns): `case_id, deletion_status, steps_json`
- Sample rows (up to five, in source order; sensitive identifier/answer values redacted):

```text
(No data rows; header only.)
```

## Relationships and join keys

- `deletion_requests.email` can join to `user_identities.email` for the current snapshot. It can also match a historical email represented by `user_audit_log` rows whose `field_name` is `email`; use `user_id` to resolve that audit history back to `user_identities.user_id`.
- `user_identities.user_id` is the stable subject key to `user_audit_log.user_id`. Audit records are changes (`old_value` → `new_value`) at `event_time`; their values should be interpreted in temporal order.
- `sample_deletion_requests.case_id` joins to `sample_output.case_id`. The corresponding evaluation files share the same request/output shape, but the supplied evaluation `output.csv` is only a blank template.
- `evidence_files.file_id` identifies a manifest row, and `file_path` locates the artifact beneath `dataset/`. There is no case/user foreign key in the manifest. `system_activity.resource_id` and resource identifiers embedded in evidence can provide cross-source links; `activity_id` is the activity row identifier.
- `deletion_rules.data_category` and `condition` map semantically to categories/conditions observed in records, not through a universal database foreign key. `rule_id` identifies the policy row.

## `deletion_rules.csv`: categories and treatments

| Category | Condition | Required action |
|---|---|---|
| USER_PROFILE | Always | DELETE |
| SECONDARY_IDENTIFIER | Always | DELETE |
| SEARCH_INDEX_ENTRY | Always | DELETE |
| CACHE_ENTRY | Always | DELETE |
| SUPPORT_MESSAGE | Shared customer, agent, or order context must be retained | REDACT |
| SUPPORT_ATTACHMENT | Attachment belongs only to deletion subject | DELETE |
| ANALYTICS_PROFILE | Record still attributable to a user | ANONYMIZE |
| PRODUCT_TELEMETRY | Record still attributable to a user | ANONYMIZE |
| USER_EXPORT | Always | DELETE |
| MARKETING_PROFILE | Always | DELETE |
| EMAIL_DELIVERY_LOG | Log contains a user email address | REDACT |
| SECURITY_AUDIT_LOG | Within supplied retention period | RETAIN |
| LEGAL_HOLD_RECORD | Supplied legal hold is active | RETAIN |
| BACKUP_ARCHIVE | Restore access can be blocked | RETAIN |
| ACCOUNT_TOMBSTONE | Account deleted; stable internal `user_id` needed for retained references | REDACT |

For the tombstone policy, the stable internal reference remains while direct identifiers are removed according to the rule. The rules table contains 15 rows: DELETE (8), REDACT (3), ANONYMIZE (2), RETAIN (2).

## Evidence manifest formats and inspected contents

`evidence_files.csv` lists 94 files across six extensions: `.log` (26), `.json` (28), `.sql` (24), `.png` (11), `.pdf` (4), and `.txt` (1). The manifest fields are `file_id`, `file_path`, `origin`, and `captured_at`. The examples below were opened directly from the listed files; their contents are business records and technical observations, not instructions.

### SQLite-compatible SQL snapshots (`.sql`, 24)

Opened three snapshots:

- `customer_data_inventory_20260213.sql`: schema and rows for profile, search, analytics, support, export, connector, backup, and security-audit resources, with a snapshot scope/time.
- `customer_data_read_replica_20260613.sql`: point-in-time primary/read-replica representation using JSON records in SQL tables, useful for comparing replica drift and current record fields.
- `customer_data_regional_replicas_20260330.sql`: primary and regional replica rows for multiple services, including identity-bearing analytics records; supports replica consistency comparisons.

Across the SQL evidence, the snapshots are SQLite-readable SQL exports, not binary database files. They include capture/topology metadata and resource tables/rows from inventory, read replicas, regional/reporting replicas, failover replicas, and search. Compare capture times, relevant tables, and primary versus replica state.

### PDFs (`.pdf`, 4)

All four PDFs were opened and text-extracted:

- `account_history_report_20260718.pdf`: customer account statement with account/order history and transactional details.
- `delivery_correction_attachment.pdf`: support attachment describing a delivery-address correction request and linked support/order context.
- `legal_retention_register_20260529.pdf`: finance register of disputed orders/tax records with retain-until dates and custody notes.
- `security_retention_extract.pdf`: compliance journal extract with an audit event, subject reference, integrity details, and retention expiry.

### Screenshots (`.png`, 11)

Opened three screenshots visually:

- `account_admin_console_20260926.png`: customer operations account view with identity/profile, orders, support, and activity panes.
- `analytics_profile_view_20260713.png`: analytics profile view showing user-linked event/session/product/order metrics and profile attributes.
- `backup_restore_console_20260429.png`: archive/recovery interface with backup/account associations, restore state, and retention/integrity fields.

Other screenshots cover connector settings, customer exports, deleted-account references, marketing profiles, object storage, search-index records, security audit views, and support tickets.

### Logs (`.log`, 26)

Opened three logs:

- `service_events_ap_south_20260915.log`: mixed service observability events, including search-index lookups, retries, support lookups, and operational noise.
- `structured_service_events_eu_west_20260918.log`: JSON-structured service events embedded line-by-line, including account/search reads and result/resource details.
- `resource_lookup_trace_20260218_083911.log`: point-in-time cross-service readbacks for connectors, analytics, exports, search, accounts, and support; exposes field-level states and lookup keys.

The other logs include service/operation streams, application traces, syslog archives, delivery events, readback traces, support replica output, and search diagnostics. Logs may contain claims about operations; compare these with state snapshots and apply each case's `audit_at` cutoff.

### JSON records (`.json`, 28)

Opened three JSON files:

- `customer_data_snapshot_bundle_20260917.json`: timestamped snapshots grouped by store and collection, with nested records for profiles, search documents, analytics, and other data stores.
- `connector_configurations_20260812.json`: integration-management export listing resource types, systems, identifiers, lookup outcomes, and connector configuration records.
- `customer_analytics_report_20260907.json`: captured analytics report containing resource IDs, user linkage/identifiers, metrics, and recent activity.

Other JSON records include recurring snapshot bundles, service-resource exports, export jobs/manifests, connector configurations, and security-audit ledgers.

### Plain text (`.txt`, 1)

The only `.txt` artifact, `customer_account_handover_20261001.txt`, was opened. It is a shift-handover snapshot with timestamped account and downstream-service readbacks, resource/category names, states such as found/not-found, anonymized/identifiable, active/blocked/disabled, and related references. Only one `.txt` exists in the manifest, so three samples for this extension are unavailable.

## Value distributions

### `deletion_requests.csv.reported_status` (518 rows)

| Value | Count |
|---|---:|
| COMPLETE | 254 |
| PARTIALLY_COMPLETE | 152 |
| NOT_STARTED | 112 |

### `system_activity.csv.event_type` (4,011 rows)

| Event type | Count |
|---|---:|
| DELETE_RECORD | 890 |
| UPDATE_RECORD | 672 |
| SYNC_RECORD | 447 |
| SEND_EMAIL | 368 |
| REFRESH_CACHE | 284 |
| RETAIN_RECORD | 206 |
| ANONYMIZE_RECORD | 204 |
| CREATE_EXPORT | 155 |
| CHECK_DATA_FLOW | 89 |
| DISABLE_DATA_FLOW | 36 |
| BLOCK_RESTORE | 36 |
| CHECK_RESTORE_ACCESS | 28 |
| LINK_RESOURCE_IDENTITY | 12 |
| CLASSIFY_REQUEST | 10 |
| RESTORE_BACKUP | 1 |
| INDEX_RECORD | 400 |
| REDACT_RECORD | 173 |

`system_activity.csv` calls this field `event_type` (there is no `operation` column). Its `reported_result` distribution is SUCCESS 2,914; FAILED 721; PARTIAL 376. These are activity claims rather than standalone proof of resulting state.

## Conventions

### Evidence and step construction

- In the sample outputs, `evidence_id` on an observed finding or a `COMPLETE` verification is the manifest `file_id` that points to the inspected artifact. The underlying record/readback must match the subject through current or historical identifiers, stable reference, resource ID, or another grounded link; the manifest alone does not establish a match.
- For `INCOMPLETE` outputs, finding steps cite the evidence for the current violation. Remediation and post-remediation verification are planned work, so their `evidence_id` is the empty string. Their target/action comes from the finding and the matching `deletion_rules.csv` category/condition.
- All 32 public sample requests are deletion requests. `sample_output.csv` is positionally aligned with `sample_deletion_requests.csv`; row *n* in one is matched to row *n* in the other by `case_id` (the identifier values are intentionally omitted here). Request email resolves either to a current identity row or an email-change audit row as listed in the trace below.

### Tombstones, retention, flows, restore, and ordering

- An account tombstone is not deleted wholesale: keep the stable internal subject reference so retained records remain linkable, but remove direct identifiers covered by the redaction policy. The public sample's already compliant tombstone has null name/email/phone/email hash and remains present; the noncompliant tombstone is reported as exposed PII and gets a planned redaction. The stable reference itself is permitted by the tombstone rule.
- Policy-retained security/audit records appear as `VERIFY_RECORD_PRESENT` in both complete-state evidence and incomplete-case future verification. They are intentionally preserved, not treated as deletion failures. Other actions such as redaction, anonymization, or retention are represented by their corresponding verification operation/state.
- Restore risks are identified from backup inventory/readback evidence indicating restore is allowed, a deletion block is absent, or a handover reports an active backup. The plan blocks restore before dependent record cleanup; future verification checks that restore is blocked.
- Data flows are identified from connector evidence such as `enabled=true`, registered scheduling, or a handover state of `ACTIVE`. The plan disables an active flow before changing records it could recreate, then verifies the flow is disabled.
- Every output uses phase order `FINDING`, `REMEDIATION`, `VERIFICATION`. Within findings, the samples group remaining-record findings before exposed-PII findings and active-flow/restore findings. In remediation, disabling flows/blocking restores precedes record treatment; the downstream record treatments then follow their policy operations. Verification follows the check-operation families (absence, retention/presence, redaction, anonymization, flow, restore). Resource/system order breaks ties in the examples. The sample does not fully specify a universal tie-breaker for every same-operation pair; see open ambiguities below.

### Case-by-case sample trace

Each line identifies the request row and matching output row by their shared ordinal, the identity-history row(s) used to resolve the request, then the evidence for each numbered step or step range. No case identifiers, email addresses, or output answer payloads are reproduced. For planned steps, the range has empty `evidence_id` by contract and follows the cited finding plus policy.

| Sample row in both CSVs | Identity lookup source | Step-to-evidence trace |
|---:|---|---|
| 1 | `user_identities.csv` data row 1 | Step 1 cites `evidence_54` (failover SQL snapshot; no matching profile in the captured profile rows). |
| 2 | `user_identities.csv` data row 2 | Step 1 cites `evidence_54` (same point-in-time failover/profile snapshot). The workflow claim differs from the independently checked state. |
| 3 | `user_identities.csv` data row 43 | Steps 1–3 each cite `evidence_94` (readback log entries for account, security audit, and analytics resources). |
| 4 | `user_identities.csv` data row 4 | Step 1 cites `evidence_54`; step 2 cites `evidence_56` (analytics record with direct identifiers cleared). |
| 5 | `user_identities.csv` data row 5 | Finding step 1 cites `evidence_54` (matching active profile in failover snapshot); planned steps 2–3 have empty evidence IDs. |
| 6 | `user_identities.csv` data row 6 | Finding step 1 cites `evidence_57` (search-primary SQL row); planned steps 2–4 have empty evidence IDs. |
| 7 | `user_identities.csv` data row 7 | Finding step 1 cites `evidence_58` (PDF support attachment); planned steps 2–4 have empty evidence IDs. |
| 8 | `user_identities.csv` data row 8 | Finding step 1 cites `evidence_59` (export-job JSON record with an available download); planned steps 2–4 have empty evidence IDs. |
| 9 | `user_identities.csv` data row 61 | Finding step 1 cites `evidence_93` (inventory SQL backup row showing restore access); planned steps 2–5 have empty evidence IDs. |
| 10 | `user_audit_log.csv` data row 121; no current-email match in identity snapshot | Finding step 1 cites `evidence_61` (support-replica readback and deletion-marker check); planned steps 2–4 have empty evidence IDs. |
| 11 | `user_identities.csv` data row 32 | Finding steps 1–4 each cite `evidence_03` (handover rows for search, analytics, support, and connector resources); planned steps 5–14 have empty evidence IDs. |
| 12 | `user_identities.csv` data row 12 and `user_audit_log.csv` data row 282 | Finding step 1 cites `evidence_01` (log readback for an analytics resource); planned steps 2–5 have empty evidence IDs. |
| 13 | `user_identities.csv` data row 33 | Finding steps 1–2 cite `evidence_03` (handover rows for search and support); planned steps 3–8 have empty evidence IDs. |
| 14 | `user_identities.csv` data row 37 | Finding step 1 cites `evidence_03` (active backup handover row); planned steps 2–5 have empty evidence IDs. |
| 15 | `user_identities.csv` data row 15 | Finding step 1 cites `evidence_01` (connector heartbeat reports enabled/scheduled); planned steps 2–5 have empty evidence IDs. |
| 16 | `user_identities.csv` data row 53 | Finding steps 1–2 cite `evidence_05` (read-replica SQL rows for account and search); planned steps 3–7 have empty evidence IDs. |
| 17 | `user_identities.csv` data row 17 | Finding step 1 cites `evidence_01` (backup restore-candidate event with no deletion block); planned steps 2–5 have empty evidence IDs. |
| 18 | `user_identities.csv` data row 50 | Finding steps 1–4 cite `evidence_94` (search hit, analytics identifiers, support identifiers, and enabled connector readbacks); planned steps 5–14 have empty evidence IDs. |
| 19 | `user_identities.csv` data row 19 | Finding steps 1–2 cite `evidence_01` (search hit and support PII scan); planned steps 3–8 have empty evidence IDs. |
| 20 | `user_identities.csv` data row 48 | Finding steps 1–2 cite `evidence_94` (search hit and enabled connector readback); planned steps 3–8 have empty evidence IDs. |
| 21 | `user_identities.csv` data row 21 | Steps 1–3 each cite `evidence_92` (service-resource export readbacks for account, audit, and analytics). |
| 22 | `user_identities.csv` data row 51 | Finding steps 1–2 cite `evidence_05` (read-replica search and analytics rows); planned steps 3–8 have empty evidence IDs. |
| 23 | `user_identities.csv` data row 23 | Finding steps 1–2 cite `evidence_92` (export and search readbacks); planned steps 3–8 have empty evidence IDs. |
| 24 | `user_identities.csv` data row 24 | Finding steps 1–2 cite `evidence_92` (account and search readbacks); planned steps 3–7 have empty evidence IDs. |
| 25 | `user_identities.csv` data row 25 | Steps 1–3 each cite `evidence_92` (account, retained audit, and analytics readbacks). The reported workflow claim is not used as state proof. |
| 26 | `user_identities.csv` data row 26 | Steps 1–6 each cite `evidence_92` (account, audit, support, analytics, connector, and backup readbacks). |
| 27 | `user_identities.csv` data row 27 | Steps 1–6 each cite `evidence_92` (account, audit, support, analytics, connector, and backup readbacks). |
| 28 | `user_identities.csv` data row 28 | Steps 1–6 each cite `evidence_92` (account, audit, support, analytics, connector, and backup readbacks). |
| 29 | `user_audit_log.csv` data row 284; no current-email match in identity snapshot | Finding steps 1–4 cite `evidence_92` (search, analytics, support, and connector readbacks); planned steps 5–14 have empty evidence IDs. |
| 30 | `user_audit_log.csv` data row 280; no current-email match in identity snapshot | Finding steps 1–4 cite `evidence_92` (search, analytics, support, and connector readbacks); planned steps 5–14 have empty evidence IDs. |
| 31 | `user_identities.csv` data row 541 | Steps 1–3 each cite `evidence_51` (snapshot bundle entries for account, retained audit, and the compliant tombstone). Capture time equals the audit cutoff. |
| 32 | `user_identities.csv` data row 542 | Finding step 1 cites `evidence_51` (snapshot bundle contains a deleted-account tombstone with direct identifiers still populated); planned steps 2–5 have empty evidence IDs. |

### Assumptions checked and open ambiguities

- No substantive contradiction with the policy/output contract appeared in the 32 examples. The examples demonstrate why `reported_status` is only a claim: a partially complete report can have a complete evidence-backed state, and a `NOT_STARTED` report can coexist with a complete state at audit time.
- Sample row 7 contains a narrower factual mismatch: the request calls the support item an identity document, but the cited PDF is a delivery-address correction attachment. The underlying attachment still contains subject-linked support data covered by the attachment-deletion rule, so the mismatch does not change the treatment; it does show that request wording should not be treated as proof of the artifact's contents.
- Terminology mismatch: the requested distribution of “system activity operations” is represented by the `event_type` column in `system_activity.csv`; there is no column literally named `operation`.
- The sample treats a missing subject row in a point-in-time database snapshot as evidence of absence. The SQL schema identifies topology and capture time, but some files do not explicitly declare that every relevant resource was included. For unseen datasets, snapshot completeness/scope is an open question before treating nonappearance as proof.
- The problem contract fixes phase order and the required treatment operations, but does not state a fully formal tie-breaker for multiple findings or checks with the same operation/resource dependency. The samples are consistent with operation-family ordering and deterministic resource/system ordering, but code should make any tie-break explicit and stable.
- The contract says use evidence available at or before `audit_at`; sample row 31 has evidence captured at exactly the cutoff and treats it as eligible. This implies an inclusive cutoff. If timestamp precision or same-time event ordering matters, the inputs do not provide an additional tie-break rule.
- The inventory may show one evidence source for an observed violation while the sample's future verification includes other dependent resources. The public examples do not always explain the full dependency graph; the plan is inferred from policy and the subject-linked evidence set.

## `sample_deletion_requests.csv`

- Data rows: 32
- Schema (7 columns): `case_id, email, requested_at, reported_status, reported_at, audit_at, request_text`
- Sample rows (up to five, in source order; sensitive identifier/answer values redacted):

```json
{"case_id": "[REDACTED]", "email": "[REDACTED]", "requested_at": "2026-08-18T09:14:00Z", "reported_status": "COMPLETE", "reported_at": "2026-08-20T16:42:00Z", "audit_at": "2026-09-03T11:30:00Z", "request_text": "Hi, I haven’t used this account in years and would like it closed. Please remove the profile and the personal details attached to it."}
{"case_id": "[REDACTED]", "email": "[REDACTED]", "requested_at": "2026-08-21T18:06:00Z", "reported_status": "PARTIALLY_COMPLETE", "reported_at": "2026-08-22T07:25:00Z", "audit_at": "2026-09-04T15:00:00Z", "request_text": "Intenté eliminar mi cuenta ayer, pero la página terminó mostrando un error. ¿Pueden comprobar si todavía queda algún dato y completar la eliminación si hace falta?"}
{"case_id": "[REDACTED]", "email": "[REDACTED]", "requested_at": "2026-09-13T11:00:00Z", "reported_status": "COMPLETE", "reported_at": "2026-09-15T11:00:00Z", "audit_at": "2026-09-26T11:00:00Z", "request_text": "Je demande la suppression définitive du compte associé à cette adresse e-mail. Veuillez examiner les identifiants actuels et antérieurs conformément à votre procédure de confidentialité. Merci de confirmer le résultat une fois la vérification terminée."}
{"case_id": "[REDACTED]", "email": "[REDACTED]", "requested_at": "2026-08-25T12:32:00Z", "reported_status": "COMPLETE", "reported_at": "2026-08-27T08:54:00Z", "audit_at": "2026-09-07T10:20:00Z", "request_text": "I’m deleting my account. You can keep anonymous statistics, but nothing in analytics should still point back to me."}
{"case_id": "[REDACTED]", "email": "[REDACTED]", "requested_at": "2026-08-27T14:17:00Z", "reported_status": "COMPLETE", "reported_at": "2026-08-28T09:03:00Z", "audit_at": "2026-09-08T13:40:00Z", "request_text": "I deleted this account and received a confirmation, but the same email address is still recognized. Please remove any remaining copy of my profile."}
```

## `sample_output.csv`

- Data rows: 32
- Schema (3 columns): `case_id, deletion_status, steps_json`
- Sample rows (up to five, in source order; sensitive identifier/answer values redacted):

```json
{"case_id": "[REDACTED]", "deletion_status": "[REDACTED]", "steps_json": "[REDACTED]"}
{"case_id": "[REDACTED]", "deletion_status": "[REDACTED]", "steps_json": "[REDACTED]"}
{"case_id": "[REDACTED]", "deletion_status": "[REDACTED]", "steps_json": "[REDACTED]"}
{"case_id": "[REDACTED]", "deletion_status": "[REDACTED]", "steps_json": "[REDACTED]"}
{"case_id": "[REDACTED]", "deletion_status": "[REDACTED]", "steps_json": "[REDACTED]"}
```

## `system_activity.csv`

- Data rows: 4011
- Schema (8 columns): `activity_id, event_time, event_type, source_system, target_system, resource_id, reported_result, details`
- Sample rows (up to five, in source order; sensitive identifier/answer values redacted):

```json
{"activity_id": "activity_01", "event_time": "2026-01-04T14:56:29Z", "event_type": "INDEX_RECORD", "source_system": "account_service", "target_system": "search_service", "resource_id": "search_9729", "reported_result": "SUCCESS", "details": "Customer search-index refresh processed search_9729."}
{"activity_id": "activity_02", "event_time": "2026-01-04T16:08:26Z", "event_type": "INDEX_RECORD", "source_system": "account_service", "target_system": "search_service", "resource_id": "search_6919", "reported_result": "SUCCESS", "details": "Customer search-index refresh processed search_6919."}
{"activity_id": "activity_03", "event_time": "2026-01-04T17:14:03Z", "event_type": "INDEX_RECORD", "source_system": "account_service", "target_system": "search_service", "resource_id": "search_4613", "reported_result": "SUCCESS", "details": "Customer search-index refresh processed search_4613."}
{"activity_id": "activity_04", "event_time": "2026-01-04T18:36:21Z", "event_type": "UPDATE_RECORD", "source_system": "support_platform", "target_system": "search_service", "resource_id": "support_4185", "reported_result": "SUCCESS", "details": "Support-case index update processed support_4185."}
{"activity_id": "activity_05", "event_time": "2026-01-04T18:36:36Z", "event_type": "UPDATE_RECORD", "source_system": "profile_service", "target_system": "account_service", "resource_id": "account_2689", "reported_result": "FAILED", "details": "Profile preference update processed account_2689."}
```

## `user_audit_log.csv`

- Data rows: 306
- Schema (6 columns): `audit_id, user_id, event_time, field_name, old_value, new_value`
- Sample rows (up to five, in source order; sensitive identifier/answer values redacted):

```json
{"audit_id": "audit_01", "user_id": "user_485", "event_time": "2024-12-14T16:31:44Z", "field_name": "phone", "old_value": "+33 6 24 34 80 16", "new_value": "+33 6 63 29 68 28"}
{"audit_id": "audit_02", "user_id": "user_505", "event_time": "2024-12-25T00:51:04Z", "field_name": "phone", "old_value": "+81 90 6278 6936", "new_value": "+81 90 7870 0272"}
{"audit_id": "audit_03", "user_id": "user_525", "event_time": "2025-01-04T00:11:24Z", "field_name": "phone", "old_value": "+46 70 144 08 06", "new_value": "+46 70 808 74 05"}
{"audit_id": "audit_04", "user_id": "user_380", "event_time": "2025-01-28T13:16:29Z", "field_name": "phone", "old_value": "+44 7700 900880", "new_value": "+44 7700 900380"}
{"audit_id": "audit_05", "user_id": "user_400", "event_time": "2025-02-08T04:36:49Z", "field_name": "phone", "old_value": "+27 72 156 3064", "new_value": "+27 72 384 3167"}
```

## `user_identities.csv`

- Data rows: 850
- Schema (6 columns): `user_id, name, email, phone, email_hash, updated_at`
- Sample rows (up to five, in source order; sensitive identifier/answer values redacted):

```json
{"user_id": "user_01", "name": "Amina El-Masri", "email": "[REDACTED]", "phone": "+971 50 482 7316", "email_hash": "d4e1f59abcf9a1e0cfdc7c27ad6c07ed4ff88b326a16ed5eed5ec6bc31618c93", "updated_at": "2026-05-28T04:03:00Z"}
{"user_id": "user_02", "name": "Mateo Ríos", "email": "[REDACTED]", "phone": "+34 612 847 593", "email_hash": "fad1c282b6b8ff346ee92e617331f69c2b6bb345af954eeb44581c57529eab9d", "updated_at": "2026-04-24T07:44:00Z"}
{"user_id": "user_03", "name": "Oliver Bennett", "email": "[REDACTED]", "phone": "+1 (202) 555-0103", "email_hash": "1fa7764c96e40e8570cbb7569f707f6d84c593cecbe5c1ed2b0a07a624dba039", "updated_at": "2026-03-14T14:21:00Z"}
{"user_id": "user_04", "name": "Thandiwe Ndlovu", "email": "[REDACTED]", "phone": "+27 71 684 5928", "email_hash": "f730ef60615bde7a8f5ee21138637b4e9d4094855fbb02da6afcdba9c076281f", "updated_at": "2026-03-21T20:59:00Z"}
{"user_id": "user_05", "name": "Leila Haddad", "email": "[REDACTED]", "phone": "+212 6 48 27 15 93", "email_hash": "62667ed065b846a842474f916da51b658edb0f9754ab2da6bf38e68779ff0d08", "updated_at": "2026-02-14T17:33:00Z"}
```
