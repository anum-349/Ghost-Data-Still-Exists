"""Per-request evidence-backed state reconstruction at the inclusive audit cutoff."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .data import DeletionRequest, DeletionRule, SystemActivity, at_or_before
from .identity import IdentityResolution, Identifier
from .observations import FileCoverage, Observation, ObservationIndex, normalize_identifier
from .policy import PolicyAction, PolicyEngine


class EvidencePointer(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["file_id", "activity_id", "audit_id"]
    value: str
    role: str


class ActivityClaim(BaseModel):
    model_config = ConfigDict(frozen=True)

    activity_id: str
    event_time: datetime
    event_type: str
    reported_result: str
    resource_id: str
    after_snapshot: bool
    details: str


class StateContradiction(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim: str
    explanation: str
    evidence: tuple[EvidencePointer, ...]


class ResourceState(BaseModel):
    model_config = ConfigDict(frozen=True)

    system_id: str
    resource_id: str
    data_category: str
    state: Literal["PRESENT", "ABSENT", "UNKNOWN"]
    captured_at: datetime | None
    evidence: tuple[EvidencePointer, ...] = ()
    activity_claims: tuple[ActivityClaim, ...] = ()
    active_data_flow: bool = False
    restore_risk: bool = False
    contradictions: tuple[StateContradiction, ...] = ()


class CaseStateFindings(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    audit_at: datetime
    reported_status_claim: str
    resources: tuple[ResourceState, ...] = ()
    active_data_flows: tuple[str, ...] = ()
    restore_risks: tuple[str, ...] = ()
    contradictions: tuple[StateContradiction, ...] = ()


def _matched_identifier_values(subject: IdentityResolution) -> dict[str, set[str]]:
    stable = {subject.user_id} if subject.user_id else set()
    result: dict[str, set[str]] = {"user_id": stable, "stable_reference": stable.copy()}
    for item in subject.identifiers:
        result.setdefault(item.identifier_type, set()).add(normalize_identifier(item.identifier_type, item.value))
    return result


def _identity_support(subject: IdentityResolution, matched: list[Identifier]) -> list[EvidencePointer]:
    refs = []
    for identifier in matched:
        for provenance in identifier.provenance:
            audit_match = re.search(r"audit:([^:]+):", provenance)
            if audit_match:
                refs.append(EvidencePointer(kind="audit_id", value=audit_match.group(1), role="identifier_history_link"))
    return refs


def _observation_link(observation: Observation, subject: IdentityResolution, cutoff: datetime) -> tuple[bool, list[Identifier]]:
    if not subject.user_id:
        return False, []
    values = _matched_identifier_values(subject)
    matched: list[Identifier] = []
    for kind, observed in observation.identifiers_present.items():
        expected = values.get(kind, set())
        if any(normalize_identifier(kind, value) in expected for value in observed):
            matched.extend(
                item for item in subject.identifiers
                if item.identifier_type == kind
                and normalize_identifier(kind, item.value) in {normalize_identifier(kind, value) for value in observed}
            )
            if kind == "stable_reference" and subject.user_id and normalize_identifier(kind, subject.user_id) in {
                normalize_identifier(kind, value) for value in observed
            }:
                matched.extend(item for item in subject.identifiers if item.identifier_type == "user_id")
            if kind == "user_id" and subject.user_id in observed:
                matched.extend(item for item in subject.identifiers if item.identifier_type == "user_id")
    # Historical identifiers remain useful for locating stale copies. If a
    # value was reassigned, require that it belonged to this subject when the
    # evidence was captured to avoid attributing the new owner's record.
    if matched:
        collision_values = {(item.identifier_type, normalize_identifier(item.identifier_type, item.value)) for collision in subject.collisions for item in subject.identifiers if item.identifier_type == collision.identifier_type and normalize_identifier(item.identifier_type, item.value) == collision.value}
        valid = []
        for identifier in matched:
            key = (identifier.identifier_type, normalize_identifier(identifier.identifier_type, identifier.value))
            if key not in collision_values or identifier.valid_at(observation.captured_at):
                valid.append(identifier)
        return bool(valid), valid
    return False, []


def _activity_link(activity: SystemActivity, subject: IdentityResolution) -> bool:
    haystack = f"{activity.resource_id} {activity.details}".casefold()
    values = _matched_identifier_values(subject)
    for kind, identifiers in values.items():
        for value in identifiers:
            if not value:
                continue
            if kind == "phone":
                phones = re.findall(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)", haystack)
                if value and any(re.sub(r"\D", "", phone) == value for phone in phones):
                    return True
            elif re.search(r"(?<![\w])" + re.escape(value) + r"(?![\w])", haystack, re.I):
                return True
    return False


def _resource_ids_in(text: str) -> set[str]:
    return set(re.findall(r"\b(?:account|search|analytics|support|export|backup|audit_record|data_flow|tombstone|marketing|object|cache|delivery|notification)_[A-Za-z0-9_-]+\b", text, re.I))


class CaseStateAnalyzer:
    """Link subject observations, select governing evidence, and apply later claims."""

    def __init__(self, index: ObservationIndex, activities: list[SystemActivity], rules: list[DeletionRule]) -> None:
        self.index = index
        self.activities = activities
        self.policy = PolicyEngine(rules)

    def analyze(self, request: DeletionRequest, subject: IdentityResolution) -> CaseStateFindings:
        cutoff = request.audit_at
        linked: dict[str, tuple[set[str], list[Identifier]]] = {}
        for observation in self.index.observations:
            if not at_or_before(observation.captured_at, cutoff):
                continue
            is_linked, identifiers = _observation_link(observation, subject, cutoff)
            if is_linked:
                systems, matched = linked.setdefault(observation.resource_id, (set(), []))
                systems.add(observation.system_id)
                matched.extend(identifiers)

        relevant_activities: dict[str, list[SystemActivity]] = {}
        for activity in self.activities:
            if not at_or_before(activity.event_time, cutoff):
                continue
            linked_to_subject = _activity_link(activity, subject)
            resource_refs = {activity.resource_id, *_resource_ids_in(activity.details)}
            if linked_to_subject:
                for resource in resource_refs:
                    if resource:
                        linked.setdefault(resource, ({activity.target_system or activity.source_system}, []))
            for resource in resource_refs:
                if resource in linked:
                    relevant_activities.setdefault(resource, []).append(activity)

        states: list[ResourceState] = []
        top_contradictions: list[StateContradiction] = []
        active_flows: set[str] = set()
        restore_risks: set[str] = set()
        for resource_id, (systems, matched_ids) in sorted(linked.items()):
            resource_contradictions: list[StateContradiction] = []
            candidates: list[tuple[datetime, str, Observation | FileCoverage, str]] = []
            resource_obs = [
                item for item in self.index.by_resource_id.get(resource_id, [])
                if at_or_before(item.captured_at, cutoff)
                and (not systems or item.system_id in systems)
            ]
            observed_systems = systems or {item.system_id for item in resource_obs if item.system_id}
            for item in resource_obs:
                candidates.append((item.captured_at, "observation", item, "PRESENT" if item.exists is not False else "ABSENT"))
            for coverage in self.index.coverage.values():
                if not at_or_before(coverage.captured_at, cutoff):
                    continue
                if not coverage.is_snapshot:
                    continue
                for system_id in observed_systems:
                    if coverage.covers_store(system_id) and not any(item.file_id == coverage.file_id for item in resource_obs):
                        candidates.append((coverage.captured_at, "coverage", coverage, "ABSENT"))
            if candidates:
                latest_time = max(item[0] for item in candidates)
                latest = [item for item in candidates if item[0] == latest_time]
                states_here = {item[3] for item in latest}
                resource_state = next(iter(states_here)) if len(states_here) == 1 else "UNKNOWN"
                governing_evidence = []
                governing_observations = []
                for _, kind, source, _state in latest:
                    if kind == "observation":
                        obs = source
                        governing_observations.append(obs)
                        governing_evidence.append(EvidencePointer(kind="file_id", value=obs.file_id, role="governing_observation"))
                    else:
                        coverage = source
                        governing_evidence.append(EvidencePointer(kind="file_id", value=coverage.file_id, role="covered_store_absence"))
            else:
                latest_time = None
                governing_observations = []
                governing_evidence = []
                resource_state = "UNKNOWN"

            post_snapshot_events: list[ActivityClaim] = []
            resource_events = relevant_activities.get(resource_id, [])
            for event in resource_events:
                after_snapshot = latest_time is None or event.event_time > latest_time
                if after_snapshot:
                    post_snapshot_events.append(ActivityClaim(
                        activity_id=event.activity_id, event_time=event.event_time,
                        event_type=event.event_type, reported_result=event.reported_result,
                        resource_id=event.resource_id, after_snapshot=True, details=event.details,
                    ))
                else:
                    expected = _successful_event_state(event)
                    if expected and event.reported_result == "SUCCESS" and resource_state != expected:
                        contradiction = StateContradiction(
                            claim=f"{event.event_type} reported SUCCESS",
                            explanation=f"A later observation says {resource_state.lower()}, contrary to the activity's claimed {expected.lower()} result.",
                            evidence=(EvidencePointer(kind="activity_id", value=event.activity_id, role="activity_claim"), *governing_evidence),
                        )
                        top_contradictions.append(contradiction)
                        resource_contradictions.append(contradiction)

            is_flow = any(
                (obs.enabled_active is True or obs.scheduled is True)
                for obs in governing_observations
            )
            flow_events = [
                event for event in resource_events
                if event.event_type in {"SYNC_RECORD", "CREATE_EXPORT"}
                and (latest_time is None or event.event_time > latest_time)
            ]
            flow_at_risk = is_flow or bool(flow_events)
            if flow_at_risk:
                active_flows.add(resource_id)
                governing_evidence.extend(EvidencePointer(kind="activity_id", value=event.activity_id, role="recreation_activity") for event in flow_events)

            backup_obs = [obs for obs in governing_observations if obs.data_category == "BACKUP_ARCHIVE" or "backup" in obs.resource_id.casefold()]
            backup_risk = any(
                (obs.restore_allowed is True or obs.restore_blocked is False)
                and obs.restore_blocked is not True and obs.deletion_blocked is not True
                for obs in backup_obs
            ) or any(
                event.event_type == "RESTORE_BACKUP"
                and (latest_time is None or event.event_time > latest_time)
                for event in resource_events
            )
            if backup_risk:
                restore_risks.add(resource_id)
                governing_evidence.extend(EvidencePointer(kind="activity_id", value=event.activity_id, role="restore_activity") for event in resource_events if event.event_type == "RESTORE_BACKUP")

            # A COMPLETE workflow claim conflicts only with policy violations
            # proven by current evidence; activity outcomes alone never settle it.
            if request.reported_status == "COMPLETE" and resource_state == "PRESENT":
                for obs in governing_observations:
                    if obs.data_category not in self.policy.rules:
                        continue
                    decision = self.policy.evaluate(obs, subject=subject, at=cutoff)
                    if decision.action in {PolicyAction.DELETE, PolicyAction.REDACT, PolicyAction.ANONYMIZE, PolicyAction.BLOCK_RESTORE}:
                        contradiction = StateContradiction(
                            claim="reported_status=COMPLETE",
                            explanation=f"Evidence shows a present resource requiring {decision.action.value}.",
                            evidence=tuple(governing_evidence),
                        )
                        top_contradictions.append(contradiction)
                        resource_contradictions.append(contradiction)
                        break
            if request.reported_status == "COMPLETE" and (flow_at_risk or backup_risk):
                kind = "active data flow" if flow_at_risk else "restore risk"
                contradiction = StateContradiction(
                    claim="reported_status=COMPLETE",
                    explanation=f"Evidence indicates an unresolved {kind} that can recreate or restore data.",
                    evidence=tuple(governing_evidence),
                )
                top_contradictions.append(contradiction)
                resource_contradictions.append(contradiction)

            # Include audit provenance for the identifiers that linked this subject.
            governing_evidence.extend(_identity_support(subject, matched_ids))
            distinct_evidence = tuple(dict.fromkeys(governing_evidence))
            states.append(ResourceState(
                system_id=sorted(systems)[0] if systems else (governing_observations[0].system_id if governing_observations else ""),
                resource_id=resource_id,
                data_category=(governing_observations or resource_obs)[0].data_category if (governing_observations or resource_obs) else "",
                state=resource_state, captured_at=latest_time,
                evidence=distinct_evidence, activity_claims=tuple(post_snapshot_events),
                active_data_flow=flow_at_risk, restore_risk=backup_risk,
                contradictions=tuple(resource_contradictions),
            ))

        return CaseStateFindings(
            case_id=request.case_id, audit_at=cutoff,
            reported_status_claim=request.reported_status,
            resources=tuple(states), active_data_flows=tuple(sorted(active_flows)),
            restore_risks=tuple(sorted(restore_risks)), contradictions=tuple(top_contradictions),
        )


def _successful_event_state(event: SystemActivity) -> str | None:
    if event.event_type == "DELETE_RECORD":
        return "ABSENT"
    if event.event_type in {"SYNC_RECORD", "CREATE_EXPORT"}:
        return "PRESENT"
    return None
