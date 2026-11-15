"""Branch reference operations. ``create_branch_ref`` is a write."""

from __future__ import annotations

from urllib.parse import quote

from app.integrations.github.client import GitHubClient, as_mapping
from app.integrations.github.exceptions import GitHubError, GitHubNotFoundError


async def get_branch_ref_sha(client: GitHubClient, owner: str, repo: str, branch: str) -> str | None:
    try:
        resp = await client.request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{quote(branch, safe='/')}")
    except GitHubNotFoundError:
        return None
    obj = as_mapping(resp.data, "ref").get("object")
    sha = obj.get("sha") if isinstance(obj, dict) else None
    if not isinstance(sha, str):
        raise GitHubError("Unexpected GitHub ref response.")
    return sha


async def create_branch_ref(
    client: GitHubClient, owner: str, repo: str, branch: str, sha: str
) -> tuple[str, str | None]:
    """Create ``refs/heads/<branch>`` at ``sha``. Returns (sha reported by GitHub, request id)."""
    resp = await client.request(
        "POST", f"/repos/{owner}/{repo}/git/refs", json_body={"ref": f"refs/heads/{branch}", "sha": sha}
    )
    obj = as_mapping(resp.data, "ref").get("object")
    reported = obj.get("sha") if isinstance(obj, dict) else None
    if not isinstance(reported, str):
        raise GitHubError("Unexpected GitHub ref response.")
    return reported, resp.request_id
