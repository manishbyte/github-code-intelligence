from __future__ import annotations

from typing import Any, TypedDict


class ReviewState(TypedDict, total=False):
    repository_id: str
    file_path: str
    commit_sha: str | None
    run_id: str
    content: str
    redacted: str
    language: str | None
    warnings: list[str]
    secret_findings: list[Any]
    raw: Any
    validated: Any
    usage: dict
    latency_ms: int
