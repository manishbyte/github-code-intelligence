from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.core.permissions import ensure_owner
from app.dependencies import DB, CurrentUser, WorkflowDepsDep
from app.guardrails.rate_limits import enforce
from app.models.approval_request import ApprovalRequest
from app.models.generated_artifact import GeneratedArtifact
from app.schemas.approval import ApprovalOut
from app.schemas.code_change import CodeChangeProposalOut, CodeChangeRequest, QualityCheckResult
from app.workflows.comment_generation.graph import run_comment_generation
from app.workflows.logging_generation.graph import run_logging_generation

router = APIRouter(prefix="/code-changes", tags=["code-changes"])
_KINDS = ("comment_patch", "logging_patch")


async def _out(db, artifact: GeneratedArtifact) -> CodeChangeProposalOut:
    approval = (await db.execute(select(ApprovalRequest).where(ApprovalRequest.artifact_id == artifact.id))).scalar_one()
    p = artifact.payload
    return CodeChangeProposalOut(
        id=str(artifact.id), kind=p["kind"], owner=p["owner"], repo=p["repo"], file_path=p["path"],
        base_commit_sha=p["base_commit_sha"], base_blob_sha=p["base_blob_sha"], summary=p["summary"], diff=p["diff"],
        quality=QualityCheckResult(**p["quality"]), approval=ApprovalOut.from_rows(approval), created_at=artifact.created_at,
    )


async def _get(db, user_id: uuid.UUID, proposal_id: uuid.UUID) -> GeneratedArtifact:
    a = (await db.execute(select(GeneratedArtifact).where(GeneratedArtifact.id == proposal_id, GeneratedArtifact.kind.in_(_KINDS)))).scalar_one_or_none()
    if a is None:
        raise NotFoundError("Proposal not found.")
    return ensure_owner(a, user_id, "Proposal")


@router.post("/comments", status_code=201, response_model=CodeChangeProposalOut)
async def propose_comments(body: CodeChangeRequest, deps: WorkflowDepsDep) -> CodeChangeProposalOut:
    await enforce(deps.db, "proposal", str(deps.user_id))
    state = await run_comment_generation(deps, repository_id=body.repository_id, file_path=body.file_path, commit_sha=body.commit_sha)
    return await _out(deps.db, await _get(deps.db, deps.user_id, uuid.UUID(state["artifact_id"])))


@router.post("/logging", status_code=201, response_model=CodeChangeProposalOut)
async def propose_logging(body: CodeChangeRequest, deps: WorkflowDepsDep) -> CodeChangeProposalOut:
    await enforce(deps.db, "proposal", str(deps.user_id))
    state = await run_logging_generation(deps, repository_id=body.repository_id, file_path=body.file_path, commit_sha=body.commit_sha)
    return await _out(deps.db, await _get(deps.db, deps.user_id, uuid.UUID(state["artifact_id"])))


@router.get("/{proposal_id}", response_model=CodeChangeProposalOut)
async def get_proposal(proposal_id: uuid.UUID, user: CurrentUser, db: DB) -> CodeChangeProposalOut:
    return await _out(db, await _get(db, user.id, proposal_id))


@router.get("/{proposal_id}/diff", response_class=PlainTextResponse)
async def get_diff(proposal_id: uuid.UUID, user: CurrentUser, db: DB) -> str:
    return (await _get(db, user.id, proposal_id)).payload["diff"]
