"""Backend enforcement of Human-in-the-Loop approval for GitHub write actions.

An ``ApprovedAction`` is created only by the approvals module after a human
approved the exact payload and the state machine moved the request to
``PUBLISHING``. Write tools re-verify it here; the LLM never supplies it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Awaitable, Callable, Literal, Mapping, Protocol

from app.core.exceptions import ActionInProgressError, ApprovalError, AppError, UnverifiedResultError

PUBLISHING_STATUS = "PUBLISHING"


class WriteActionType(StrEnum):
    CREATE_ISSUE = "create_issue"
    CREATE_BRANCH = "create_branch"
    COMMIT_FILE = "commit_file"
    CREATE_PULL_REQUEST = "create_pull_request"


@dataclass(frozen=True)
class ApprovedAction:
    approval_id: str
    user_id: str
    approved_by: str
    action_type: WriteActionType
    owner: str
    repo: str
    status: str
    payload_digest: str
    idempotency_key: str
    approved_at: datetime
    expires_at: datetime


def payload_digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def authorize_write(
    approval: object,
    *,
    user_id: str,
    action_type: WriteActionType,
    owner: str,
    repo: str,
    payload: Mapping[str, Any],
    now: datetime,
) -> ApprovedAction:
    if not isinstance(approval, ApprovedAction):
        raise ApprovalError("A valid human approval is required for this action.")
    if approval.status != PUBLISHING_STATUS:
        raise ApprovalError("The approval is not in a publishable state.")
    if approval.user_id != user_id or approval.approved_by != user_id:
        raise ApprovalError("The approval does not belong to the authenticated user.")
    if approval.action_type != action_type:
        raise ApprovalError("The approval is for a different action type.")
    if approval.owner.casefold() != owner.casefold() or approval.repo.casefold() != repo.casefold():
        raise ApprovalError("The approval is for a different repository.")
    if len(approval.idempotency_key) < 8:
        raise ApprovalError("The approval has no usable idempotency key.")
    if now.tzinfo is None or approval.expires_at.tzinfo is None or now >= approval.expires_at:
        raise ApprovalError("The approval has expired.")
    if not hmac.compare_digest(approval.payload_digest, payload_digest(payload)):
        raise ApprovalError("The action differs from what was approved.")
    return approval


@dataclass(frozen=True)
class LedgerClaim:
    state: Literal["claimed", "completed", "in_progress"]
    result: Mapping[str, Any] | None = None


class ActionLedger(Protocol):
    """Duplicate-action protection; the production implementation is PostgreSQL-backed."""

    async def claim(self, key: str) -> LedgerClaim: ...

    async def complete(self, key: str, result: Mapping[str, Any]) -> None: ...

    async def fail(self, key: str, *, category: str, outcome_unknown: bool) -> None: ...


async def execute_approved_write(
    *,
    ledger: ActionLedger,
    approval: ApprovedAction,
    check_permission: Callable[[], Awaitable[None]],
    perform: Callable[[], Awaitable[dict[str, Any]]],
) -> tuple[dict[str, Any], bool]:
    """Permission check -> idempotent claim -> write+verify. Returns (result, replayed)."""
    await check_permission()
    claim = await ledger.claim(approval.idempotency_key)
    if claim.state == "completed" and claim.result is not None:
        return dict(claim.result), True
    if claim.state != "claimed":
        raise ActionInProgressError("This action is already being processed or needs reconciliation.")
    try:
        result = await perform()
    except Exception as exc:  # recorded, then re-raised unchanged
        unknown = bool(getattr(exc, "outcome_unknown", False)) or isinstance(exc, UnverifiedResultError)
        category = exc.code if isinstance(exc, AppError) else type(exc).__name__
        await ledger.fail(approval.idempotency_key, category=category, outcome_unknown=unknown)
        raise
    await ledger.complete(approval.idempotency_key, result)
    return result, False
