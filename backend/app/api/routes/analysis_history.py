from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.dependencies import DB, CurrentUser
from app.guardrails.sql_and_data_safety import clamp_page
from app.models.analysis_run import AnalysisRun
from app.models.github_repository import GitHubRepository
from app.schemas.review import HistoryItemOut

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=list[HistoryItemOut])
async def history(user: CurrentUser, db: DB, kind: str | None = Query(default=None, max_length=30),
                  limit: int = 20, offset: int = 0) -> list[HistoryItemOut]:
    limit, offset = clamp_page(limit, offset)
    q = select(AnalysisRun, GitHubRepository.owner, GitHubRepository.name).outerjoin(
        GitHubRepository, GitHubRepository.id == AnalysisRun.repository_id).where(AnalysisRun.user_id == user.id)
    if kind:
        q = q.where(AnalysisRun.kind == kind)
    rows = (await db.execute(q.order_by(AnalysisRun.created_at.desc()).limit(limit).offset(offset))).all()
    return [HistoryItemOut(id=str(r.id), kind=r.kind, status=r.status, decision=r.decision, file_path=r.file_path,
                           repository=f"{o}/{n}" if o else None, created_at=r.created_at, completed_at=r.completed_at)
            for r, o, n in rows]
