"""Create a GitHub issue after human approval; the result is re-read and verified."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.core.constants import MAX_ISSUE_BODY_LENGTH, MAX_ISSUE_TITLE_LENGTH
from app.core.exceptions import InvalidInputError, UnverifiedResultError
from app.guardrails.action_policy import (
    ApprovedAction, WriteActionType, authorize_write, execute_approved_write,
)
from app.guardrails.input_validation import validate_owner_repo
from app.guardrails.permission_checks import require_write_permission
from app.guardrails.secret_detection import find_secrets
from app.integrations.github.issues import create_issue, get_issue
from app.integrations.github.permissions import get_repository_access
from app.schemas.common import StrictModel
from app.schemas.github_action import GitHubActionResult
from app.tools import WriteToolContext

TOOL_NAME = "create_issue"


class CreateIssueInput(StrictModel):
    owner: str = Field(min_length=1, max_length=39)
    repo: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=MAX_ISSUE_TITLE_LENGTH)
    body: str = Field(default="", max_length=MAX_ISSUE_BODY_LENGTH)
    labels: list[str] = Field(default_factory=list, max_length=10)


def build_payload(params: CreateIssueInput) -> dict[str, Any]:
    """The exact content a human approves; its digest is bound to the approval."""
    return {"owner": params.owner, "repo": params.repo, "title": params.title,
            "body": params.body, "labels": list(params.labels)}


async def run(ctx: WriteToolContext, approval: ApprovedAction, params: CreateIssueInput) -> GitHubActionResult:
    ref = validate_owner_repo(params.owner, params.repo)
    if any(not (1 <= len(label) <= 50) for label in params.labels):
        raise InvalidInputError("Invalid label.")
    if params.title.strip() == "":
        raise InvalidInputError("Issue title is empty.")
    if find_secrets(params.title + "\n" + params.body):
        raise InvalidInputError("Issue content appears to contain a credential.")
    approved = authorize_write(
        approval, user_id=ctx.user_id, action_type=WriteActionType.CREATE_ISSUE,
        owner=ref.owner, repo=ref.name, payload=build_payload(params), now=ctx.now(),
    )

    async def check() -> None:
        require_write_permission(await get_repository_access(ctx.client, ref.owner, ref.name), "issue")

    async def perform() -> dict[str, Any]:
        created = await create_issue(
            ctx.client, ref.owner, ref.name, title=params.title, body=params.body, labels=params.labels
        )
        seen = await get_issue(ctx.client, ref.owner, ref.name, created.number)
        expected_prefix = f"https://github.com/{ref.owner}/{ref.name}/issues/".casefold()
        if (
            seen.number != created.number
            or seen.title.strip() != params.title.strip()
            or seen.state != "open"
            or not seen.html_url.casefold().startswith(expected_prefix)
        ):
            raise UnverifiedResultError("The created issue could not be verified.")
        return {"github_url": seen.html_url, "github_number": seen.number,
                "github_sha": None, "request_id": created.request_id}

    result, replayed = await execute_approved_write(
        ledger=ctx.ledger, approval=approved, check_permission=check, perform=perform
    )
    return GitHubActionResult(
        action_type=approved.action_type.value, approval_id=approved.approval_id, replayed=replayed, **result
    )
