"""Commit a full new version of one existing file to an application branch.

Stale-source protection: ``sha`` is the blob SHA of the file the change was
generated against; the write is refused unless the branch still holds it.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import Field

from app.core.constants import APPLICATION_BRANCH_PREFIX, DEFAULT_MAX_SOURCE_FILE_BYTES, MAX_COMMIT_MESSAGE_LENGTH
from app.core.exceptions import InvalidInputError, StaleSourceError, UnverifiedResultError
from app.guardrails.action_policy import (
    ApprovedAction, WriteActionType, authorize_write, execute_approved_write,
)
from app.guardrails.input_validation import validate_branch_name, validate_commit_sha, validate_owner_repo
from app.guardrails.path_safety import validate_write_path
from app.guardrails.permission_checks import require_write_permission
from app.guardrails.secret_detection import find_secrets_in_added_lines
from app.integrations.github.branches import get_branch_ref_sha
from app.integrations.github.commits import latest_commit_sha_for_path, update_file
from app.integrations.github.contents import FileFetch, get_file
from app.integrations.github.permissions import get_repository_access
from app.schemas.common import StrictModel
from app.schemas.github_action import GitHubActionResult
from app.tools import WriteToolContext

TOOL_NAME = "create_commit"


class CreateCommitInput(StrictModel):
    owner: str = Field(min_length=1, max_length=39)
    repo: str = Field(min_length=1, max_length=100)
    branch: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=DEFAULT_MAX_SOURCE_FILE_BYTES * 2)
    message: str = Field(min_length=1, max_length=MAX_COMMIT_MESSAGE_LENGTH)
    sha: str = Field(min_length=40, max_length=64, description="Blob SHA of the file being replaced")


def build_payload(params: CreateCommitInput) -> dict[str, Any]:
    return {
        "owner": params.owner, "repo": params.repo, "branch": params.branch, "path": params.path,
        "content_sha256": hashlib.sha256(params.content.encode("utf-8")).hexdigest(),
        "message": params.message, "sha": params.sha,
    }


async def run(ctx: WriteToolContext, approval: ApprovedAction, params: CreateCommitInput) -> GitHubActionResult:
    ref = validate_owner_repo(params.owner, params.repo)
    branch = validate_branch_name(params.branch)
    if not branch.startswith(APPLICATION_BRANCH_PREFIX):
        raise InvalidInputError(f"Commits are only allowed on '{APPLICATION_BRANCH_PREFIX}' branches.")
    path = validate_write_path(params.path)
    expected_sha = validate_commit_sha(params.sha)
    if "\x00" in params.content:
        raise InvalidInputError("Binary content cannot be committed.")
    new_bytes = params.content.encode("utf-8")
    if len(new_bytes) > ctx.max_file_bytes:
        raise InvalidInputError("File exceeds the size limit.")
    approved = authorize_write(
        approval, user_id=ctx.user_id, action_type=WriteActionType.COMMIT_FILE,
        owner=ref.owner, repo=ref.name, payload=build_payload(params), now=ctx.now(),
    )
    state: dict[str, FileFetch] = {}

    async def check() -> None:
        require_write_permission(await get_repository_access(ctx.client, ref.owner, ref.name), "push")
        current = await get_file(ctx.client, ref.owner, ref.name, path, branch, max_bytes=ctx.max_file_bytes)
        if current.status != "ok" or current.data is None:
            raise StaleSourceError("The target file is missing or unreadable on the branch.")
        try:
            old_text = current.data.decode("utf-8")
        except UnicodeDecodeError:
            raise InvalidInputError("The target file is not UTF-8 text.") from None
        if current.blob_sha != expected_sha and current.data != new_bytes:
            raise StaleSourceError("The file changed since the change was generated.")
        if find_secrets_in_added_lines(old_text, params.content):
            raise InvalidInputError("The change adds content that appears to be a credential.")
        state["current"] = current

    async def perform() -> dict[str, Any]:
        current = state["current"]
        if current.blob_sha == expected_sha:
            done = await update_file(
                ctx.client, ref.owner, ref.name, path, branch=branch, message=params.message,
                content=new_bytes, expected_blob_sha=expected_sha,
            )
            commit_sha, blob_sha, request_id = done.commit_sha, done.blob_sha, done.request_id
        else:  # already applied by an interrupted earlier attempt: reconcile, do not re-write
            commit_sha = await latest_commit_sha_for_path(ctx.client, ref.owner, ref.name, branch, path) \
                or await get_branch_ref_sha(ctx.client, ref.owner, ref.name, branch)
            blob_sha, request_id = current.blob_sha, None
        if commit_sha is None:
            raise UnverifiedResultError("The commit could not be located.")
        seen = await get_file(ctx.client, ref.owner, ref.name, path, commit_sha, max_bytes=ctx.max_file_bytes)
        if seen.status != "ok" or seen.data != new_bytes or seen.blob_sha != blob_sha:
            raise UnverifiedResultError("The committed file content could not be verified.")
        return {"github_url": f"https://github.com/{ref.owner}/{ref.name}/commit/{commit_sha}",
                "github_number": None, "github_sha": commit_sha, "request_id": request_id}

    result, replayed = await execute_approved_write(
        ledger=ctx.ledger, approval=approved, check_permission=check, perform=perform
    )
    return GitHubActionResult(
        action_type=approved.action_type.value, approval_id=approved.approval_id, replayed=replayed, **result
    )
