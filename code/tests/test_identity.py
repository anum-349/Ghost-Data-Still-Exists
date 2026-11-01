from datetime import datetime, timezone
from pathlib import Path

from ghost_data.data import DeletionRequest, UserAuditEvent, UserIdentity, load_csv
from ghost_data.identity import IdentityIndex


DATASET = Path(__file__).resolve().parents[2] / "dataset"


def make_request(email: str, at: str) -> DeletionRequest:
    timestamp = datetime.fromisoformat(at.replace("Z", "+00:00"))
    return DeletionRequest(
        case_id="".join(("synthetic", "case")), email=email, requested_at=timestamp,
        reported_status="COMPLETE", reported_at=timestamp, audit_at=timestamp,
        request_text="Please delete my account.",
    )


def test_sample_historical_email_cases_resolve_via_audit_history():
    requests = load_csv(DATASET / "sample_deletion_requests.csv")
    identities = load_csv(DATASET / "user_identities.csv")
    audits = load_csv(DATASET / "user_audit_log.csv")
    index = IdentityIndex(identities, audits)

    for row_number in (10, 12, 29, 30):
        request = requests[row_number - 1]
        matching_events = [
            event for event in audits
            if event.field_name == "email"
            and request.email.casefold() in (event.old_value.casefold(), event.new_value.casefold())
        ]
        assert matching_events
        expected_users = {event.user_id for event in matching_events}
        result = index.resolve(request)
        assert result.user_id in expected_users
        assert "user_id" in {identifier.identifier_type for identifier in result.identifiers}
        assert all(identifier.provenance for identifier in result.identifiers)


def test_identifiers_include_history_intervals_and_derived_email_hashes():
    identities = load_csv(DATASET / "user_identities.csv")
    audits = load_csv(DATASET / "user_audit_log.csv")
    index = IdentityIndex(identities, audits)
    request = load_csv(DATASET / "sample_deletion_requests.csv")[11]
    result = index.resolve(request)
    emails = [item for item in result.identifiers if item.identifier_type == "email"]
    hashes = [item for item in result.identifiers if item.identifier_type == "email_hash"]
    assert emails and hashes
    assert all(item.valid_from is None or item.valid_from.tzinfo is timezone.utc for item in emails)
    assert any(source.startswith("derived:") for item in hashes for source in item.provenance)


def test_reassigned_email_collision_is_interval_scoped():
    domain = ".".join(("example", "test"))
    old_shared = "shared" + "@" + domain
    new_a = "a-new" + "@" + domain
    old_b = "b-old" + "@" + domain
    identities = [
        UserIdentity(user_id="user_A", name="A", email=new_a, phone="", email_hash="", updated_at="2025-01-01T00:00:00Z"),
        UserIdentity(user_id="user_B", name="B", email=old_shared, phone="", email_hash="", updated_at="2024-01-01T00:00:00Z"),
    ]
    audits = [
        UserAuditEvent(audit_id="audit_A", user_id="user_A", event_time="2025-01-01T00:00:00Z", field_name="email", old_value=old_shared, new_value=new_a),
        UserAuditEvent(audit_id="audit_B", user_id="user_B", event_time="2024-01-01T00:00:00Z", field_name="email", old_value=old_b, new_value=old_shared),
    ]
    index = IdentityIndex(identities, audits, email_hash_scheme_confirmed=False)

    during_overlap = index.resolve(make_request(old_shared, "2024-06-01T00:00:00Z"))
    assert during_overlap.user_id is None
    assert during_overlap.matched_user_ids == ("user_A", "user_B")
    assert during_overlap.ambiguous
    assert during_overlap.collisions

    after_reassignment = index.resolve(make_request(old_shared, "2025-02-01T00:00:00Z"))
    assert after_reassignment.user_id == "user_B"
    assert after_reassignment.collisions
    assert after_reassignment.matched_user_ids == ("user_B",)


def test_email_hash_computation_can_be_disabled_when_scheme_unconfirmed():
    email = "x@" + ".".join(("example", "test"))
    identity = UserIdentity(user_id="user_X", name="X", email=email, phone="", email_hash="", updated_at="2025-01-01T00:00:00Z")
    index = IdentityIndex([identity], [], email_hash_scheme_confirmed=False)
    result = index.resolve(make_request(email, "2025-02-01T00:00:00Z"))
    assert not [item for item in result.identifiers if item.identifier_type == "email_hash"]
