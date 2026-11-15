from __future__ import annotations

from typing import Any, TypedDict


class CodeChangeState(TypedDict, total=False):
    repository_id: str
    file_path: str
    commit_sha: str | None
    run_id: str
    owner: str
    repo_name: str
    default_branch: str
    content: str
    redacted: str
    language: str | None
    blob_sha: str
    warnings: list[str]
    conventions: dict[str, Any]
    raw: Any
    usage: dict
    latency_ms: int
    dropped: list[str]
    patch: Any
    quality: Any
    artifact_id: str
    approval_id: str
    payload: dict[str, Any]
