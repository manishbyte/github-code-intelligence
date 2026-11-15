"""Result of a verified GitHub write."""

from __future__ import annotations

from typing import Literal

from app.schemas.common import StrictModel


class GitHubActionResult(StrictModel):
    action_type: str
    approval_id: str
    status: Literal["succeeded"] = "succeeded"
    verified: Literal[True] = True
    replayed: bool
    github_url: str
    github_number: int | None
    github_sha: str | None
    request_id: str | None
