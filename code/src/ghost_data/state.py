"""Per-request evidence-backed state reconstruction at the inclusive audit cutoff."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .data import DeletionRequest, DeletionRule, SystemActivity, at_or_before
from .identity import IdentityResolution, Identifier
from .observations import FileCoverage, Observation, ObservationIndex, normalize_identifier, system_for_resource
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


class ResourceLinkEdge(BaseModel):
    """A traversed resource relationship with its source artifact and match key."""
    model_config = ConfigDict(frozen=True)
    source_resource: str
    target_resource: str
    edge_type: str
    provenance: str
    depth: int


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
    link_edges: tuple[ResourceLinkEdge, ...] = ()


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
    observed_by_kind = {kind: list(observed) for kind, observed in observation.identifiers_present.items()}
    for identifier in observation.inherited_identifiers:
        observed_by_kind.setdefault(identifier.identifier_type, []).append(identifier.value)
    matched: list[Identifier] = []
    for kind, observed in observed_by_kind.items():
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
    reserved = {"service", "platform", "storage", "replica", "primary", "secondary", "read", "reporting"}
    found = set(re.findall(r"\b(?:account|search|analytics|support|export|backup|audit_record|data_flow|tombstone|marketing|object|cache|delivery|notification)_[A-Za-z0-9_-]+\b(?!\.(?:pdf|png|jpe?g|csv|json|txt|sql)\b)", text, re.I))
    return {item for item in found if item.rsplit("_", 1)[-1].casefold() not in reserved}


class CaseStateAnalyzer:
    """Link subject observations, select governing evidence, and apply later claims."""

    def __init__(self, index: ObservationIndex, activities: list[SystemActivity], rules: list[DeletionRule]) -> None:
        self.index = index
        self.activities = activities
        self.policy = PolicyEngine(rules)

    def analyze(self, request: DeletionRequest, subject: IdentityResolution) -> CaseStateFindings:
        cutoff = request.audit_at
        observations = [o for o in self.index.observations if at_or_before(o.captured_at, cutoff)]
        by_resource: dict[str, list[Observation]] = {}
        for obs in observations:
            by_resource.setdefault(obs.resource_id, []).append(obs)
        # Graph edges only use explicit user identity, recognized shared business
        # references, or resource co-mentions in a timestamp-valid activity.
        graph: dict[str, list[tuple[str, ResourceLinkEdge]]] = {}
        def edge(left: str, right: str, kind: str, source: str) -> None:
            if not left or not right or left == right:
                return
            item = ResourceLinkEdge(source_resource=left, target_resource=right,
                                    edge_type=kind, provenance=source, depth=0)
            graph.setdefault(left, []).append((right, item))
            graph.setdefault(right, []).append((left, item.model_copy(update={"source_resource": right, "target_resource": left})))

        for obs in observations:
            for field, referenced_resources in obs.resource_references.items():
                for referenced_resource in referenced_resources:
                    edge(
                        obs.resource_id,
                        referenced_resource,
                        "explicit_resource_reference",
                        f"{obs.file_id}:{field}",
                    )

        shared: dict[tuple[str, str], list[Observation]] = {}
        for obs in observations:
            for key, vals in obs.shared_references.items():
                for value in vals:
                    shared.setdefault((key, normalize_identifier(key, value)), []).append(obs)
        for (key, value), members in shared.items():
            # A reference used by many records is not discriminative enough to
            # safely join them; order/ticket/conversation references are scoped.
            unique = {m.resource_id: m for m in members}
            if 1 < len(unique) <= 8:
                ids = sorted(unique)
                for i, left in enumerate(ids):
                    for right in ids[i + 1:]:
                        edge(left, right, "shared_reference", f"{unique[left].file_id}:{key}={value}")

        relevant_activities: dict[str, list[SystemActivity]] = {}
        seed_provenance: dict[str, set[str]] = {}
        timing_link_events: dict[str, SystemActivity] = {}
        has_linked_account_observation = any(
            re.fullmatch(r"account_\d+", observation.resource_id, re.I)
            and _observation_link(observation, subject, cutoff)[0]
            for observation in observations
        )
        if not has_linked_account_observation and at_or_before(request.reported_at, cutoff):
            nearby_account_deletes = [
                activity
                for activity in self.activities
                if activity.event_type == "DELETE_RECORD"
                and activity.target_system == "account_service"
                and re.fullmatch(r"account_\d+", activity.resource_id, re.I)
                and at_or_before(activity.event_time, cutoff)
                and abs((activity.event_time - request.reported_at).total_seconds()) <= 60
            ]
            resources = {activity.resource_id for activity in nearby_account_deletes}
            if len(resources) == 1:
                resource_id = next(iter(resources))
                timing_link_events[resource_id] = min(
                    (activity for activity in nearby_account_deletes if activity.resource_id == resource_id),
                    key=lambda activity: (
                        abs((activity.event_time - request.reported_at).total_seconds()),
                        activity.event_time,
                        activity.activity_id,
                    ),
                )
        for activity in self.activities:
            if not at_or_before(activity.event_time, cutoff):
                continue
            refs = sorted({x for x in (*_resource_ids_in(activity.resource_id), *_resource_ids_in(activity.details)) if x})
            identity_link = _activity_link(activity, subject)
            if identity_link or activity.event_type == "LINK_RESOURCE_IDENTITY":
                for i, left in enumerate(refs):
                    for right in refs[i + 1:]:
                        edge(left, right, "activity_resource_mention", activity.activity_id)
            if identity_link:
                for resource in refs:
                    # Identity-link events and explicit identity matches are
                    # direct graph seeds, represented as a self-provenance edge.
                    graph.setdefault(resource, [])
                    seed_provenance.setdefault(resource, set()).add(activity.activity_id)
            for resource in refs:
                relevant_activities.setdefault(resource, []).append(activity)

        linked: dict[str, tuple[set[str], list[Identifier]]] = {}
        queue: list[tuple[str, int]] = []
        context_edges: list[ResourceLinkEdge] = []
        for obs in observations:
            is_linked, identifiers = _observation_link(obs, subject, cutoff)
            if is_linked:
                queue.append((obs.resource_id, 0))
                seed_provenance.setdefault(obs.resource_id, set()).add(obs.file_id)
                systems, matched = linked.setdefault(obs.resource_id, (set(), []))
                systems.add(obs.system_id); matched.extend(identifiers)
                matched_keys = {
                    (item.identifier_type, normalize_identifier(item.identifier_type, item.value))
                    for item in identifiers
                }
                for inherited in obs.inherited_identifiers:
                    key = (
                        inherited.identifier_type,
                        normalize_identifier(inherited.identifier_type, inherited.value),
                    )
                    if key in matched_keys:
                        context_edges.append(ResourceLinkEdge(
                            source_resource=subject.user_id or "",
                            target_resource=obs.resource_id,
                            edge_type="inherited_identifier",
                            provenance=inherited.provenance,
                            depth=0,
                        ))
        for resource, activity in timing_link_events.items():
            systems = {observation.system_id for observation in by_resource.get(resource, []) if observation.system_id}
            if not systems and activity.target_system:
                systems.add(activity.target_system)
            linked.setdefault(resource, (systems, []))
            seed_provenance.setdefault(resource, set()).add(activity.activity_id)
            queue.append((resource, 0))
        for resource in seed_provenance:
            if not by_resource.get(resource):
                linked.setdefault(resource, ({""}, []))
        # Direct event-to-identity relations are seeds even when the resource
        # itself has no observation record.
        for resource in seed_provenance:
            if not any(x[0] == resource for x in queue):
                queue.append((resource, 0))
        max_depth = 3
        visited_depth: dict[str, int] = {}
        traversed: list[ResourceLinkEdge] = []
        traversed.extend(context_edges)
        traversed.extend(
            ResourceLinkEdge(
                source_resource=subject.user_id or "",
                target_resource=resource,
                edge_type="reported_at_proximity",
                provenance=activity.activity_id,
                depth=0,
            )
            for resource, activity in timing_link_events.items()
        )
        while queue:
            resource, depth = queue.pop(0)
            if resource in visited_depth and visited_depth[resource] <= depth:
                continue
            visited_depth[resource] = depth
            if depth >= max_depth:
                continue
            for target, relation in graph.get(resource, []):
                traversed.append(relation.model_copy(update={"depth": depth + 1}))
                target_systems = {o.system_id for o in by_resource.get(target, []) if o.system_id}
                if not target_systems and relation.edge_type == "explicit_resource_reference":
                    inferred_system = system_for_resource(target)
                    if inferred_system:
                        target_systems.add(inferred_system)
                linked.setdefault(target, (target_systems, []))
                queue.append((target, depth + 1))
        # Keep all identifier evidence for every reached record, with temporal
        # collision checks, so policy uses the actual capture-time contents.
        for resource_id in linked:
            systems, matched = linked[resource_id]
            for obs in by_resource.get(resource_id, []):
                ok, ids = _observation_link(obs, subject, cutoff)
                if ok:
                    matched.extend(ids)

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

            # Identity-link claims can connect a resource node without proving
            # that a record exists. Keep unknown nodes only when independent
            # activity establishes an active flow or restore risk.
            if resource_state == "UNKNOWN" and not flow_at_risk and not backup_risk:
                continue

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
            link_edges=tuple(traversed),
        )


def _successful_event_state(event: SystemActivity) -> str | None:
    if event.event_type == "DELETE_RECORD":
        return "ABSENT"
    if event.event_type in {"SYNC_RECORD", "CREATE_EXPORT"}:
        return "PRESENT"
    return None
