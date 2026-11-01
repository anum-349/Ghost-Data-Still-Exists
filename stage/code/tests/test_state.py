from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ghost_data.data import DeletionRequest, DeletionRule, SystemActivity, UserAuditEvent, UserIdentity
from ghost_data.identity import IdentityIndex
from ghost_data.observations import FileCoverage, InheritedIdentifier, Observation, ObservationIndex
from ghost_data.state import CaseStateAnalyzer, _observation_link


DATASET = Path(__file__).resolve().parents[2] / "dataset"
RULES = __import__("ghost_data.data", fromlist=["load_csv"]).load_csv(DATASET / "deletion_rules.csv")
DOMAIN = ".".join(("invalid", "test"))


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def setup_case(*, reported_status="COMPLETE", audit_at="2026-01-01T00:00:00Z"):
    user = UserIdentity(
        user_id="user_subject", name="Subject", email="subject@" + DOMAIN,
        phone="", email_hash="", updated_at="2025-01-01T00:00:00Z",
    )
    request = DeletionRequest(
        case_id="".join(("synthetic", "case")), email=user.email,
        requested_at="2025-12-01T00:00:00Z", reported_status=reported_status,
        reported_at="2025-12-02T00:00:00Z", audit_at=audit_at,
        request_text="Please delete this account.",
    )
    subject = IdentityIndex([user], []).resolve(request)
    return request, subject


def make_observation(resource="search_fixture", *, captured="2025-12-20T00:00:00Z", exists=True):
    return Observation(
        file_id="snapshot-evidence", captured_at=instant(captured), system_id="search_service",
        resource_id=resource, data_category="SEARCH_INDEX_ENTRY",
        identifiers_present={"user_id": ["user_subject"]}, exists=exists,
    )


def make_activity(activity_id, event_type, when, *, result="SUCCESS", resource="search_fixture"):
    return SystemActivity(
        activity_id=activity_id, event_time=instant(when), event_type=event_type,
        source_system="profile_service", target_system="search_service",
        resource_id=resource, reported_result=result,
        details="user_id=user_subject resource_id=" + resource,
    )


def test_sync_after_snapshot_is_reported_as_recreation_risk_not_proof_of_presence():
    request, subject = setup_case()
    observation = make_observation(exists=False)
    coverage = FileCoverage(
        file_id="snapshot-evidence", file_path="synthetic.sql", captured_at=observation.captured_at,
        tables=["search_documents"], stores=["search_service"], observations=1, is_snapshot=True,
    )
    activity = make_activity("activity-sync", "SYNC_RECORD", "2025-12-21T00:00:00Z")
    analyzer = CaseStateAnalyzer(ObservationIndex([observation], [coverage]), [activity], RULES)

    findings = analyzer.analyze(request, subject)

    state = findings.resources[0]
    assert state.state == "ABSENT"
    assert state.active_data_flow
    assert findings.active_data_flows == ("search_fixture",)
    assert state.activity_claims[0].activity_id == "activity-sync"
    assert state.activity_claims[0].after_snapshot
    assert findings.contradictions


def test_activity_after_audit_cutoff_is_ignored():
    request, subject = setup_case(audit_at="2025-12-21T12:00:00Z")
    observation = make_observation(exists=False)
    after_cutoff = make_activity("activity-late", "SYNC_RECORD", "2025-12-21T12:00:01Z")
    analyzer = CaseStateAnalyzer(ObservationIndex([observation], []), [after_cutoff], RULES)

    findings = analyzer.analyze(request, subject)

    assert findings.resources[0].state == "ABSENT"
    assert not findings.resources[0].active_data_flow
    assert findings.resources[0].activity_claims == ()


def test_shared_reference_edge_expands_linking_with_provenance():
    request, subject = setup_case()
    direct = make_observation(resource="account_subject")
    related = Observation(
        file_id="related-snapshot", captured_at=instant("2025-12-20T00:00:00Z"),
        system_id="search_service", resource_id="search_related",
        data_category="SEARCH_INDEX_ENTRY", shared_references={"order_id": ["order_fixture"]},
    )
    direct = direct.model_copy(update={"shared_references": {"order_id": ["order_fixture"]}})
    findings = CaseStateAnalyzer(ObservationIndex([direct, related], []), [], RULES).analyze(request, subject)
    assert {item.resource_id for item in findings.resources} == {"account_subject", "search_related"}
    assert any(edge.edge_type == "shared_reference" and edge.provenance.endswith("order_id=order_fixture")
               for edge in findings.link_edges)


def test_explicit_resource_reference_links_account_to_subject_and_snapshot_state():
    request, subject = setup_case()
    source = make_observation(resource="search_source", exists=False).model_copy(update={
        "resource_references": {"source_resource_id": ["account_referenced"]},
    })
    account_coverage = FileCoverage(
        file_id="account-snapshot", file_path="account_snapshot.sql",
        captured_at=instant("2025-12-23T00:00:00Z"),
        tables=["customer_profiles"], stores=["account_service"],
        observations=0, is_snapshot=True,
    )

    findings = CaseStateAnalyzer(
        ObservationIndex([source], [account_coverage]), [], RULES,
    ).analyze(request, subject)

    account_state = next(item for item in findings.resources if item.resource_id == "account_referenced")
    assert account_state.system_id == "account_service"
    assert account_state.state == "ABSENT"
    assert any(
        edge.edge_type == "explicit_resource_reference"
        and edge.provenance == "snapshot-evidence:source_resource_id"
        for edge in findings.link_edges
    )
    assert any(
        evidence.value == "account-snapshot"
        and evidence.role == "covered_store_absence"
        for evidence in account_state.evidence
    )


def test_expired_unreassigned_historical_identifier_links_stale_observation():
    domain = DOMAIN
    old_email = "old@" + domain
    current_email = "current@" + domain
    user = UserIdentity(
        user_id="user_subject", name="Subject", email=current_email, phone="",
        email_hash="", updated_at="2025-01-01T00:00:00Z",
    )
    audit = UserAuditEvent(
        audit_id="audit_email_change", user_id=user.user_id,
        event_time="2025-01-01T00:00:00Z", field_name="email",
        old_value=old_email, new_value=current_email,
    )
    request = DeletionRequest(
        case_id="".join(("synthetic", "case")), email=old_email,
        requested_at="2025-02-01T00:00:00Z", reported_status="COMPLETE",
        reported_at="2025-02-02T00:00:00Z", audit_at="2025-12-01T00:00:00Z",
        request_text="Please delete this account.",
    )
    subject = IdentityIndex([user], [audit]).resolve(request)
    observation = Observation(
        file_id="stale-evidence", captured_at=instant("2025-11-01T00:00:00Z"),
        system_id="search_service", resource_id="search_stale",
        data_category="SEARCH_INDEX_ENTRY",
        inherited_identifiers=[InheritedIdentifier(
            identifier_type="email", value=old_email,
            provenance="stale-evidence:lookup",
        )],
    )

    linked, matched = _observation_link(observation, subject, request.audit_at)

    assert linked
    assert any(item.identifier_type == "email" and item.value == old_email for item in matched)


def test_inherited_identifier_link_retains_context_edge_provenance():
    request, subject = setup_case()
    observation = Observation(
        file_id="context-evidence", captured_at=instant("2025-12-20T00:00:00Z"),
        system_id="account_service", resource_id="account_context",
        data_category="USER_PROFILE",
        inherited_identifiers=[InheritedIdentifier(
            identifier_type="email", value=subject.requested_email,
            provenance="context-evidence:shared_trace_id=trace-fixture",
        )],
        exists=False,
    )

    findings = CaseStateAnalyzer(ObservationIndex([observation], []), [], RULES).analyze(request, subject)

    assert [item.resource_id for item in findings.resources] == ["account_context"]
    assert any(
        edge.edge_type == "inherited_identifier"
        and edge.provenance == "context-evidence:shared_trace_id=trace-fixture"
        for edge in findings.link_edges
    )


def test_later_snapshot_contradicts_successful_delete_claim():
    request, subject = setup_case()
    observation = make_observation(captured="2025-12-22T00:00:00Z", exists=True)
    delete_claim = make_activity("activity-delete", "DELETE_RECORD", "2025-12-21T00:00:00Z")
    analyzer = CaseStateAnalyzer(ObservationIndex([observation], []), [delete_claim], RULES)

    findings = analyzer.analyze(request, subject)

    assert findings.resources[0].state == "PRESENT"
    assert findings.contradictions
    assert {item.kind for item in findings.contradictions[0].evidence} == {"activity_id", "file_id"}


def test_absence_uses_latest_snapshot_that_covers_the_resource_store():
    request, subject = setup_case()
    prior = make_observation(captured="2025-12-20T00:00:00Z", exists=True)
    prior_coverage = FileCoverage(
        file_id=prior.file_id, file_path="prior.sql", captured_at=prior.captured_at,
        tables=["search_documents"], stores=["search_service"], observations=1, is_snapshot=True,
    )
    later_coverage = FileCoverage(
        file_id="later-snapshot", file_path="later.sql", captured_at=instant("2025-12-23T00:00:00Z"),
        tables=["search_documents"], stores=["search_service"], observations=0, is_snapshot=True,
    )
    analyzer = CaseStateAnalyzer(ObservationIndex([prior], [prior_coverage, later_coverage]), [], RULES)

    findings = analyzer.analyze(request, subject)

    state = findings.resources[0]
    assert state.state == "ABSENT"
    assert state.captured_at == later_coverage.captured_at
    assert any(reference.value == "later-snapshot" and reference.role == "covered_store_absence" for reference in state.evidence)


def test_restore_allowed_without_a_deletion_block_is_a_restore_risk():
    request, subject = setup_case()
    backup = Observation(
        file_id="backup-snapshot", captured_at=instant("2025-12-20T00:00:00Z"),
        system_id="backup_service", resource_id="backup_fixture", data_category="BACKUP_ARCHIVE",
        identifiers_present={"user_id": ["user_subject"]}, exists=True,
        restore_allowed=True, restore_blocked=False, deletion_blocked=False,
    )
    coverage = FileCoverage(
        file_id=backup.file_id, file_path="backup_snapshot.sql", captured_at=backup.captured_at,
        tables=["backup_restore_entries"], stores=["backup_service"], observations=1, is_snapshot=True,
    )
    analyzer = CaseStateAnalyzer(ObservationIndex([backup], [coverage]), [], RULES)

    findings = analyzer.analyze(request, subject)

    assert findings.restore_risks == ("backup_fixture",)
    assert findings.resources[0].restore_risk


def test_unique_nearby_account_delete_links_only_to_snapshot_state():
    request, subject = setup_case()
    resource_id = "account_" + f"{uuid4().int % 1_000_000:06d}"
    activity = SystemActivity(
        activity_id="activity_account_delete",
        event_time=instant("2025-12-02T00:00:30Z"),
        event_type="DELETE_RECORD",
        source_system="deletion_worker",
        target_system="account_service",
        resource_id=resource_id,
        reported_result="SUCCESS",
        details="Deletion worker completed the requested operation.",
    )
    coverage = FileCoverage(
        file_id="account-snapshot",
        file_path="account_snapshot.sql",
        captured_at=instant("2025-12-20T00:00:00Z"),
        tables=["customer_profiles"],
        stores=["account_service"],
        observations=0,
        is_snapshot=True,
    )

    findings = CaseStateAnalyzer(ObservationIndex([], [coverage]), [activity], RULES).analyze(request, subject)

    assert len(findings.resources) == 1
    state = findings.resources[0]
    assert (state.resource_id, state.system_id, state.state) == (
        resource_id, "account_service", "ABSENT",
    )
    assert any(
        evidence.value == "account-snapshot" and evidence.role == "covered_store_absence"
        for evidence in state.evidence
    )
    assert any(
        edge.edge_type == "reported_at_proximity"
        and edge.provenance == activity.activity_id
        for edge in findings.link_edges
    )


def test_ambiguous_nearby_account_deletes_do_not_create_a_link():
    request, subject = setup_case()
    resource_ids = [
        "account_" + f"{uuid4().int % 1_000_000:06d}"
        for _ in range(2)
    ]
    activities = [
        SystemActivity(
            activity_id=f"activity_account_delete_{index}",
            event_time=instant(f"2025-12-02T00:00:{seconds:02d}Z"),
            event_type="DELETE_RECORD",
            source_system="deletion_worker",
            target_system="account_service",
            resource_id=resource_ids[index - 1],
            reported_result="SUCCESS",
            details="Deletion worker completed the requested operation.",
        )
        for index, seconds in ((1, 20), (2, 40))
    ]

    findings = CaseStateAnalyzer(ObservationIndex([], []), activities, RULES).analyze(request, subject)

    assert findings.resources == ()
    assert not any(edge.edge_type == "reported_at_proximity" for edge in findings.link_edges)
