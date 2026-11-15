"""File commit operations. ``update_file`` is a write and only updates existing files."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from urllib.parse import quote

from app.integrations.github.client import GitHubClient, as_mapping
from app.integrations.github.exceptions import GitHubError


@dataclass(frozen=True)
class CommitResult:
    commit_sha: str
    blob_sha: str
    request_id: str | None


async def update_file(
    client: GitHubClient,
    owner: str,
    repo: str,
    path: str,
    *,
    branch: str,
    message: str,
    content: bytes,
    expected_blob_sha: str,
) -> CommitResult:
    """Update an existing file; GitHub rejects the write if ``expected_blob_sha`` is stale."""
    resp = await client.request(
        "PUT",
        f"/repos/{owner}/{repo}/contents/{quote(path, safe='/')}",
        json_body={
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "sha": expected_blob_sha,
            "branch": branch,
        },
    )
    data = as_mapping(resp.data, "commit result")
    commit, file = data.get("commit"), data.get("content")
    commit_sha = commit.get("sha") if isinstance(commit, dict) else None
    blob_sha = file.get("sha") if isinstance(file, dict) else None
    if not isinstance(commit_sha, str) or not isinstance(blob_sha, str):
        raise GitHubError("Unexpected GitHub commit response.")
    return CommitResult(commit_sha, blob_sha, resp.request_id)


async def latest_commit_sha_for_path(
    client: GitHubClient, owner: str, repo: str, branch: str, path: str
) -> str | None:
    resp = await client.request(
        "GET", f"/repos/{owner}/{repo}/commits", params={"sha": branch, "path": path, "per_page": "1"}
    )
    if not isinstance(resp.data, list) or not resp.data:
        return None
    sha = resp.data[0].get("sha") if isinstance(resp.data[0], dict) else None
    return sha if isinstance(sha, str) else None
