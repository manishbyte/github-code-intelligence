"""Payload construction and pre-publish validation for code changes."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Mapping

from app.core.exceptions import ApprovalError, StaleSourceError
from app.integrations.github.client import GitHubClient
from app.integrations.github.contents import get_file
from app.integrations.github.repositories import get_branch_head_sha
from app.tools.github_write import create_branch, create_commit, create_pull_request


def build_code_change_payload(
    *, owner: str, repo: str, default_branch: str, base_commit_sha: str, base_blob_sha: str, path: str,
    new_content: str, approval_id: uuid.UUID, branch_slug: str, commit_message: str, pr_title: str, pr_body: str,
) -> dict[str, Any]:
    """The exact three-step payload a human approves (branch -> commit -> pull request)."""
    branch = f"code-intel/{branch_slug}-{str(approval_id)[:8]}"
    branch_in = create_branch.CreateBranchInput(owner=owner, repo=repo, branch=branch, from_sha=base_commit_sha)
    commit_in = create_commit.CreateCommitInput(
        owner=owner, repo=repo, branch=branch, path=path, content=new_content, message=commit_message, sha=base_blob_sha)
    pr_in = create_pull_request.CreatePullRequestInput(
        owner=owner, repo=repo, head=branch, base=default_branch, title=pr_title, body=pr_body, draft=False)
    return {
        "branch": create_branch.build_payload(branch_in),
        "commit": create_commit.build_payload(commit_in),
        "pull_request": create_pull_request.build_payload(pr_in),
    }


def verify_artifact_matches_payload(artifact_payload: Mapping[str, Any], approval_payload: Mapping[str, Any]) -> None:
    content = artifact_payload.get("new_content")
    expected = approval_payload.get("commit", {}).get("content_sha256")
    if not isinstance(content, str) or hashlib.sha256(content.encode("utf-8")).hexdigest() != expected:
        raise ApprovalError("The stored change does not match what was approved.")


async def preflight_code_change(
    client: GitHubClient, approval_payload: Mapping[str, Any], artifact_payload: Mapping[str, Any], *, max_bytes: int
) -> None:
    """Refuse to publish if the artifact was altered or the file changed upstream since it was proposed."""
    verify_artifact_matches_payload(artifact_payload, approval_payload)
    commit, pr = approval_payload["commit"], approval_payload["pull_request"]
    head = await get_branch_head_sha(client, commit["owner"], commit["repo"], pr["base"])
    if head is None:
        raise StaleSourceError("The base branch no longer exists.")
    current = await get_file(client, commit["owner"], commit["repo"], commit["path"], head, max_bytes=max_bytes)
    if current.status != "ok" or current.blob_sha != commit["sha"]:
        raise StaleSourceError("The file changed on the base branch since this change was proposed; generate it again.")
