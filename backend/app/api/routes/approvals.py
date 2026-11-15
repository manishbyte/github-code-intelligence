from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.approvals.decisions import decide_approval, get_owned_approval
from app.authorization.policies import require
from app.dependencies import DB, CurrentUser
from app.guardrails.sql_and_data_safety import clamp_page
from app.models.approval_request import ApprovalRequest
from app.models.github_action import GitHubAction
from app.schemas.approval import ApprovalOut, DecisionBody
from app.workflows.common import utcnow

router = APIRouter(prefix="/approvals", tags=["approvals"])


async def approval_with_actions(db, approval: ApprovalRequest) -> ApprovalOut:
    actions = (await db.execute(select(GitHubAction).where(GitHubAction.approval_id == approval.id, GitHubAction.user_id == approval.user_id)
                                .order_by(GitHubAction.created_at))).scalars().all()
    return ApprovalOut.from_rows(approval, actions)


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(user: CurrentUser, db: DB, state: str | None = Query(default=None, max_length=20),
                         limit: int = 20, offset: int = 0) -> list[ApprovalOut]:
    limit, offset = clamp_page(limit, offset)
    q = select(ApprovalRequest).where(ApprovalRequest.user_id == user.id)
    if state:
        q = q.where(ApprovalRequest.state == state.upper())
    rows = (await db.execute(q.order_by(ApprovalRequest.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return [await approval_with_actions(db, r) for r in rows]


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval(approval_id: uuid.UUID, user: CurrentUser, db: DB) -> ApprovalOut:
    return await approval_with_actions(db, await get_owned_approval(db, approval_id, user.id))


async def _decide(approval_id: uuid.UUID, body: DecisionBody, user, db, approve: bool) -> ApprovalOut:
    require(user.role, "approval:decide")
    row = await decide_approval(db, approval_id=approval_id, user_id=user.id, approve=approve,
                                displayed_digest=body.displayed_payload_digest, now=utcnow())
    return await approval_with_actions(db, row)


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
async def approve(approval_id: uuid.UUID, body: DecisionBody, user: CurrentUser, db: DB) -> ApprovalOut:
    return await _decide(approval_id, body, user, db, True)


@router.post("/{approval_id}/reject", response_model=ApprovalOut)
async def reject(approval_id: uuid.UUID, body: DecisionBody, user: CurrentUser, db: DB) -> ApprovalOut:
    return await _decide(approval_id, body, user, db, False)
