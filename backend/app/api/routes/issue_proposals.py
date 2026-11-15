from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.core.permissions import ensure_owner
from app.dependencies import DB, CurrentUser, WorkflowDepsDep
from app.guardrails.rate_limits import enforce
from app.models.approval_request import ApprovalRequest
from app.models.generated_artifact import GeneratedArtifact
from app.schemas.approval import ApprovalOut
from app.schemas.issue import DuplicateCandidate, IssueProposalOut, IssueProposalRequest
from app.workflows.issue_proposal.graph import run_issue_proposal

router = APIRouter(tags=["issue-proposals"])


async def _proposal_out(db, artifact: GeneratedArtifact) -> IssueProposalOut:
    approval = (await db.execute(select(ApprovalRequest).where(ApprovalRequest.artifact_id == artifact.id))).scalar_one()
    issue = artifact.payload["issue"]
    return IssueProposalOut(
        id=str(artifact.id), analysis_id=str(artifact.analysis_run_id), owner=issue["owner"], repo=issue["repo"],
        title=issue["title"], body=issue["body"],
        duplicate_candidates=[DuplicateCandidate(**d) for d in artifact.payload.get("duplicates", [])],
        approval=ApprovalOut.from_rows(approval), created_at=artifact.created_at,
    )


@router.post("/reviews/{analysis_id}/issue-proposals", status_code=201, response_model=IssueProposalOut)
async def create_issue_proposal(analysis_id: uuid.UUID, body: IssueProposalRequest, deps: WorkflowDepsDep) -> IssueProposalOut:
    await enforce(deps.db, "proposal", str(deps.user_id))
    state = await run_issue_proposal(deps, analysis_id=analysis_id, finding_ids=body.finding_ids)
    artifact = (await deps.db.execute(select(GeneratedArtifact).where(GeneratedArtifact.id == uuid.UUID(state["artifact_id"])))).scalar_one()
    return await _proposal_out(deps.db, artifact)


@router.get("/issue-proposals/{proposal_id}", response_model=IssueProposalOut)
async def get_issue_proposal(proposal_id: uuid.UUID, user: CurrentUser, db: DB) -> IssueProposalOut:
    artifact = (await db.execute(select(GeneratedArtifact).where(GeneratedArtifact.id == proposal_id, GeneratedArtifact.kind == "issue_proposal"))).scalar_one_or_none()
    if artifact is None:
        raise NotFoundError("Issue proposal not found.")
    return await _proposal_out(db, ensure_owner(artifact, user.id, "Issue proposal"))
