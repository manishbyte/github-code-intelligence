from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.dependencies import DB, CurrentUser, WorkflowDepsDep
from app.guardrails.rate_limits import enforce
from app.models.github_repository import GitHubRepository
from app.schemas.github import RepositoryPermissionStatus
from app.schemas.repository import InspectRequest, InspectResultOut, RepositoryOut
from app.tools.github_read import check_permissions
from app.workflows.common import load_repository
from app.workflows.repository_inspection.graph import run_repository_inspection

router = APIRouter(tags=["repositories"])


def repository_out(r: GitHubRepository) -> RepositoryOut:
    return RepositoryOut(id=str(r.id), owner=r.owner, name=r.name, html_url=r.html_url, default_branch=r.default_branch,
                         visibility=r.visibility, description=r.description,
                         last_inspected_at=r.last_inspected_at.isoformat() if r.last_inspected_at else None)


@router.get("/github/repositories", response_model=list[RepositoryOut])
async def list_repositories(user: CurrentUser, db: DB) -> list[RepositoryOut]:
    rows = (await db.execute(select(GitHubRepository).where(GitHubRepository.user_id == user.id)
                             .order_by(GitHubRepository.last_inspected_at.desc().nullslast()).limit(100))).scalars().all()
    return [repository_out(r) for r in rows]


@router.get("/github/repositories/{repository_id}/permissions", response_model=RepositoryPermissionStatus)
async def repository_permissions(repository_id: uuid.UUID, deps: WorkflowDepsDep) -> RepositoryPermissionStatus:
    repo = await load_repository(deps.db, deps.user_id, repository_id)
    return await check_permissions.run(deps.read_ctx, check_permissions.CheckPermissionsInput(owner=repo.owner, repo=repo.name))


@router.post("/repositories/inspect", response_model=InspectResultOut)
async def inspect_repository(body: InspectRequest, deps: WorkflowDepsDep) -> InspectResultOut:
    await enforce(deps.db, "inspect", str(deps.user_id))
    state = await run_repository_inspection(deps, body.repository_url)
    repo = await load_repository(deps.db, deps.user_id, uuid.UUID(state["repository_id"]))
    return InspectResultOut(repository=repository_out(repo), snapshot_id=state.get("snapshot_id"),
                            commit_sha=state.get("head_sha"), is_empty=bool(state.get("is_empty")),
                            entry_count=int(state.get("entry_count", 0)))


@router.get("/repositories/{repository_id}", response_model=RepositoryOut)
async def get_repository(repository_id: uuid.UUID, user: CurrentUser, db: DB) -> RepositoryOut:
    return repository_out(await load_repository(db, user.id, repository_id))
