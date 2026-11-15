from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.authorization.policies import require
from app.core.permissions import ensure_owner
from app.dependencies import DB, CurrentUser, WorkflowDepsDep
from app.guardrails.rate_limits import enforce
from app.models.analysis_run import AnalysisRun
from app.models.review_finding import ReviewFinding
from app.schemas.finding import FindingOut
from app.schemas.review import ReviewRequest, ReviewRunOut
from app.workflows.code_review.graph import run_code_review
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/reviews", tags=["reviews"])


async def _load_run(db, user_id: uuid.UUID, analysis_id: uuid.UUID) -> AnalysisRun:
    run = (await db.execute(select(AnalysisRun).where(AnalysisRun.id == analysis_id, AnalysisRun.kind == "review"))).scalar_one_or_none()
    if run is None:
        raise NotFoundError("Review not found.")
    return ensure_owner(run, user_id, "Review")


async def _findings(db, run: AnalysisRun) -> list[ReviewFinding]:
    return list((await db.execute(select(ReviewFinding).where(ReviewFinding.analysis_run_id == run.id, ReviewFinding.user_id == run.user_id)
                                  .order_by(ReviewFinding.start_line))).scalars().all())


@router.post("", status_code=201, response_model=ReviewRunOut)
async def create_review(body: ReviewRequest, user: CurrentUser, deps: WorkflowDepsDep) -> ReviewRunOut:
    require(user.role, "review:create")
    await enforce(deps.db, "review", str(user.id))
    run_id = await run_code_review(deps, repository_id=body.repository_id, file_path=body.file_path, commit_sha=body.commit_sha)
    run = await _load_run(deps.db, user.id, run_id)
    return ReviewRunOut.from_rows(run, await _findings(deps.db, run))


@router.get("/{analysis_id}", response_model=ReviewRunOut)
async def get_review(analysis_id: uuid.UUID, user: CurrentUser, db: DB) -> ReviewRunOut:
    run = await _load_run(db, user.id, analysis_id)
    return ReviewRunOut.from_rows(run, await _findings(db, run))


@router.get("/{analysis_id}/findings", response_model=list[FindingOut])
async def get_findings(analysis_id: uuid.UUID, user: CurrentUser, db: DB) -> list[FindingOut]:
    run = await _load_run(db, user.id, analysis_id)
    return [FindingOut.from_row(f) for f in await _findings(db, run)]
