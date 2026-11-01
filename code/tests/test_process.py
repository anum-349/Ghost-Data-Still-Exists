import json
import threading
from pathlib import Path
from uuid import uuid4

from ghost_data.data import DeletionRequest, DeletionRule, OutputRow, SystemActivity, load_csv
from ghost_data.identity import IdentityResolution
from ghost_data.observations import Observation, ObservationIndex
from ghost_data.process import CaseProcessor
from ghost_data.request_classifier import RequestClassification
from ghost_data.steps import Phase
from ghost_data.state import (
    CaseStateAnalyzer, CaseStateFindings, EvidencePointer, ResourceLinkEdge, ResourceState,
)


def test_not_applicable_returns_empty_steps_without_touching_pipeline():
    processor = CaseProcessor.__new__(CaseProcessor)
    processor.classifier = type("Classifier", (), {
        "classify": lambda self, text: RequestClassification(
            requests_deletion=False, confidence=1, reason="non-deletion request")
    })()
    request = DeletionRequest(case_id=uuid4().hex, email="", requested_at="2026-01-01T00:00:00Z",
        reported_status="NOT_STARTED", reported_at="2026-01-01T00:00:00Z",
        audit_at="2026-01-01T00:00:00Z", request_text="access my data")
    result = processor.process_case(request)
    assert isinstance(result, OutputRow)
    assert result.deletion_status == "NOT_APPLICABLE"
    assert result.steps_json == "[]"


def test_unresolved_case_is_logged_and_not_reported_complete(tmp_path):
    processor = CaseProcessor.__new__(CaseProcessor)
    request = DeletionRequest(
        case_id=uuid4().hex, email="", requested_at="2026-01-01T00:00:00Z",
        reported_status="COMPLETE", reported_at="2026-01-01T00:00:00Z",
        audit_at="2026-01-01T00:00:00Z", request_text="delete my account",
    )
    user_id = "user_" + uuid4().hex[:3]
    subject = IdentityResolution(
        requested_email="", as_of=request.requested_at, user_id=user_id,
        identifiers=(), matched_user_ids=(user_id,), collisions=(),
    )
    processor.classifier = type("Classifier", (), {
        "classify": lambda self, text: RequestClassification(
            requests_deletion=True, confidence=1, reason="deletion request")
    })()
    processor.identities = type("Identities", (), {"resolve": lambda self, item: subject})()
    processor.analyzer = type("Analyzer", (), {
        "analyze": lambda self, item, resolved: CaseStateFindings(
            case_id=item.case_id, audit_at=item.audit_at, reported_status_claim=item.reported_status,
        )
    })()
    processor.unresolved_log_path = tmp_path / ".local" / "unresolved_cases.jsonl"
    processor._unresolved_log_lock = threading.Lock()

    result = processor.process_case(request)

    assert result.deletion_status == "INCOMPLETE"
    assert result.steps_json == "[]"
    entries = [
        json.loads(line)
        for line in processor.unresolved_log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(entries) == 1
    assert entries[0]["case_id"] == request.case_id
    assert entries[0]["reason"] == "no_linked_resources"


def test_covered_store_absence_is_emitted_as_evidence_backed_verification():
    processor = CaseProcessor.__new__(CaseProcessor)
    request = DeletionRequest(
        case_id=uuid4().hex, email="", requested_at="2025-12-01T00:00:00Z",
        reported_status="COMPLETE", reported_at="2025-12-02T00:00:00Z",
        audit_at="2026-01-01T00:00:00Z", request_text="delete my account",
    )
    user_id = "user_" + uuid4().hex[:3]
    subject = IdentityResolution(
        requested_email="", as_of=request.requested_at, user_id=user_id,
        identifiers=(), matched_user_ids=(user_id,), collisions=(),
    )
    processor.classifier = type("Classifier", (), {
        "classify": lambda self, text: RequestClassification(
            requests_deletion=True, confidence=1, reason="deletion request")
    })()
    processor.identities = type("Identities", (), {"resolve": lambda self, item: subject})()
    resource_id = "account_" + f"{uuid4().int % 1_000_000:06d}"
    processor.analyzer = type("Analyzer", (), {
        "analyze": lambda self, item, resolved: CaseStateFindings(
            case_id=item.case_id,
            audit_at=item.audit_at,
            reported_status_claim=item.reported_status,
            resources=(ResourceState(
                system_id="account_service",
                resource_id=resource_id,
                data_category="",
                state="ABSENT",
                captured_at=item.audit_at,
                evidence=(EvidencePointer(
                    kind="file_id", value="account-snapshot", role="covered_store_absence",
                ),),
            ),),
            link_edges=(ResourceLinkEdge(
                source_resource=user_id,
                target_resource=resource_id,
                edge_type="reported_at_proximity",
                provenance=uuid4().hex,
                depth=0,
            ),),
        )
    })()
    processor.observations = type("ObservationIndex", (), {"by_resource_id": {}})()

    result = processor.process_case(request)

    assert result.deletion_status == "COMPLETE"
    steps = json.loads(result.steps_json)
    assert len(steps) == 1
    assert steps[0]["operation"] == "VERIFY_RECORD_ABSENT"
    assert steps[0]["resource_id"] == resource_id
    assert steps[0]["evidence_id"] == "account-snapshot"


def test_timing_linked_present_profile_gets_finding_remediation_and_verification():
    dataset = Path(__file__).resolve().parents[2] / "dataset"
    rules = load_csv(dataset / "deletion_rules.csv", DeletionRule)
    processor = CaseProcessor.__new__(CaseProcessor)
    resource_id = "account_" + f"{uuid4().int % 1_000_000:06d}"
    user_id = "user_" + uuid4().hex[:3]
    request = DeletionRequest(
        case_id=uuid4().hex, email="", requested_at="2025-12-01T00:00:00Z",
        reported_status="PARTIALLY_COMPLETE", reported_at="2025-12-02T00:00:00Z",
        audit_at="2026-01-01T00:00:00Z", request_text="delete my account",
    )
    subject = IdentityResolution(
        requested_email="", as_of=request.requested_at, user_id=user_id,
        identifiers=(), matched_user_ids=(user_id,), collisions=(),
    )
    observation = Observation(
        file_id="profile-evidence", captured_at="2025-12-20T00:00:00Z",
        system_id="account_service", resource_id=resource_id,
        data_category="USER_PROFILE", exists=True,
    )
    index = ObservationIndex([observation], [])
    activity = SystemActivity(
        activity_id="delete-claim", event_time="2025-12-02T00:00:30Z",
        event_type="DELETE_RECORD", source_system="deletion_worker",
        target_system="account_service", resource_id=resource_id,
        reported_result="SUCCESS", details="Deletion worker completed the operation.",
    )
    processor.classifier = type("Classifier", (), {
        "classify": lambda self, text: RequestClassification(
            requests_deletion=True, confidence=1, reason="deletion request")
    })()
    processor.identities = type("Identities", (), {"resolve": lambda self, item: subject})()
    processor.observations = index
    processor.analyzer = CaseStateAnalyzer(index, [activity], rules)

    result = processor.process_case(request)

    assert result.deletion_status == "INCOMPLETE"
    steps = json.loads(result.steps_json)
    assert [(step["phase"], step["operation"]) for step in steps] == [
        (Phase.FINDING, "REPORT_REMAINING_RECORD"),
        (Phase.REMEDIATION, "DELETE_RECORD"),
        (Phase.VERIFICATION, "VERIFY_RECORD_ABSENT"),
    ]
    assert steps[0]["evidence_id"] == observation.file_id
    assert all(not step["evidence_id"] for step in steps[1:])
