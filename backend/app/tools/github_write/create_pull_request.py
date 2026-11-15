"""Open a pull request from an application branch; reuse an existing open one."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.core.constants import APPLICATION_BRANCH_PREFIX, MAX_ISSUE_TITLE_LENGTH, MAX_PULL_REQUEST_BODY_LENGTH
from app.core.exceptions import InvalidInputError, UnverifiedResultError
from app.guardrails.action_policy import (
    ApprovedAction, WriteActionType, authorize_write, execute_approved_write,
)
from app.guardrails.input_validation import validate_branch_name, validate_owner_repo
from app.guardrails.permission_checks import require_write_permission
from app.guardrails.secret_detection import find_secrets
from app.integrations.github.permissions import get_repository_access
from app.integrations.github.pull_requests import create_pull_request, find_open_pull_request, get_pull_request
from app.schemas.common import StrictModel
from app.schemas.github_action import GitHubActionResult
from app.tools import WriteToolContext

TOOL_NAME = "create_pull_request"


class CreatePullRequestInput(StrictModel):
    owner: str = Field(min_length=1, max_length=39)
    repo: str = Field(min_length=1, max_length=100)
    head: str = Field(min_length=1, max_length=200)
    base: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=MAX_ISSUE_TITLE_LENGTH)
    body: str = Field(default="", max_length=MAX_PULL_REQUEST_BODY_LENGTH)
    draft: bool = False


def build_payload(params: CreatePullRequestInput) -> dict[str, Any]:
    return {"owner": params.owner, "repo": params.repo, "head": params.head, "base": params.base,
            "title": params.title, "body": params.body, "draft": params.draft}


async def run(
    ctx: WriteToolContext, approval: ApprovedAction, params: CreatePullRequestInput
) -> GitHubActionResult:
    ref = validate_owner_repo(params.owner, params.repo)
    head = validate_branch_name(params.head)
    base = validate_branch_name(params.base)
    if not head.startswith(APPLICATION_BRANCH_PREFIX) or head == base:
        raise InvalidInputError(f"The head branch must start with '{APPLICATION_BRANCH_PREFIX}' and differ from base.")
    if find_secrets(params.title + "\n" + params.body):
        raise InvalidInputError("Pull request content appears to contain a credential.")
    approved = authorize_write(
        approval, user_id=ctx.user_id, action_type=WriteActionType.CREATE_PULL_REQUEST,
        owner=ref.owner, repo=ref.name, payload=build_payload(params), now=ctx.now(),
    )

    async def check() -> None:
        require_write_permission(await get_repository_access(ctx.client, ref.owner, ref.name), "push")

    async def perform() -> dict[str, Any]:
        pr = await find_open_pull_request(ctx.client, ref.owner, ref.name, head, base)
        created_now = pr is None
        if pr is None:
            pr = await create_pull_request(
                ctx.client, ref.owner, ref.name, title=params.title, head=head, base=base,
                body=params.body, draft=params.draft,
            )
        seen = await get_pull_request(ctx.client, ref.owner, ref.name, pr.number)
        expected_prefix = f"https://github.com/{ref.owner}/{ref.name}/pull/".casefold()
        if (
            seen.state != "open" or seen.head_ref != head or seen.base_ref != base
            or (created_now and seen.draft != params.draft)
            or not seen.html_url.casefold().startswith(expected_prefix)
        ):
            raise UnverifiedResultError("The pull request could not be verified.")
        return {"github_url": seen.html_url, "github_number": seen.number,
                "github_sha": None, "request_id": pr.request_id}

    result, replayed = await execute_approved_write(
        ledger=ctx.ledger, approval=approved, check_permission=check, perform=perform
    )
    return GitHubActionResult(
        action_type=approved.action_type.value, approval_id=approved.approval_id, replayed=replayed, **result
    )
