"""Database operations for approval requests; every transition goes through the state machine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals import policy
from app.approvals.state_machine import (
    ApprovalSnapshot, ApprovalState, begin_publish, decide, finish_publish,
)
from app.core.exceptions import ApprovalError, NotFoundError
from app.core.permissions import ensure_owner
from app.guardrails.action_policy import payload_digest
from app.models.approval_decision import ApprovalDecision
from app.models.approval_request import ApprovalRequest
from app.observability.audit import record_audit


def to_snapshot(row: ApprovalRequest) -> ApprovalSnapshot:
    return ApprovalSnapshot(
        approval_id=str(row.id), owner_user_id=str(row.user_id), state=ApprovalState(row.state),
        payload_digest=row.payload_digest, expires_at=row.expires_at,
        decided_by=str(row.decided_by) if row.decided_by else None, decided_at=row.decided_at,
    )


def _apply(row: ApprovalRequest, snap: ApprovalSnapshot) -> None:
    row.state = snap.state.value
    row.decided_by = uuid.UUID(snap.decided_by) if snap.decided_by else None
    row.decided_at = snap.decided_at


async def create_approval(
    db: AsyncSession, *, approval_id: uuid.UUID, user_id: uuid.UUID, artifact_id: uuid.UUID | None,
    action_type: str, owner: str, repo: str, payload: Mapping[str, Any], now: datetime,
) -> ApprovalRequest:
    if action_type not in policy.ACTION_TYPES:
        raise ApprovalError("Unsupported approval action type.")
    row = ApprovalRequest(
        id=approval_id, user_id=user_id, artifact_id=artifact_id, action_type=action_type, owner=owner,
        repo=repo, state=ApprovalState.PENDING_REVIEW.value, payload=dict(payload),
        payload_digest=payload_digest(payload), expires_at=policy.expiry(now),
    )
    db.add(row)
    await db.flush()
    await record_audit(db, event_type="approval.created", user_id=user_id, entity_type="approval",
                       entity_id=str(row.id), details={"action_type": action_type, "repo": f"{owner}/{repo}"})
    return row


async def lock_approval(db: AsyncSession, approval_id: uuid.UUID, user_id: uuid.UUID) -> ApprovalRequest:
    row = (await db.execute(select(ApprovalRequest).where(ApprovalRequest.id == approval_id).with_for_update())).scalar_one_or_none()
    return ensure_owner(row, user_id, "Approval")


async def decide_approval(
    db: AsyncSession, *, approval_id: uuid.UUID, user_id: uuid.UUID, approve: bool,
    displayed_digest: str, now: datetime,
) -> ApprovalRequest:
    row = await lock_approval(db, approval_id, user_id)
    if payload_digest(row.payload) != row.payload_digest:  # integrity check of stored payload
        raise ApprovalError("The stored approval content failed its integrity check.")
    snap = decide(to_snapshot(row), decider_user_id=str(user_id), approve=approve,
                  displayed_payload_digest=displayed_digest, now=now)
    _apply(row, snap)
    db.add(ApprovalDecision(approval_id=row.id, user_id=user_id, decision="approve" if approve else "reject",
                            payload_digest=row.payload_digest))
    await record_audit(db, event_type="approval.approved" if approve else "approval.rejected", user_id=user_id,
                       entity_type="approval", entity_id=str(row.id))
    await db.commit()
    return row


async def begin_publishing(db: AsyncSession, *, approval_id: uuid.UUID, user_id: uuid.UUID, now: datetime) -> ApprovalSnapshot:
    """APPROVED -> PUBLISHING, committed before any GitHub write (blocks concurrent publishers)."""
    row = await lock_approval(db, approval_id, user_id)
    if payload_digest(row.payload) != row.payload_digest:
        raise ApprovalError("The stored approval content failed its integrity check.")
    snap = begin_publish(to_snapshot(row), now=now)
    _apply(row, snap)
    await record_audit(db, event_type="approval.publishing", user_id=user_id, entity_type="approval", entity_id=str(row.id))
    await db.commit()
    return snap


async def finish_publishing(db: AsyncSession, *, approval_id: uuid.UUID, user_id: uuid.UUID, succeeded: bool) -> None:
    row = await lock_approval(db, approval_id, user_id)
    snap = finish_publish(to_snapshot(row), succeeded=succeeded)
    _apply(row, snap)
    await record_audit(db, event_type="approval.published" if succeeded else "approval.failed", user_id=user_id,
                       entity_type="approval", entity_id=str(row.id))
    await db.commit()


async def expire_stale(db: AsyncSession, now: datetime) -> int:
    result = await db.execute(
        update(ApprovalRequest)
        .where(ApprovalRequest.state.in_([ApprovalState.PENDING_REVIEW.value, ApprovalState.APPROVED.value]),
               ApprovalRequest.expires_at <= now)
        .values(state=ApprovalState.EXPIRED.value)
    )
    await db.commit()
    return result.rowcount or 0


async def get_owned_approval(db: AsyncSession, approval_id: uuid.UUID, user_id: uuid.UUID) -> ApprovalRequest:
    row = (await db.execute(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Approval not found.")
    return ensure_owner(row, user_id, "Approval")
