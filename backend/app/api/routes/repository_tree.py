from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.dependencies import DB, CurrentUser
from app.guardrails.path_safety import validate_repo_path
from app.models.github_repository import GitHubRepository
from app.schemas.tree import RepositoryTree, TreeEntry
from app.workers.queue import enqueue
from app.workflows.common import load_repository, resolve_snapshot

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("/{repository_id}/tree", response_model=RepositoryTree)
async def get_tree(
    repository_id: uuid.UUID, user: CurrentUser, db: DB,
    commit_sha: str | None = Query(default=None, min_length=40, max_length=64),
    path_filter: str | None = Query(default=None, max_length=1024),
) -> RepositoryTree:
    repo = await load_repository(db, user.id, repository_id)
    snap = await resolve_snapshot(db, user.id, repo, commit_sha)
    prefix = validate_repo_path(path_filter, allow_trailing_slash=True) if path_filter else None
    items = [e for e in snap.tree if prefix is None or e["path"] == prefix or e["path"].startswith(prefix + "/")]
    entries = [TreeEntry(path=e["path"], kind=e["kind"], sha=e["sha"], mode=e["mode"], size=e.get("size")) for e in items]
    return RepositoryTree(
        owner=repo.owner, repo=repo.name, commit_sha=snap.commit_sha, tree_sha=snap.tree_sha, entries=entries,
        entry_count=len(entries), file_count=sum(e.kind == "file" for e in entries),
        directory_count=sum(e.kind == "directory" for e in entries), skipped_unsafe_entries=snap.skipped_unsafe_entries,
        path_filter=prefix,
    )


@router.post("/{repository_id}/refresh", status_code=202)
async def refresh_repository(repository_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, str]:
    """Queue a background re-inspection (for large repositories)."""
    repo = await load_repository(db, user.id, repository_id)
    job = await enqueue(db, kind="repository_refresh", user_id=user.id,
                        payload={"repository_url": f"https://github.com/{repo.owner}/{repo.name}"})
    await db.commit()
    return {"job_id": str(job.id), "status": "queued"}
