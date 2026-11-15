"""Approval state machine. Only ``APPROVED`` can move to ``PUBLISHING``.

Pure and deterministic: persistence and locking (``SELECT ... FOR UPDATE``)
belong to the caller; every transition is validated here first.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from app.core.exceptions import ApprovalError
from app.guardrails.action_policy import PUBLISHING_STATUS, ApprovedAction, WriteActionType


class ApprovalState(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class ApprovalEvent(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    EXPIRE = "EXPIRE"
    START_PUBLISH = "START_PUBLISH"
    PUBLISH_SUCCEEDED = "PUBLISH_SUCCEEDED"
    PUBLISH_FAILED = "PUBLISH_FAILED"


S, E = ApprovalState, ApprovalEvent
_TRANSITIONS: Mapping[ApprovalState, Mapping[ApprovalEvent, ApprovalState]] = {
    S.PENDING_REVIEW: {E.APPROVE: S.APPROVED, E.REJECT: S.REJECTED, E.EXPIRE: S.EXPIRED},
    S.APPROVED: {E.START_PUBLISH: S.PUBLISHING, E.EXPIRE: S.EXPIRED},
    S.PUBLISHING: {E.PUBLISH_SUCCEEDED: S.PUBLISHED, E.PUBLISH_FAILED: S.FAILED},
}
TERMINAL_STATES = frozenset({S.REJECTED, S.EXPIRED, S.PUBLISHED, S.FAILED})


class InvalidTransitionError(ApprovalError):
    code = "invalid_transition"


def next_state(state: ApprovalState, event: ApprovalEvent) -> ApprovalState:
    try:
        return _TRANSITIONS[state][event]
    except KeyError:
        raise InvalidTransitionError(f"Cannot apply {event.value} in state {state.value}.") from None


@dataclass(frozen=True)
class ApprovalSnapshot:
    approval_id: str
    owner_user_id: str
    state: ApprovalState
    payload_digest: str  # digest of the exact content the human saw
    expires_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None


def _require_live(snapshot: ApprovalSnapshot, now: datetime) -> None:
    if now.tzinfo is None or snapshot.expires_at.tzinfo is None:
        raise ApprovalError("Timestamps must be timezone-aware.")
    if now >= snapshot.expires_at:
        raise ApprovalError("The approval request has expired.")


def decide(
    snapshot: ApprovalSnapshot, *, decider_user_id: str, approve: bool,
    displayed_payload_digest: str, now: datetime,
) -> ApprovalSnapshot:
    """Record a human decision. The decider must own the request and have seen the current payload."""
    if decider_user_id != snapshot.owner_user_id:
        raise ApprovalError("Only the owner of the request can decide it.")
    if displayed_payload_digest != snapshot.payload_digest:
        raise ApprovalError("The content changed after it was shown for review.")
    _require_live(snapshot, now)
    new = next_state(snapshot.state, E.APPROVE if approve else E.REJECT)
    return replace(snapshot, state=new, decided_by=decider_user_id, decided_at=now)


def begin_publish(snapshot: ApprovalSnapshot, *, now: datetime) -> ApprovalSnapshot:
    _require_live(snapshot, now)
    return replace(snapshot, state=next_state(snapshot.state, E.START_PUBLISH))


def finish_publish(snapshot: ApprovalSnapshot, *, succeeded: bool) -> ApprovalSnapshot:
    return replace(snapshot, state=next_state(snapshot.state, E.PUBLISH_SUCCEEDED if succeeded else E.PUBLISH_FAILED))


def to_approved_action(
    snapshot: ApprovalSnapshot, *, action_type: WriteActionType, owner: str, repo: str, idempotency_key: str
) -> ApprovedAction:
    """Build the capability write tools require; only possible while ``PUBLISHING``."""
    if snapshot.state is not S.PUBLISHING or snapshot.decided_by is None or snapshot.decided_at is None:
        raise ApprovalError("Only an approved request in PUBLISHING state can be published.")
    return ApprovedAction(
        approval_id=snapshot.approval_id, user_id=snapshot.owner_user_id, approved_by=snapshot.decided_by,
        action_type=action_type, owner=owner, repo=repo, status=PUBLISHING_STATUS,
        payload_digest=snapshot.payload_digest, idempotency_key=idempotency_key,
        approved_at=snapshot.decided_at, expires_at=snapshot.expires_at,
    )
