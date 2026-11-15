from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.routes.approvals import approval_with_actions
from app.approvals.decisions import begin_publishing, finish_publishing, get_owned_approval
from app.authorization.policies import require
from app.core.exceptions import NotFoundError
from app.core.permissions import ensure_owner
from app.dependencies import DB, CurrentUser, SettingsDep, build_write_context
from app.guardrails.action_policy import WriteActionType
from app.guardrails.rate_limits import enforce
from app.models.generated_artifact import GeneratedArtifact
from app.models.github_action import GitHubAction
from app.observability.audit import record_audit
from app.schemas.approval import ActionRecordOut, ApprovalOut
from app.workflows.common import utcnow
from app.workflows.publishing.graph import run_publishing
from app.workflows.publishing.state import PublishDeps
from app.approvals.state_machine import to_approved_action

router = APIRouter(tags=["github-actions"])


@router.post("/approvals/{approval_id}/publish", response_model=ApprovalOut)
async def publish(approval_id: uuid.UUID, request: Request, user: CurrentUser, db: DB, settings: SettingsDep) -> ApprovalOut:
    """Publish an APPROVED request. Validates user, state, repository, permissions and idempotency."""
    require(user.role, "github:publish")
    await enforce(db, "publish", str(user.id))
    approval = await get_owned_approval(db, approval_id, user.id)
    artifact = None
    if approval.artifact_id is not None:
        artifact = (await db.execute(select(GeneratedArtifact).where(GeneratedArtifact.id == approval.artifact_id))).scalar_one_or_none()
        artifact = ensure_owner(artifact, user.id, "Proposal")
    ctx = await build_write_context(request, user, db, settings, approval_id)  # also verifies write scope
    snapshot = await begin_publishing(db, approval_id=approval_id, user_id=user.id, now=utcnow())  # APPROVED -> PUBLISHING
    base = to_approved_action(snapshot, action_type=WriteActionType.COMMIT_FILE, owner=approval.owner, repo=approval.repo,
                              idempotency_key=f"{approval_id}:base")
    try:
        results = await run_publishing(PublishDeps(
            ctx=ctx, base=base, action_kind=approval.action_type, approval_payload=approval.payload,
            artifact_payload=artifact.payload if artifact is not None else {},
        ))
    except Exception:
        await db.rollback()
        await finish_publishing(db, approval_id=approval_id, user_id=user.id, succeeded=False)
        raise
    await finish_publishing(db, approval_id=approval_id, user_id=user.id, succeeded=True)
    await record_audit(db, event_type="github.published", user_id=user.id, entity_type="approval", entity_id=str(approval_id),
                       details={"steps": [r["action_type"] for r in results]})
    await db.commit()
    await db.refresh(approval)
    return await approval_with_actions(db, approval)


@router.get("/github-actions/{action_id}", response_model=ActionRecordOut)
async def get_action(action_id: uuid.UUID, user: CurrentUser, db: DB) -> ActionRecordOut:
    a = (await db.execute(select(GitHubAction).where(GitHubAction.id == action_id))).scalar_one_or_none()
    if a is None:
        raise NotFoundError("Action not found.")
    ensure_owner(a, user.id, "Action")
    return ActionRecordOut(id=str(a.id), step=a.step, status=a.status, github_url=a.github_url, github_number=a.github_number,
                           github_sha=a.github_sha, error_category=a.error_category, created_at=a.created_at)
