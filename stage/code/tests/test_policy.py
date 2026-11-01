import json
from datetime import datetime, timezone
from pathlib import Path

from ghost_data.data import DeletionRule, load_csv
from ghost_data.identity import IdentityIndex
from ghost_data.observations import Observation, parse_evidence_file
from ghost_data.policy import PolicyAction, PolicyEngine


DATASET = Path(__file__).resolve().parents[2] / "dataset"
RULES = load_csv(DATASET / "deletion_rules.csv")
RULE_BY_CATEGORY = {rule.data_category: rule for rule in RULES}
ENGINE = PolicyEngine(RULES)
AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYNTHETIC_EMAIL = "subject" + "@" + ".".join(("invalid", "test"))


def observation(category: str, **facts) -> Observation:
    return Observation(
        file_id="fixture-evidence", captured_at=AS_OF, system_id="fixture_system",
        resource_id="fixture_resource", data_category=category, **facts,
    )


def test_engine_loads_every_policy_category_from_csv():
    assert set(ENGINE.rules) == {rule.data_category for rule in RULES}
    assert all(rule.condition for rule in RULES)


def test_always_conditions_take_the_action_from_the_policy_csv():
    for rule in RULES:
        if rule.condition == "Always":
            decision = ENGINE.evaluate(observation(rule.data_category))
            assert decision.action.value == rule.required_action
            assert decision.condition_met is True


def test_support_message_shared_context_redacts_otherwise_deletes():
    shared = ENGINE.evaluate(observation("SUPPORT_MESSAGE", shared_context=True))
    private = ENGINE.evaluate(observation("SUPPORT_MESSAGE", shared_context=False))
    assert shared.action.value == RULE_BY_CATEGORY["SUPPORT_MESSAGE"].required_action
    assert shared.retain_record
    assert private.action is PolicyAction.DELETE


def test_support_message_with_unknown_context_and_no_direct_identifiers_is_compliant_redaction():
    decision = ENGINE.evaluate(observation(
        "SUPPORT_MESSAGE", identifiers_present={"stable_reference": ["stable-reference"]},
    ))
    assert decision.action is PolicyAction.REDACT
    assert decision.condition_met is False
    assert decision.retain_record


def test_support_attachment_requires_subject_exclusivity():
    owned = ENGINE.evaluate(observation("SUPPORT_ATTACHMENT", belongs_only_to_subject=True))
    shared = ENGINE.evaluate(observation("SUPPORT_ATTACHMENT", belongs_only_to_subject=False))
    unknown = ENGINE.evaluate(observation("SUPPORT_ATTACHMENT"))
    assert owned.action.value == RULE_BY_CATEGORY["SUPPORT_ATTACHMENT"].required_action
    assert shared.action is PolicyAction.NO_ACTION
    assert unknown.action is PolicyAction.REVIEW


def test_analytics_and_telemetry_anonymize_only_while_attributable():
    for category in ("ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"):
        linked = ENGINE.evaluate(observation(category, attributable=True))
        cleared = ENGINE.evaluate(observation(category, anonymized=True, identifiable=False))
        unknown = ENGINE.evaluate(observation(category))
        assert linked.action.value == RULE_BY_CATEGORY[category].required_action
        assert cleared.action is PolicyAction.NO_ACTION
        assert unknown.action is PolicyAction.REVIEW


def test_email_delivery_log_is_redacted_only_when_email_is_present():
    has_email = ENGINE.evaluate(observation("EMAIL_DELIVERY_LOG", identifiers_present={"email": [SYNTHETIC_EMAIL]}))
    no_email = ENGINE.evaluate(observation("EMAIL_DELIVERY_LOG"))
    assert has_email.action.value == RULE_BY_CATEGORY["EMAIL_DELIVERY_LOG"].required_action
    assert has_email.clear_identifiers == ("email",)
    assert no_email.action is PolicyAction.NO_ACTION


def test_security_retention_legal_hold_and_backup_conditions():
    retained = ENGINE.evaluate(observation("SECURITY_AUDIT_LOG", within_retention=True))
    expired = ENGINE.evaluate(observation("SECURITY_AUDIT_LOG", within_retention=False))
    held = ENGINE.evaluate(observation("LEGAL_HOLD_RECORD", legal_hold_active=True))
    released = ENGINE.evaluate(observation("LEGAL_HOLD_RECORD", legal_hold_active=False))
    backup = ENGINE.evaluate(observation("BACKUP_ARCHIVE", restore_access_blockable=True))
    already_blocked = ENGINE.evaluate(observation("BACKUP_ARCHIVE", restore_blocked=True))
    restore_disallowed = ENGINE.evaluate(observation("BACKUP_ARCHIVE", restore_allowed=False))
    assert retained.action.value == RULE_BY_CATEGORY["SECURITY_AUDIT_LOG"].required_action
    assert expired.action is PolicyAction.DELETE
    assert held.action.value == RULE_BY_CATEGORY["LEGAL_HOLD_RECORD"].required_action
    assert released.action is PolicyAction.DELETE
    assert backup.action is PolicyAction.BLOCK_RESTORE and backup.retain_record
    assert already_blocked.action.value == RULE_BY_CATEGORY["BACKUP_ARCHIVE"].required_action
    assert restore_disallowed.action.value == RULE_BY_CATEGORY["BACKUP_ARCHIVE"].required_action


def test_tombstone_preserves_stable_user_id_and_clears_direct_identifiers():
    exposed = ENGINE.evaluate(observation(
        "ACCOUNT_TOMBSTONE",
        identifiers_present={"user_id": ["stable-reference"], "email": [SYNTHETIC_EMAIL], "name": ["synthetic" + " " + "person"]},
    ))
    compliant = ENGINE.evaluate(observation(
        "ACCOUNT_TOMBSTONE", identifiers_present={"user_id": ["stable-reference"]},
        identifiers_cleared=["name", "email", "phone", "email_hash"],
    ))
    assert exposed.action.value == RULE_BY_CATEGORY["ACCOUNT_TOMBSTONE"].required_action
    assert exposed.retain_record and exposed.preserve_identifiers == ("user_id",)
    assert set(exposed.clear_identifiers) == {"email", "name"}
    assert compliant.action is PolicyAction.RETAIN


def test_explicit_retention_deadline_is_evaluated_at_case_cutoff():
    due = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observation_due = observation("SECURITY_AUDIT_LOG", retention_until=due)
    assert ENGINE.evaluate(observation_due, at=due).action.value == RULE_BY_CATEGORY["SECURITY_AUDIT_LOG"].required_action
    after = datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert ENGINE.evaluate(observation_due, at=after).action is PolicyAction.DELETE


def test_sample_output_policy_actions_are_supported_by_csv_rules():
    # Derive observed treatment families from the sample answers, then ensure
    # the rules loaded from the policy CSV include corresponding actions.
    sample_rows = load_csv(DATASET / "sample_output.csv")
    operations = {
        step["operation"]
        for row in sample_rows
        for step in json.loads(row.steps_json)
        if step["phase"] == "REMEDIATION"
    }
    policy_actions = {rule.required_action for rule in RULES}
    assert "DELETE_RECORD" in operations and "DELETE" in policy_actions
    assert "REDACT_RECORD" in operations and "REDACT" in policy_actions
    assert "ANONYMIZE_RECORD" in operations and "ANONYMIZE" in policy_actions
    assert "BLOCK_RESTORE" in operations and "BACKUP_ARCHIVE" in ENGINE.rules


def test_policy_decisions_agree_with_sample_remediation_steps_when_evidence_is_decisive():
    requests = load_csv(DATASET / "sample_deletion_requests.csv")
    outputs = load_csv(DATASET / "sample_output.csv")
    identities = load_csv(DATASET / "user_identities.csv")
    audits = load_csv(DATASET / "user_audit_log.csv")
    manifest = {row.file_id: row for row in load_csv(DATASET / "evidence_files.csv")}
    identity_index = IdentityIndex(identities, audits)
    evidence_ids = {
        step["evidence_id"]
        for row in outputs
        for step in json.loads(row.steps_json)
        if step["phase"] == "FINDING" and step["evidence_id"]
    }
    observations = {}
    for evidence_id in evidence_ids:
        parsed, _ = parse_evidence_file(manifest[evidence_id], DATASET)
        for item in parsed:
            observations[(item.file_id, item.resource_id)] = item

    operation_for_action = {
        PolicyAction.DELETE: "DELETE_RECORD",
        PolicyAction.REDACT: "REDACT_RECORD",
        PolicyAction.ANONYMIZE: "ANONYMIZE_RECORD",
        PolicyAction.BLOCK_RESTORE: "BLOCK_RESTORE",
    }
    checked = set()
    for request, output in zip(requests, outputs):
        subject = identity_index.resolve(request)
        steps = json.loads(output.steps_json)
        findings = {step["resource_id"]: step for step in steps if step["phase"] == "FINDING"}
        for step in (value for value in steps if value["phase"] == "REMEDIATION"):
            if step["operation"] == "DISABLE_DATA_FLOW":
                continue  # flow-control operations have no deletion_rules.csv category
            finding = findings.get(step["resource_id"])
            if not finding or not finding["evidence_id"]:
                continue
            item = observations.get((finding["evidence_id"], step["resource_id"]))
            if item is None or item.data_category_source != "explicit" or item.data_category not in ENGINE.rules:
                continue
            decision = ENGINE.evaluate(item, subject=subject, at=request.audit_at)
            expected_operation = operation_for_action.get(decision.action)
            if expected_operation:
                assert step["operation"] == expected_operation, (item.data_category, decision.reason)
                checked.add(item.data_category)
    assert checked <= set(ENGINE.rules)
