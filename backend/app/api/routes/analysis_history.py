from __future__ import annotations
# Enable postponed evaluation of annotations (PEP 563) for forward references.

from fastapi import APIRouter, Query
# FastAPI router utilities and query parameter handling.
from sqlalchemy import select

from app.dependencies import DB, CurrentUser
# Dependency injection helpers: DB session and current authenticated user.
from app.guardrails.sql_and_data_safety import clamp_page
# Clamp pagination parameters to safe limits defined by guardrails.
from app.models.analysis_run import AnalysisRun
from app.models.github_repository import GitHubRepository
from app.schemas.review import HistoryItemOut

router = APIRouter(prefix="/history", tags=["history"])
# Define a router for history endpoints, mounted under '/history'.


@router.get("", response_model=list[HistoryItemOut])
# GET endpoint returning a list of history items for the current user.
async def history(user: CurrentUser, db: DB, kind: str | None = Query(default=None, max_length=30),
                  # Parameters: optional kind filter, pagination limit/offset with defaults.
                  limit: int = 20, offset: int = 0) -> list[HistoryItemOut]:
    limit, offset = clamp_page(limit, offset)
    # Apply guardrail clamping to limit/offset to prevent abuse.
    q = select(AnalysisRun, GitHubRepository.owner, GitHubRepository.name).outerjoin(
        # Build a query selecting analysis runs plus repository owner/name via outer join.
        GitHubRepository, GitHubRepository.id == AnalysisRun.repository_id).where(AnalysisRun.user_id == user.id)
    if kind:
        # If a kind is provided, restrict results to that analysis kind.
        q = q.where(AnalysisRun.kind == kind)
    rows = (await db.execute(q.order_by(AnalysisRun.created_at.desc()).limit(limit).offset(offset))).all()
    # Execute the query, ordering by newest first and applying pagination.
    return [HistoryItemOut(id=str(r.id), kind=r.kind, status=r.status, decision=r.decision, file_path=r.file_path,
                           # Transform raw rows into HistoryItemOut schema, formatting repository as 'owner/name'.
                           repository=f"{o}/{n}" if o else None, created_at=r.created_at, completed_at=r.completed_at)
            for r, o, n in rows]
