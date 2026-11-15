"""Resolve a public repository URL to metadata and the default-branch head commit."""

from __future__ import annotations

from pydantic import Field

from app.core.exceptions import InvalidInputError
from app.guardrails.input_validation import parse_github_repo_url
from app.integrations.github.repositories import get_branch_head_sha, get_repository
from app.schemas.common import StrictModel
from app.schemas.repository import RepositoryInfo
from app.tools import ToolContext

TOOL_NAME = "get_repository"


class GetRepositoryInput(StrictModel):
    repository_url: str = Field(min_length=1, max_length=300)


async def run(ctx: ToolContext, params: GetRepositoryInput) -> RepositoryInfo:
    ref = parse_github_repo_url(params.repository_url)
    repo = await get_repository(ctx.client, ref.owner, ref.name)
    if repo.visibility != "public":
        raise InvalidInputError("Only public repositories are supported.")
    if repo.disabled:
        raise InvalidInputError("This repository is disabled.")
    head = await get_branch_head_sha(ctx.client, repo.owner, repo.name, repo.default_branch)
    return RepositoryInfo(
        owner=repo.owner, name=repo.name, full_name=repo.full_name, html_url=repo.html_url,
        visibility=repo.visibility, default_branch=repo.default_branch,
        default_branch_head_sha=head, is_empty=head is None, description=repo.description,
        is_fork=repo.is_fork, archived=repo.archived,
    )
