"""File content schema. ``content`` is untrusted repository data."""

from __future__ import annotations

from typing import Literal

from app.schemas.common import SecretFindingModel, StrictModel

FileContentStatus = Literal[
    "ok", "binary", "too_large", "not_found", "not_a_file", "unsupported_type"
]


class FileContent(StrictModel):
    owner: str
    repo: str
    path: str
    commit_sha: str
    status: FileContentStatus
    message: str | None
    blob_sha: str | None
    size_bytes: int | None
    language: str | None
    content: str | None
    line_count: int | None
    secret_findings: list[SecretFindingModel]
    content_trust: Literal["untrusted"] = "untrusted"
