"""Deletion policy evaluation driven by deletion_rules.csv and observations."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Callable

from pydantic import BaseModel, ConfigDict

from .data import DeletionRule
from .identity import IdentityResolution
from .observations import Observation, normalize_identifier


class PolicyAction(StrEnum):
    DELETE = "DELETE"
    REDACT = "REDACT"
    ANONYMIZE = "ANONYMIZE"
    RETAIN = "RETAIN"
    BLOCK_RESTORE = "BLOCK_RESTORE"
    NO_ACTION = "NO_ACTION"
    REVIEW = "REVIEW"


class PolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_category: str
    action: PolicyAction
    condition_met: bool | None
    reason: str
    retain_record: bool = False
    preserve_identifiers: tuple[str, ...] = ()
    clear_identifiers: tuple[str, ...] = ()


Evaluator = Callable[[DeletionRule, Observation, IdentityResolution | None, datetime | None], PolicyDecision]


def _decision(rule: DeletionRule, action: PolicyAction, matched: bool | None, reason: str, **kwargs) -> PolicyDecision:
    return PolicyDecision(data_category=rule.data_category, action=action, condition_met=matched, reason=reason, **kwargs)


def _matches_subject(observation: Observation, subject: IdentityResolution | None) -> bool | None:
    if subject is None or subject.user_id is None:
        return None
    candidate_values: dict[str, set[str]] = {"user_id": {subject.user_id}}
    for identifier in subject.identifiers:
        candidate_values.setdefault(identifier.identifier_type, set()).add(
            normalize_identifier(identifier.identifier_type, identifier.value)
        )
    for kind, observed_values in observation.identifiers_present.items():
        expected = candidate_values.get(kind, set())
        if any(normalize_identifier(kind, value) in expected for value in observed_values):
            return True
    return False


def _always(rule: DeletionRule, observation: Observation, subject: IdentityResolution | None, at: datetime | None) -> PolicyDecision:
    return _decision(rule, PolicyAction(rule.required_action), True, "The policy condition is Always.")


def _support_message(rule, observation, subject, at):
    shared = observation.shared_context is True
    if observation.shared_context is None:
        direct = {"name", "email", "phone", "email_hash"}.intersection(observation.identifiers_present)
        if not direct:
            return _decision(
                rule, PolicyAction.REDACT, False,
                "Shared context is not established and direct identifiers are already absent; preserve the compliant redacted record.",
                retain_record=True,
            )
    action = PolicyAction(rule.required_action) if shared else PolicyAction.DELETE
    return _decision(rule, action, shared, "Shared conversation context must be retained with identifying fields redacted." if shared else "No shared customer, agent, or order context is indicated; delete the message.", retain_record=shared)


def _support_attachment(rule, observation, subject, at):
    only_subject = observation.belongs_only_to_subject
    if only_subject is None:
        linked = _matches_subject(observation, subject)
        if linked is not None:
            only_subject = linked and observation.shared_context is not True
    if only_subject is True:
        return _decision(rule, PolicyAction(rule.required_action), True, "The attachment is linked to this subject and has no shared-context flag.")
    if only_subject is False:
        return _decision(rule, PolicyAction.NO_ACTION, False, "The attachment is not exclusive to the deletion subject under the supplied evidence.")
    return _decision(rule, PolicyAction.REVIEW, None, "Evidence does not establish whether the attachment belongs only to this subject.")


def _attributability(rule, observation, subject, at):
    attributable = observation.attributable
    if attributable is None:
        attributable = observation.identifiable
    if attributable is None:
        attributable = _matches_subject(observation, subject)
    if attributable:
        return _decision(rule, PolicyAction(rule.required_action), True, "The record remains attributable to the subject.")
    if observation.anonymized is True or attributable is False:
        return _decision(rule, PolicyAction.NO_ACTION, False, "The record is already anonymized or no longer attributable.")
    return _decision(rule, PolicyAction.REVIEW, None, "The evidence does not establish whether the record remains attributable.")


def _email_delivery(rule, observation, subject, at):
    contains_email = bool(observation.identifiers_present.get("email"))
    if contains_email:
        return _decision(rule, PolicyAction(rule.required_action), True, "The delivery log contains an email address and must be redacted.", retain_record=True, clear_identifiers=("email",))
    return _decision(rule, PolicyAction.NO_ACTION, False, "No email address is present in the delivery-log observation.")


def _security_audit(rule, observation, subject, at):
    within = observation.within_retention
    if within is None and observation.retention_until is not None and at is not None:
        within = at <= observation.retention_until
    if within is True:
        return _decision(rule, PolicyAction(rule.required_action), True, "The audit record is within its supplied retention period.", retain_record=True)
    if within is False:
        return _decision(rule, PolicyAction.DELETE, False, "The supplied retention period has expired; the record is eligible for deletion.")
    return _decision(rule, PolicyAction.REVIEW, None, "No retention deadline or within-retention fact is available.")


def _legal_hold(rule, observation, subject, at):
    active = observation.legal_hold_active
    if active is True:
        return _decision(rule, PolicyAction(rule.required_action), True, "A supplied legal hold is active.", retain_record=True)
    if active is False:
        return _decision(rule, PolicyAction.DELETE, False, "The evidence says no legal hold is active.")
    return _decision(rule, PolicyAction.REVIEW, None, "The evidence does not establish whether a legal hold is active.")


def _backup(rule, observation, subject, at):
    if observation.restore_blocked is True or observation.deletion_blocked is True or observation.restore_allowed is False:
        return _decision(rule, PolicyAction(rule.required_action), True, "The archive is retained and restore access is already blocked.", retain_record=True, preserve_identifiers=("user_id",))
    if observation.restore_access_blockable is True or observation.restore_allowed is True:
        return _decision(rule, PolicyAction.BLOCK_RESTORE, True, "Retain the archive and block restore access before dependent cleanup.", retain_record=True, preserve_identifiers=("user_id",))
    if observation.restore_access_blockable is False:
        return _decision(rule, PolicyAction.REVIEW, False, "The supplied condition for blocking restore access is not met.", retain_record=True, preserve_identifiers=("user_id",))
    return _decision(rule, PolicyAction.REVIEW, None, "Evidence does not establish whether restore access can be blocked.", retain_record=True, preserve_identifiers=("user_id",))


def _tombstone(rule, observation, subject, at):
    prohibited = {"name", "email", "phone", "email_hash"}
    present = prohibited.intersection(observation.identifiers_present)
    preserve = ("user_id",) if (
        observation.identifiers_present.get("user_id")
        or observation.identifiers_present.get("stable_reference")
        or _matches_subject(observation, subject)
    ) else ()
    if present:
        return _decision(rule, PolicyAction(rule.required_action), True, "Keep the tombstone's stable user reference and redact direct identifiers.", retain_record=True, preserve_identifiers=preserve, clear_identifiers=tuple(sorted(present)))
    if preserve:
        return _decision(rule, PolicyAction.RETAIN, True, "The tombstone contains only the permitted stable user reference.", retain_record=True, preserve_identifiers=preserve)
    return _decision(rule, PolicyAction.REVIEW, None, "The evidence does not establish the tombstone's stable subject reference.", retain_record=True)


CONDITION_EVALUATORS: dict[str, Evaluator] = {
    "Always": _always,
    "Conversation contains shared customer, agent, or order context that must be retained": _support_message,
    "Attachment belongs only to the deletion subject": _support_attachment,
    "Record is still attributable to a user": _attributability,
    "Log contains a user email address": _email_delivery,
    "Record is within the supplied retention period": _security_audit,
    "A supplied legal hold is active": _legal_hold,
    "Restore access can be blocked": _backup,
    "Account is deleted and only a stable internal user_id is needed to preserve references to retained records": _tombstone,
}


class PolicyEngine:
    """Evaluate each observation using conditions/actions loaded from the CSV."""

    def __init__(self, rules: list[DeletionRule]) -> None:
        self.rules = {rule.data_category: rule for rule in rules}
        if len(self.rules) != len(rules):
            raise ValueError("deletion_rules.csv contains duplicate data_category values")
        unsupported = [rule.condition for rule in rules if rule.condition not in CONDITION_EVALUATORS]
        if unsupported:
            raise ValueError(f"no evaluator for deletion policy condition(s): {unsupported}")

    def evaluate(
        self,
        observation: Observation,
        *,
        subject: IdentityResolution | None = None,
        at: datetime | None = None,
    ) -> PolicyDecision:
        rule = self.rules.get(observation.data_category)
        if rule is None:
            raise KeyError(f"no deletion rule for category {observation.data_category!r}")
        evaluator = CONDITION_EVALUATORS[rule.condition]
        return evaluator(rule, observation, subject, at)

    def evaluate_all(self, observations: list[Observation], *, subject: IdentityResolution | None = None, at: datetime | None = None) -> list[PolicyDecision]:
        return [self.evaluate(item, subject=subject, at=at) for item in observations]
