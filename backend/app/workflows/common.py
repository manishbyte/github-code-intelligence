"""Shared workflow dependencies and data-access helpers (all queries are user-scoped)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import GroqClient
from app.config import Settings
from app.core.exceptions import InvalidInputError, LLMError, NotFoundError
from app.core.permissions import ensure_owner
from app.guardrails.path_safety import validate_repo_path
from app.models.file_snapshot import FileSnapshot
from app.models.github_repository import GitHubRepository
from app.models.repository_snapshot import RepositorySnapshot
from app.tools import ToolContext


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WorkflowDeps:
    db: AsyncSession
    user_id: uuid.UUID
    read_ctx: ToolContext
    settings: Settings
    llm: GroqClient | None = None
    github_account_id: uuid.UUID | None = None
    now: Callable[[], datetime] = utcnow

    def require_llm(self) -> GroqClient:
        if self.llm is None:
            raise LLMError("The language model is not configured (GROQ_API_KEY / GROQ_MODEL).")
        return self.llm


async def load_repository(db: AsyncSession, user_id: uuid.UUID, repository_id: uuid.UUID) -> GitHubRepository:
    row = (await db.execute(select(GitHubRepository).where(GitHubRepository.id == repository_id))).scalar_one_or_none()
    return ensure_owner(row, user_id, "Repository")


async def resolve_snapshot(
    db: AsyncSession, user_id: uuid.UUID, repo: GitHubRepository, commit_sha: str | None
) -> RepositorySnapshot:
    q = select(RepositorySnapshot).where(RepositorySnapshot.repository_id == repo.id, RepositorySnapshot.user_id == user_id)
    if commit_sha:
        q = q.where(RepositorySnapshot.commit_sha == commit_sha)
    snap = (await db.execute(q.order_by(RepositorySnapshot.created_at.desc()).limit(1))).scalar_one_or_none()
    if snap is None:
        raise NotFoundError("No inspected snapshot found; inspect the repository first.")
    return snap


def tree_files(snapshot: RepositorySnapshot) -> dict[str, dict[str, Any]]:
    return {e["path"]: e for e in snapshot.tree if e.get("kind") == "file"}


async def load_file(deps: WorkflowDeps, repo: GitHubRepository, snapshot: RepositorySnapshot, path: str) -> FileSnapshot:
    """Return the file at the snapshot's commit (cached), only if it is a regular file in the tree."""
    from app.tools.github_read.get_file_content import GetFileContentInput, run as get_file_content

    path = validate_repo_path(path)
    if path not in tree_files(snapshot):
        raise InvalidInputError("That path is not a regular file in this snapshot.")
    cached = (await deps.db.execute(
        select(FileSnapshot).where(FileSnapshot.snapshot_id == snapshot.id, FileSnapshot.path == path)
    )).scalar_one_or_none()
    if cached is not None:
        return ensure_owner(cached, deps.user_id, "File")
    result = await get_file_content(
        deps.read_ctx,
        GetFileContentInput(owner=repo.owner, repo=repo.name, path=path, commit_sha=snapshot.commit_sha),
    )
    if result.status != "ok" or result.content is None or result.blob_sha is None:
        raise InvalidInputError(result.message or "The file could not be read.")
    row = FileSnapshot(
        snapshot_id=snapshot.id, user_id=deps.user_id, path=path, blob_sha=result.blob_sha,
        size_bytes=result.size_bytes or 0, language=result.language, content=result.content,
    )
    deps.db.add(row)
    await deps.db.flush()
    return row
