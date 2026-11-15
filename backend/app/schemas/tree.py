"""Repository tree schemas."""

from __future__ import annotations

from typing import Literal

from app.schemas.common import StrictModel


class TreeEntry(StrictModel):
    path: str
    kind: Literal["file", "directory", "symlink", "submodule"]
    sha: str
    mode: str
    size: int | None


class RepositoryTree(StrictModel):
    owner: str
    repo: str
    commit_sha: str
    tree_sha: str
    entries: list[TreeEntry]
    entry_count: int
    file_count: int
    directory_count: int
    skipped_unsafe_entries: int
    path_filter: str | None
    is_truncated: Literal[False] = False  # truncation is resolved or the call fails
