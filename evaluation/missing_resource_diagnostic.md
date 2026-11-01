# Missing sample resource diagnostic

Diagnostic only; dataset files were read only. The sample reference was used solely to define missing memberships.

Missing expected resource pairs in predictions: 72.

## Counts

- A: 17
- B: 41
- C: 11
- D: 3

## Every missing resource pair

| Sample row | Resource | Class | Evidence |
|---:|---|:---:|---|
| 1 | account_001 | A | evidence_54 |
| 2 | account_002 | A | evidence_54 |
| 3 | analytics_9406 | B | evidence_94 |
| 4 | account_004 | A | evidence_54 |
| 4 | analytics_901 | B | evidence_56 |
| 5 | account_005 | C | evidence_54 |
| 6 | account_006 | A | (empty) |
| 7 | account_007 | A | (empty) |
| 7 | support_001 | B | evidence_58 |
| 8 | account_008 | A | (empty) |
| 9 | account_3960 | B | (empty) |
| 9 | audit_record_4902 | B | (empty) |
| 10 | account_010 | A | (empty) |
| 10 | support_002 | B | evidence_61 |
| 11 | audit_record_9394 | B | (empty) |
| 11 | data_flow_9522 | D | evidence_03 |
| 12 | account_9797 | B | (empty) |
| 12 | analytics_9914 | B | evidence_01 |
| 12 | audit_record_2945 | B | (empty) |
| 13 | audit_record_4816 | B | (empty) |
| 14 | audit_record_987 | B | (empty) |
| 14 | backup_3870 | D | evidence_03 |
| 15 | account_4745 | C | (empty) |
| 15 | audit_record_1596 | B | (empty) |
| 15 | data_flow_9846 | B | evidence_01 |
| 16 | audit_record_9528 | C | (empty) |
| 17 | account_4092 | B | (empty) |
| 17 | audit_record_1797 | B | (empty) |
| 17 | backup_3245 | B | evidence_01 |
| 18 | account_5521 | A | (empty) |
| 18 | audit_record_6645 | A | (empty) |
| 19 | account_9102 | B | (empty) |
| 19 | audit_record_6793 | B | (empty) |
| 20 | account_5037 | A | (empty) |
| 20 | audit_record_5569 | A | (empty) |
| 21 | account_6440 | B | evidence_92 |
| 21 | analytics_5335 | B | evidence_92 |
| 21 | audit_record_3737 | C | evidence_92 |
| 22 | account_4990 | A | (empty) |
| 22 | audit_record_3482 | C | (empty) |
| 23 | account_410 | A | (empty) |
| 23 | audit_record_4128 | B | (empty) |
| 24 | account_5334 | C | evidence_92 |
| 24 | audit_record_7095 | B | (empty) |
| 25 | account_3136 | B | evidence_92 |
| 25 | analytics_1895 | B | evidence_92 |
| 25 | audit_record_451 | C | evidence_92 |
| 26 | account_5684 | B | evidence_92 |
| 26 | analytics_4566 | B | evidence_92 |
| 26 | audit_record_5416 | C | evidence_92 |
| 27 | account_3866 | B | evidence_92 |
| 27 | analytics_4574 | B | evidence_92 |
| 27 | audit_record_3830 | C | evidence_92 |
| 28 | account_5482 | B | evidence_92 |
| 28 | analytics_6077 | B | evidence_92 |
| 28 | audit_record_9265 | C | evidence_92 |
| 29 | account_7012 | A | (empty) |
| 29 | analytics_5208 | B | evidence_92 |
| 29 | audit_record_3954 | B | (empty) |
| 29 | data_flow_3827 | B | evidence_92 |
| 29 | search_1993 | B | evidence_92 |
| 29 | support_5281 | B | evidence_92 |
| 30 | account_4163 | A | (empty) |
| 30 | analytics_3697 | B | evidence_92 |
| 30 | audit_record_1707 | B | (empty) |
| 30 | data_flow_8524 | B | evidence_92 |
| 30 | search_9359 | B | evidence_92 |
| 30 | support_6477 | B | evidence_92 |
| 31 | account_4857 | A | evidence_51 |
| 31 | audit_record_6909 | D | evidence_51 |
| 32 | account_8858 | A | (empty) |
| 32 | audit_record_7068 | C | (empty) |

## A: No observation in index — examples

### Sample row 1 — account_001

- Expected system: account_service; evidence: evidence_54; file: `evidence/databases/customer_accounts_failover_replica_20260902.sql`
- Diagnosis: No parsed observation for this resource_id exists anywhere in the evidence index.
- All parsed observations for resource: 0
- Subject identifier set: `{"email": ["amina.elmasri@gmail.com"], "email_hash": ["d4e1f59abcf9a1e0cfdc7c27ad6c07ed4ff88b326a16ed5eed5ec6bc31618c93"], "name": ["Amina El-Masri"], "phone": ["+971 50 482 7316"], "user_id": ["user_01"]}`
- Matching identifiers present in record: `{}`
- Cited-file observations: `[]`
- Selected state: `null`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
-- Ghost Data Still Exists: point-in-time database snapshot
-- Dialect: SQLite-compatible SQL
-- Captured at: 2026-09-02T23:00:00Z
-- Database topology: failover_replica
-- Compare the primary and any replica tables for replication drift.

BEGIN TRANSACTION;
CREATE TABLE customer_profiles_failover_replica (
                resource_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                full_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL,
                account_status TEXT NOT NULL, updated_at TEXT NOT NULL
            );
INSERT INTO "customer_profiles_failover_replica" VALUES('account_005','user_05','Leila Haddad','leila.haddad@yahoo.com','+212 6 48 27 15 93','ACTIVE','2026-09-02T22:45:00Z');
INSERT INTO "customer_profiles_failover_replica" VALUES('account_8741','user_8741','Karim El-Masri','karim.elmasri@gmail.com','+971 50 731 6284','ACTIVE','2026-09-02T22:45:00Z');
INSERT INTO "customer_profiles_failover_replica" VALUES('account_9116','user_9116','Mateo Rios Gil'…
```

### Sample row 2 — account_002

- Expected system: account_service; evidence: evidence_54; file: `evidence/databases/customer_accounts_failover_replica_20260902.sql`
- Diagnosis: No parsed observation for this resource_id exists anywhere in the evidence index.
- All parsed observations for resource: 0
- Subject identifier set: `{"email": ["mateo.rios@outlook.com"], "email_hash": ["fad1c282b6b8ff346ee92e617331f69c2b6bb345af954eeb44581c57529eab9d"], "name": ["Mateo Ríos"], "phone": ["+34 612 847 593"], "user_id": ["user_02"]}`
- Matching identifiers present in record: `{}`
- Cited-file observations: `[]`
- Selected state: `null`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
-- Ghost Data Still Exists: point-in-time database snapshot
-- Dialect: SQLite-compatible SQL
-- Captured at: 2026-09-02T23:00:00Z
-- Database topology: failover_replica
-- Compare the primary and any replica tables for replication drift.

BEGIN TRANSACTION;
CREATE TABLE customer_profiles_failover_replica (
                resource_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                full_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL,
                account_status TEXT NOT NULL, updated_at TEXT NOT NULL
            );
INSERT INTO "customer_profiles_failover_replica" VALUES('account_005','user_05','Leila Haddad','leila.haddad@yahoo.com','+212 6 48 27 15 93','ACTIVE','2026-09-02T22:45:00Z');
INSERT INTO "customer_profiles_failover_replica" VALUES('account_8741','user_8741','Karim El-Masri','karim.elmasri@gmail.com','+971 50 731 6284','ACTIVE','2026-09-02T22:45:00Z');
INSERT INTO "customer_profiles_failover_replica" VALUES('account_9116','user_9116','Mateo Rios Gil'…
```

### Sample row 4 — account_004

- Expected system: account_service; evidence: evidence_54; file: `evidence/databases/customer_accounts_failover_replica_20260902.sql`
- Diagnosis: No parsed observation for this resource_id exists anywhere in the evidence index.
- All parsed observations for resource: 0
- Subject identifier set: `{"email": ["thandiwe.n@gmail.com"], "email_hash": ["f730ef60615bde7a8f5ee21138637b4e9d4094855fbb02da6afcdba9c076281f"], "name": ["Thandiwe Ndlovu"], "phone": ["+27 71 684 5928"], "user_id": ["user_04"]}`
- Matching identifiers present in record: `{}`
- Cited-file observations: `[]`
- Selected state: `null`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
-- Ghost Data Still Exists: point-in-time database snapshot
-- Dialect: SQLite-compatible SQL
-- Captured at: 2026-09-02T23:00:00Z
-- Database topology: failover_replica
-- Compare the primary and any replica tables for replication drift.

BEGIN TRANSACTION;
CREATE TABLE customer_profiles_failover_replica (
                resource_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                full_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL,
                account_status TEXT NOT NULL, updated_at TEXT NOT NULL
            );
INSERT INTO "customer_profiles_failover_replica" VALUES('account_005','user_05','Leila Haddad','leila.haddad@yahoo.com','+212 6 48 27 15 93','ACTIVE','2026-09-02T22:45:00Z');
INSERT INTO "customer_profiles_failover_replica" VALUES('account_8741','user_8741','Karim El-Masri','karim.elmasri@gmail.com','+971 50 731 6284','ACTIVE','2026-09-02T22:45:00Z');
INSERT INTO "customer_profiles_failover_replica" VALUES('account_9116','user_9116','Mateo Rios Gil'…
```


## B: Observation exists but is not linked — examples

### Sample row 3 — analytics_9406

- Expected system: analytics_platform; evidence: evidence_94; file: `evidence/logs/resource_lookup_trace_20260926_103856.log`
- Diagnosis: The cited file has an observation, but no subject link reached this resource.
- All parsed observations for resource: 2
- Subject identifier set: `{"email": ["l.fontaine46@yahoo.com"], "email_hash": ["4b065493f4403c03ee3cd593b75b03cb6085134a7acb5c5c63ed71d3da346c77"], "name": ["Louis Fontaine"], "phone": ["+33 6 80 08 96 38"], "user_id": ["user_43"]}`
- Matching identifiers present in record: `{}`
- Cited-file observations: `[{"captured_at": "2026-09-26T10:38:56+00:00", "category": "ANALYTICS_PROFILE", "excerpt": "2026-09-26T09:54:09Z level=DEBUG service=analytics_platform trace_id=rb-095409-021 event=analytics_profile_read_started resource_id=analytics_9406 lookup_key=null", "ids": {"phone": ["095409-021"]}, "refs": {}, "system": "analytics_platform"}, {"captured_at": "2026-09-26T10:38:56+00:00", "category": "ANALYTICS_PROFILE", "excerpt": "2026-09-26T09:54:09Z level=INFO service=analytics_platform trace_id=rb-095409-021 event=analytics_profile_read_completed resource_id=analytics_9406 customer_reference=null email=null phone=null email_hash=null audience_cohort=general_shopper", "ids": {"email": ["null"], "email_hash": ["null"], "phone": ["null"], "stable_reference": ["null"]}, "refs": {}, "system": "analytics_platform"}]`
- Selected state: `null`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
2026-09-26T09:52:54Z level=INFO service=integration_service trace_id=rb-095254-020 event=connector_config_read_completed resource_id=data_flow_1770 enabled=true last_delivery_status=delivered connector_name=customer_events_connector customer_email=akosua.gyasi@gmail.com customer_reference=null
2026-09-26T09:54:09Z level=DEBUG service=analytics_platform trace_id=rb-095409-021 event=analytics_profile_read_started resource_id=analytics_9406 lookup_key=null
2026-09-26T09:54:09Z level=INFO service=analytics_platform trace_id=rb-095409-021 event=analytics_profile_read_completed resource_id=analytics_9406 customer_reference=null email=null phone=null email_hash=null audience_cohort=general_shopper
2026-09-26T09:58:35Z level=DEBUG service=search_service trace_id=rb-095835-022 event=index_query_started resource_id=search_2127 lookup_key=lnajjar900380@fastmail.com
```

### Sample row 4 — analytics_901

- Expected system: analytics_platform; evidence: evidence_56; file: `evidence/records/customer_analytics_report_20260907.json`
- Diagnosis: The cited file has an observation, but no subject link reached this resource.
- All parsed observations for resource: 1
- Subject identifier set: `{"email": ["thandiwe.n@gmail.com"], "email_hash": ["f730ef60615bde7a8f5ee21138637b4e9d4094855fbb02da6afcdba9c076281f"], "name": ["Thandiwe Ndlovu"], "phone": ["+27 71 684 5928"], "user_id": ["user_04"]}`
- Matching identifiers present in record: `{}`
- Cited-file observations: `[{"captured_at": "2026-09-07T09:45:00+00:00", "category": "ANALYTICS_PROFILE", "excerpt": "{\"email\": null, \"email_hash\": null, \"metrics\": {\"orders_completed_90d\": 2, \"products_viewed_30d\": 24, \"revenue_90d_usd\": 146.8, \"sessions_30d\": 11}, \"phone\": null, \"recent_activity\": [{\"event\": \"product_viewed\", \"product\": \"Travel backpack\"}, {\"event\": \"purchase_completed\", \"product\": \"Travel backpack\", \"quantity\": 1}], \"reporting_window\": \"last_90_days\", \"resource_id\": \"analytics_901\", \"user_id\": null}", "ids": {}, "refs": {}, "system": "analytics_platform"}]`
- Selected state: `null`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
    {
      "resource_id": "analytics_901",
      "user_id": null,
```

### Sample row 7 — support_001

- Expected system: support_platform; evidence: evidence_58; file: `evidence/documents/delivery_correction_attachment.pdf`
- Diagnosis: The cited file has an observation, but no subject link reached this resource.
- All parsed observations for resource: 2
- Subject identifier set: `{"email": ["priya.raman@gmail.com"], "email_hash": ["284c7b87b8237e241293c9e81c8f0bef10c4dc1dffefb382c45107ea40c39668"], "name": ["Priya Raman"], "phone": ["+91 98765 73142"], "user_id": ["user_07"]}`
- Matching identifiers present in record: `{}`
- Cited-file observations: `[{"captured_at": "2026-09-12T07:30:00+00:00", "category": "SUPPORT_ATTACHMENT", "excerpt": "        Support reference CS-4827 / support_001                                   ", "ids": {}, "refs": {}, "system": "support_platform"}, {"captured_at": "2026-09-12T07:30:00+00:00", "category": "SUPPORT_ATTACHMENT", "excerpt": "         Detail            reference CS-4827 / support_001                        ", "ids": {}, "refs": {}, "system": "support_platform"}]`
- Selected state: `null`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
        DELIVERY     ADDRESS      CORRECTION       REQUEST                        
        Support reference CS-4827 / support_001                                   
                                                                                  
         Detail            reference CS-4827 / support_001                        
```


## C: Different snapshot selected — examples

### Sample row 5 — account_005

- Expected system: account_service; evidence: evidence_54; file: `evidence/databases/customer_accounts_failover_replica_20260902.sql`
- Diagnosis: Resource linked; another evidence snapshot/coverage was selected.
- All parsed observations for resource: 1
- Subject identifier set: `{"email": ["leila.haddad@yahoo.com"], "email_hash": ["62667ed065b846a842474f916da51b658edb0f9754ab2da6bf38e68779ff0d08"], "name": ["Leila Haddad"], "phone": ["+212 6 48 27 15 93"], "user_id": ["user_05"]}`
- Matching identifiers present in record: `{"email": ["leila.haddad@yahoo.com"], "name": ["Leila Haddad"], "phone": ["+212 6 48 27 15 93"], "user_id": ["user_05"]}`
- Cited-file observations: `[{"captured_at": "2026-09-02T23:00:00+00:00", "category": "USER_PROFILE", "excerpt": "{\"account_status\": \"ACTIVE\", \"email\": \"leila.haddad@yahoo.com\", \"full_name\": \"Leila Haddad\", \"phone\": \"+212 6 48 27 15 93\", \"resource_id\": \"account_005\", \"updated_at\": \"2026-09-02T22:45:00Z\", \"user_id\": \"user_05\"}", "ids": {"email": ["leila.haddad@yahoo.com"], "name": ["Leila Haddad"], "phone": ["+212 6 48 27 15 93"], "user_id": ["user_05"]}, "refs": {}, "system": "account_service"}]`
- Selected state: `{"captured_at": "2026-09-05T07:18:01+00:00", "category": "USER_PROFILE", "evidence": ["evidence_90"], "state": "ABSENT"}`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
            );
INSERT INTO "customer_profiles_failover_replica" VALUES('account_005','user_05','Leila Haddad','leila.haddad@yahoo.com','+212 6 48 27 15 93','ACTIVE','2026-09-02T22:45:00Z');
INSERT INTO "customer_profiles_failover_replica" VALUES('account_8741','user_8741','Karim El-Masri','karim.elmasri@gmail.com','+971 50 731 6284','ACTIVE','2026-09-02T22:45:00Z');
```

### Sample row 15 — account_4745

- Expected system: account_service; evidence: (empty); file: `(no citation)`
- Diagnosis: Resource linked from other evidence; the cited file has no parsed observation for this resource.
- All parsed observations for resource: 1
- Subject identifier set: `{"email": ["lucia-torres@gmail.com"], "email_hash": ["3a998570469df6b3cf40bb58e9b2a55e4890cded9f801df993ed6584f990826c"], "name": ["Lucía Torres"], "phone": ["+34 715 351 235", "+34 728 875 900"], "user_id": ["user_15"]}`
- Matching identifiers present in record: `{"email": ["lucia-torres@gmail.com"]}`
- Cited-file observations: `[]`
- Selected state: `{"captured_at": "2026-09-15T12:00:00+00:00", "category": "USER_PROFILE", "evidence": ["evidence_51"], "state": "ABSENT"}`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
(no extracted text; inspect source artifact format)
```

### Sample row 16 — audit_record_9528

- Expected system: security_service; evidence: (empty); file: `(no citation)`
- Diagnosis: Resource linked from other evidence; the cited file has no parsed observation for this resource.
- All parsed observations for resource: 2
- Subject identifier set: `{"email": ["diya.k4436@outlook.com"], "email_hash": ["1ecc0a4afc62297c78d36eb27b889e059bec83609e3177b8bbd42ea7648ad46e"], "name": ["Diya Kapoor"], "phone": ["+91 96023 32879"], "user_id": ["user_53"]}`
- Matching identifiers present in record: `{}`
- Cited-file observations: `[]`
- Selected state: `{"captured_at": "2026-09-21T10:00:00+00:00", "category": "SECURITY_AUDIT_LOG", "evidence": ["evidence_05"], "state": "PRESENT"}`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
(no extracted text; inspect source artifact format)
```


## D: Linked and selected but dropped — examples

### Sample row 11 — data_flow_9522

- Expected system: integration_service; evidence: evidence_03; file: `evidence/records/customer_account_handover_20261001.txt`
- Diagnosis: Cited snapshot was selected but the processor/planner emitted no step for this resource.
- All parsed observations for resource: 1
- Subject identifier set: `{"email": ["novak.tomasz@icloud.com"], "email_hash": ["c5d7aedd1046a82b5fdc1d4f8e2a2d463245cecad77e0f10aec24a5d83b0dc52"], "name": ["Tomasz Novak"], "phone": ["+48 601 623 422"], "user_id": ["user_32"]}`
- Matching identifiers present in record: `{"email": ["novak.tomasz@icloud.com"]}`
- Cited-file observations: `[{"captured_at": "2026-10-01T12:00:00+00:00", "category": "USER_PROFILE", "excerpt": "- 2026-10-01T12:00:00Z | integration_service | data_flow_9522 | DATA_FLOW | ACTIVE | novak.tomasz@icloud.com", "ids": {"email": ["novak.tomasz@icloud.com"]}, "refs": {}, "system": "integration_service"}]`
- Selected state: `{"captured_at": "2026-10-01T12:00:00+00:00", "category": "USER_PROFILE", "evidence": ["evidence_03"], "state": "PRESENT"}`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
- 2026-10-01T12:00:00Z | integration_service | data_flow_7495 | DATA_FLOW | ACTIVE | SIPHO.MOKOENA@GMAIL.COM
- 2026-10-01T12:00:00Z | integration_service | data_flow_9522 | DATA_FLOW | ACTIVE | novak.tomasz@icloud.com
- 2026-10-01T12:00:00Z | search_service | search_052 | SEARCH_INDEX_ENTRY | FOUND | novak.tomasz@icloud.com
```

### Sample row 14 — backup_3870

- Expected system: backup_service; evidence: evidence_03; file: `evidence/records/customer_account_handover_20261001.txt`
- Diagnosis: Cited snapshot was selected but the processor/planner emitted no step for this resource.
- All parsed observations for resource: 1
- Subject identifier set: `{"email": ["y.tanaka32@gmail.com"], "email_hash": ["3eafe3b9e3dcda746895ba9b54148df33f38f8dc900b14acd2dfc95428493e20"], "name": ["Yuki Tanaka"], "phone": ["+81 90 0802 6399"], "user_id": ["user_37"]}`
- Matching identifiers present in record: `{"email": ["y.tanaka32@gmail.com"]}`
- Cited-file observations: `[{"captured_at": "2026-10-01T12:00:00+00:00", "category": "BACKUP_ARCHIVE", "excerpt": "- 2026-10-01T12:00:00Z | backup_service | backup_3870 | BACKUP_ARCHIVE | ACTIVE | y.tanaka32@gmail.com", "ids": {"email": ["y.tanaka32@gmail.com"]}, "refs": {}, "system": "backup_service"}]`
- Selected state: `{"captured_at": "2026-10-01T12:00:00+00:00", "category": "BACKUP_ARCHIVE", "evidence": ["evidence_03"], "state": "PRESENT"}`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
- 2026-10-01T12:00:00Z | analytics_platform | analytics_9447 | ANALYTICS_PROFILE | ANONYMIZED | no direct identifier
- 2026-10-01T12:00:00Z | backup_service | backup_3870 | BACKUP_ARCHIVE | ACTIVE | y.tanaka32@gmail.com
- 2026-10-01T12:00:00Z | backup_service | backup_706 | BACKUP_ARCHIVE | BLOCKED | user_39
```

### Sample row 31 — audit_record_6909

- Expected system: security_service; evidence: evidence_51; file: `evidence/records/customer_data_snapshot_bundle_20260915.json`
- Diagnosis: Cited snapshot was selected but the processor/planner emitted no step for this resource.
- All parsed observations for resource: 1
- Subject identifier set: `{"email": ["a.eze08@gmail.com"], "email_hash": ["1b7bf5a90890498cc6b7d2b50b0580ad1dbfaee7766f5d09cd87ecb548533e9e"], "name": ["Amara Eze"], "phone": ["+234 803 052 7943"], "user_id": ["user_541"]}`
- Matching identifiers present in record: `{}`
- Cited-file observations: `[{"captured_at": "2026-09-15T12:00:00+00:00", "category": "SECURITY_AUDIT_LOG", "excerpt": "{\"actor_type\": \"automated_privacy_workflow\", \"event_name\": \"account_deletion_reviewed\", \"integrity_seal\": \"sha256:0000000000000000000000000000000000000000000000000000000000001afd\", \"resource_id\": \"audit_record_6909\", \"subject_reference\": \"user_541\"}", "ids": {"email_hash": ["0000000000000000000000000000000000000000000000000000000000001afd"], "stable_reference": ["user_541"]}, "refs": {}, "system": "security_service"}]`
- Selected state: `{"captured_at": "2026-09-15T12:00:00+00:00", "category": "SECURITY_AUDIT_LOG", "evidence": ["evidence_51"], "state": "PRESENT"}`
- Shortest potential link path: `none found`
- Later emitted steps: `[]`
- Raw record text:
```text
        {
          "resource_id": "audit_record_6909",
          "subject_reference": "user_541",
```

## Additional requested diagnostics

- Full-run COMPLETE step-count histogram: `{0: 129, 1: 62, 2: 6, 4: 13}`
- Expected COMPLETE sample step-count histogram: `{1: 2, 2: 1, 3: 4, 6: 3}`

### NOT_APPLICABLE full-run requests

- `case_541` ? Please change the email address used for this account. I want to continue using the service.
- `case_542` ? Could you send me a copy of the information held on my account? I still use it, so please don't delete or change anything.

### CLASSIFY_REQUEST activity events

- `activity_3486` (2026-08-28T11:07:25Z): Privacy intake classified request for account_2461 as non-deletion; no destructive action was authorized.
- `activity_3512` (2026-08-29T10:47:38Z): Privacy intake classified request for account_2176 as non-deletion; no destructive action was authorized.
- `activity_3531` (2026-08-30T10:58:51Z): Privacy intake classified request for account_9321 as non-deletion; no destructive action was authorized.
- `activity_3618` (2026-09-03T11:09:05Z): Privacy intake classified request for account_6486 as non-deletion; no destructive action was authorized.
- `activity_3648` (2026-09-04T10:49:18Z): Privacy intake classified request for account_7452 as non-deletion; no destructive action was authorized.
- `activity_3659` (2026-09-05T11:00:31Z): Privacy intake classified request for account_5605 as non-deletion; no destructive action was authorized.
- `activity_3741` (2026-09-09T11:11:44Z): Privacy intake classified request for account_7821 as non-deletion; no destructive action was authorized.
- `activity_3778` (2026-09-10T10:51:57Z): Privacy intake classified request for account_5835 as non-deletion; no destructive action was authorized.
- `activity_3789` (2026-09-11T11:02:11Z): Privacy intake classified request for account_1733 as non-deletion; no destructive action was authorized.
- `activity_3827` (2026-09-13T10:56:12Z): Privacy intake classified request for account_228 as non-deletion; no destructive action was authorized.

### Test suite

Full suite result: 93 passed, 1 failed out of 94. The failure is `test_category_mapping_uses_policy_categories_and_logs_unmapped_types`; it expected the table-token test to resolve the profile category, while the generic matcher returned ACCOUNT_TOMBSTONE. No implementation or dataset files were changed during this diagnostic turn.

## Diagnostic interpretation details

### A parser-gap audit

All A cases have no `Observation` keyed by the expected resource ID. A raw text scan found one resource ID in the evidence corpus under a different field name; the other 16 expected IDs do not appear in the evidence text/OCR. Thus those 16 are evidence/reference gaps, not records the parser skipped. The one parser coverage gap is:

- Sample row 6: the expected account resource is present in the read replica file as `source_resource_id` on an observed search record, but `_resource` recognizes only `resource_id`, `resourceId`, and `record_id`. The raw row links the subject-matched search record to the expected account resource. Shortest path: subject email → search record (direct identifier match) → account resource (`source_resource_id`).

The cited SQL example for sample row 1 contains other account rows but no occurrence of the expected resource ID, so there is no raw record for the parser to have skipped.

### B link-path findings

The B examples expose the subject identifier set alongside the observed record identifiers and references. The shortest path is “none found” when the record contains no subject identifier and no shared reference found on a linked observation or activity. A trace phone, null fields, or an unrelated support reference does not establish a subject link.

### D drop points

- The active flow example reaches the `data_flow_` branch in `process_case.py`, which continues without a flow finding because `active_data_flow` was false; the pipe-delimited record did not populate the active/enabled field.
- The backup example's policy action is `REVIEW` because the evidence does not establish whether restore access can be blocked. `process_case.py` has no target treatment for REVIEW, so `treatment` remains empty and the resource is skipped.
- The audit record's policy action is `REVIEW` because no retention deadline/within-retention fact is available. The processor likewise produces no target for REVIEW, so the expected verification is dropped.
