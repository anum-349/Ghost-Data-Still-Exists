"""Temporal identity resolution from current identity and audit CSV records."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .data import DeletionRequest, UserAuditEvent, UserIdentity


FIELD_TYPES = {
    "email": "email",
    "phone": "phone",
    "name": "name",
    "full_name": "name",
    "email_hash": "email_hash",
}
IDENTIFIER_TYPES = ("email", "phone", "name", "email_hash", "user_id")


def _normalize(kind: str, value: str) -> str:
    if kind == "phone":
        return re.sub(r"\D", "", value)
    if kind == "name":
        return " ".join(value.casefold().split())
    return value.casefold().strip()


class Identifier(BaseModel):
    model_config = ConfigDict(frozen=True)

    identifier_type: str
    value: str
    user_id: str
    provenance: tuple[str, ...]
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    def valid_at(self, timestamp: datetime) -> bool:
        """Intervals are half-open [valid_from, valid_until)."""
        return (self.valid_from is None or self.valid_from <= timestamp) and (
            self.valid_until is None or timestamp < self.valid_until
        )


class IdentityCollision(BaseModel):
    model_config = ConfigDict(frozen=True)

    identifier_type: str
    value: str
    user_ids: tuple[str, ...]
    valid_from: datetime | None
    valid_until: datetime | None
    overlaps: bool
    owner_intervals: tuple[tuple[str, datetime | None, datetime | None], ...]


class IdentityResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    requested_email: str
    as_of: datetime
    user_id: str | None
    identifiers: tuple[Identifier, ...]
    matched_user_ids: tuple[str, ...]
    collisions: tuple[IdentityCollision, ...]

    @property
    def ambiguous(self) -> bool:
        return len(self.matched_user_ids) > 1


class IdentityIndex:
    """Index subject identifiers and their validity/provenance intervals."""

    def __init__(
        self,
        identities: list[UserIdentity],
        audit_events: list[UserAuditEvent],
        *,
        email_hash_scheme_confirmed: bool = True,
    ) -> None:
        """Build temporal identifier sets.

        The dataset notes confirm email_hash == SHA-256(lowercase(email)) for
        all current identity rows; disable derivation only when using another
        dataset whose hash contract has not been confirmed.
        """
        self.identifiers: dict[str, list[Identifier]] = defaultdict(list)
        self.email_hash_scheme_confirmed = email_hash_scheme_confirmed
        current_by_user = {row.user_id: row for row in identities}
        events_by_field: dict[tuple[str, str], list[UserAuditEvent]] = defaultdict(list)
        for event in audit_events:
            kind = FIELD_TYPES.get(event.field_name)
            if kind:
                events_by_field[(event.user_id, kind)].append(event)

        # Reconstruct transitions as adjacent half-open intervals.
        for (user_id, kind), events in events_by_field.items():
            ordered = sorted(events, key=lambda event: (event.event_time, event.audit_id))
            for index, event in enumerate(ordered):
                prior = ordered[index - 1].event_time if index else None
                self._add(user_id, kind, event.old_value, prior, event.event_time, f"audit:{event.audit_id}:old_value")
                following = ordered[index + 1].event_time if index + 1 < len(ordered) else None
                self._add(user_id, kind, event.new_value, event.event_time, following, f"audit:{event.audit_id}:new_value")

        for user_id, row in current_by_user.items():
            self._add(user_id, "user_id", user_id, None, None, "user_identities:user_id")
            for field in ("email", "phone", "name", "email_hash"):
                value = getattr(row, field)
                if not value:
                    continue
                kind = field
                matching = [
                    event for event in events_by_field.get((user_id, kind), [])
                    if event.new_value == value
                ]
                starts = max((event.event_time for event in matching), default=None)
                self._add(user_id, kind, value, starts, None, f"user_identities:{field}")

        if email_hash_scheme_confirmed:
            email_identifiers = [x for values in self.identifiers.values() for x in values if x.identifier_type == "email"]
            for item in email_identifiers:
                digest = hashlib.sha256(item.value.lower().encode("utf-8")).hexdigest()
                self._add(
                    item.user_id, "email_hash", digest, item.valid_from, item.valid_until,
                    "derived:sha256(lowercase(email))",
                )
        self.collisions = self._find_collisions()

    def _add(
        self, user_id: str, kind: str, value: str, start: datetime | None,
        end: datetime | None, source: str,
    ) -> None:
        if not value:
            return
        self.identifiers[user_id].append(Identifier(
            identifier_type=kind,
            value=value,
            user_id=user_id,
            provenance=(source,),
            valid_from=start,
            valid_until=end,
        ))

    def _find_collisions(self) -> list[IdentityCollision]:
        grouped: dict[tuple[str, str], list[tuple[str, Identifier]]] = defaultdict(list)
        for user_id, identifiers in self.identifiers.items():
            for item in identifiers:
                if item.identifier_type == "user_id":
                    continue
                grouped[(item.identifier_type, _normalize(item.identifier_type, item.value))].append((user_id, item))
        found = []
        for (kind, value), entries in grouped.items():
            for index, (user_a, a) in enumerate(entries):
                for user_b, b in entries[index + 1:]:
                    if user_a == user_b:
                        continue
                    start = max((x for x in (a.valid_from, b.valid_from) if x is not None), default=None)
                    ends = [x for x in (a.valid_until, b.valid_until) if x is not None]
                    end = min(ends) if ends else None
                    overlaps = end is None or start is None or start < end
                    found.append(IdentityCollision(
                        identifier_type=kind, value=value,
                        user_ids=tuple(sorted({user_a, user_b})),
                        valid_from=start if overlaps else None,
                        valid_until=end if overlaps else None,
                        overlaps=overlaps,
                        owner_intervals=(
                            (user_a, a.valid_from, a.valid_until),
                            (user_b, b.valid_from, b.valid_until),
                        ),
                    ))
        return found

    def resolve(self, request: DeletionRequest) -> IdentityResolution:
        email_key = _normalize("email", request.email)
        matching_users = set()
        for user_id, identifiers in self.identifiers.items():
            if any(
                item.identifier_type == "email"
                and _normalize("email", item.value) == email_key
                and item.valid_at(request.requested_at)
                for item in identifiers
            ):
                matching_users.add(user_id)
        matched = tuple(sorted(matching_users))
        # A stale historical address remains a useful lookup when it has a
        # single recorded owner and nobody else held it at request time.
        if not matched:
            historical_users = {
                user_id for user_id, identifiers in self.identifiers.items()
                if any(item.identifier_type == "email" and _normalize("email", item.value) == email_key for item in identifiers)
            }
            if len(historical_users) == 1:
                matching_users = historical_users
                matched = tuple(sorted(matching_users))
        selected = matched[0] if len(matched) == 1 else None
        identifiers = tuple(
            sorted(
                self.identifiers.get(selected, []),
                key=lambda item: (item.identifier_type, _normalize(item.identifier_type, item.value), item.value),
            )
        ) if selected else ()
        subject_keys = {
            (item.identifier_type, _normalize(item.identifier_type, item.value))
            for item in identifiers
        }
        collision_keys = subject_keys if selected else {("email", email_key)}
        email_collisions = tuple(
            c for c in self.collisions
            if (c.identifier_type, c.value) in collision_keys
        )
        return IdentityResolution(
            requested_email=request.email,
            as_of=request.requested_at,
            user_id=selected,
            identifiers=identifiers,
            matched_user_ids=matched,
            collisions=email_collisions,
        )
