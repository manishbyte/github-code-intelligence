"""Create an application-namespaced branch from a pinned commit; verify the ref."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.core.constants import APPLICATION_BRANCH_PREFIX
from app.core.exceptions import InvalidInputError, UnverifiedResultError
from app.guardrails.action_policy import (
    ApprovedAction, WriteActionType, authorize_write, execute_approved_write,
)
from app.guardrails.input_validation import validate_branch_name, validate_commit_sha, validate_owner_repo
from app.guardrails.permission_checks import require_write_permission
from app.integrations.github.branches import create_branch_ref, get_branch_ref_sha
from app.integrations.github.exceptions import GitHubConflictError
from app.integrations.github.permissions import get_repository_access
from app.schemas.common import StrictModel
from app.schemas.github_action import GitHubActionResult
from app.tools import WriteToolContext

TOOL_NAME = "create_branch"


class CreateBranchInput(StrictModel):
    owner: str = Field(min_length=1, max_length=39)
    repo: str = Field(min_length=1, max_length=100)
    branch: str = Field(min_length=1, max_length=200)
    from_sha: str = Field(min_length=40, max_length=64)


def build_payload(params: CreateBranchInput) -> dict[str, Any]:
    return {"owner": params.owner, "repo": params.repo, "branch": params.branch, "from_sha": params.from_sha}


async def run(ctx: WriteToolContext, approval: ApprovedAction, params: CreateBranchInput) -> GitHubActionResult:
    ref = validate_owner_repo(params.owner, params.repo)
    branch = validate_branch_name(params.branch)
    if not branch.startswith(APPLICATION_BRANCH_PREFIX) or branch == APPLICATION_BRANCH_PREFIX:
        raise InvalidInputError(f"Branches must start with '{APPLICATION_BRANCH_PREFIX}'.")
    from_sha = validate_commit_sha(params.from_sha)
    approved = authorize_write(
        approval, user_id=ctx.user_id, action_type=WriteActionType.CREATE_BRANCH,
        owner=ref.owner, repo=ref.name, payload=build_payload(params), now=ctx.now(),
    )

    async def check() -> None:
        require_write_permission(await get_repository_access(ctx.client, ref.owner, ref.name), "push")

    async def perform() -> dict[str, Any]:
        request_id = None
        existing = await get_branch_ref_sha(ctx.client, ref.owner, ref.name, branch)
        if existing is None:
            _, request_id = await create_branch_ref(ctx.client, ref.owner, ref.name, branch, from_sha)
        elif existing != from_sha:
            raise GitHubConflictError("The branch already exists at a different commit.")
        if await get_branch_ref_sha(ctx.client, ref.owner, ref.name, branch) != from_sha:
            raise UnverifiedResultError("The created branch could not be verified.")
        return {"github_url": f"https://github.com/{ref.owner}/{ref.name}/tree/{branch}",
                "github_number": None, "github_sha": from_sha, "request_id": request_id}

    result, replayed = await execute_approved_write(
        ledger=ctx.ledger, approval=approved, check_permission=check, perform=perform
    )
    return GitHubActionResult(
        action_type=approved.action_type.value, approval_id=approved.approval_id, replayed=replayed, **result
    )
