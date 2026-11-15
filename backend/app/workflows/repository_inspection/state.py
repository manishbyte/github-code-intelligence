from __future__ import annotations

from typing import Any, TypedDict


class InspectionState(TypedDict, total=False):
    url: str
    repo: Any  # RepositoryData
    head_sha: str | None
    repository_id: str
    snapshot_id: str | None
    entry_count: int
    is_empty: bool
