"""Repository metadata schema."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import StrictModel


class RepositoryInfo(StrictModel):
    owner: str
    name: str
    full_name: str
    html_url: str
    visibility: str
    default_branch: str
    default_branch_head_sha: str | None
    is_empty: bool
    description: str | None
    is_fork: bool
    archived: bool


class InspectRequest(StrictModel):
    repository_url: str = Field(min_length=1, max_length=300)


class RepositoryOut(StrictModel):
    id: str
    owner: str
    name: str
    html_url: str
    default_branch: str
    visibility: str
    description: str | None
    last_inspected_at: str | None


class InspectResultOut(StrictModel):
    repository: RepositoryOut
    snapshot_id: str | None
    commit_sha: str | None
    is_empty: bool
    entry_count: int
