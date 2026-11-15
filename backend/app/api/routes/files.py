from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.dependencies import WorkflowDepsDep
from app.guardrails.patch_safety import split_lines
from app.guardrails.secret_detection import find_secrets
from app.schemas.common import SecretFindingModel
from app.schemas.file import FileContent
from app.workflows.common import load_file, load_repository, resolve_snapshot

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("/{repository_id}/files/{file_path:path}", response_model=FileContent)
async def get_file(
    repository_id: uuid.UUID, file_path: str, deps: WorkflowDepsDep,
    commit_sha: str | None = Query(default=None, min_length=40, max_length=64),
) -> FileContent:
    repo = await load_repository(deps.db, deps.user_id, repository_id)
    snap = await resolve_snapshot(deps.db, deps.user_id, repo, commit_sha)
    f = await load_file(deps, repo, snap, file_path)  # validates the path and that it is a file in the snapshot
    await deps.db.commit()
    findings = [SecretFindingModel(rule=s.rule, line=s.line, preview=s.preview) for s in find_secrets(f.content)]
    return FileContent(
        owner=repo.owner, repo=repo.name, path=f.path, commit_sha=snap.commit_sha, status="ok", message=None,
        blob_sha=f.blob_sha, size_bytes=f.size_bytes, language=f.language, content=f.content,
        line_count=len(split_lines(f.content)), secret_findings=findings,
    )
