"""Repository metadata and branch heads (read-only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import quote

from app.integrations.github.client import GitHubClient, as_mapping
from app.integrations.github.exceptions import GitHubError, GitHubNotFoundError


@dataclass(frozen=True)
class RepositoryData:
    owner: str
    name: str
    full_name: str
    html_url: str
    visibility: str
    default_branch: str
    description: str | None
    is_fork: bool
    archived: bool
    disabled: bool
    has_issues: bool
    permissions: Mapping[str, bool] | None  # None when GitHub did not report it


async def get_repository(client: GitHubClient, owner: str, repo: str) -> RepositoryData:
    resp = await client.request("GET", f"/repos/{owner}/{repo}")
    data = as_mapping(resp.data, "repository")
    owner_obj = data.get("owner")
    try:
        login = owner_obj["login"]  # type: ignore[index]
        name = data["name"]
        default_branch = data["default_branch"]
        full_name = data["full_name"]
    except (KeyError, TypeError):
        raise GitHubError("Unexpected GitHub repository response.") from None
    visibility = data.get("visibility") or ("private" if data.get("private") else "public")
    perms = data.get("permissions")
    return RepositoryData(
        owner=login,
        name=name,
        full_name=full_name,
        html_url=str(data.get("html_url", f"https://github.com/{full_name}")),
        visibility=str(visibility),
        default_branch=default_branch,
        description=data.get("description"),
        is_fork=bool(data.get("fork")),
        archived=bool(data.get("archived")),
        disabled=bool(data.get("disabled")),
        has_issues=bool(data.get("has_issues", True)),
        permissions={k: bool(v) for k, v in perms.items()} if isinstance(perms, dict) else None,
    )


async def get_branch_head_sha(client: GitHubClient, owner: str, repo: str, branch: str) -> str | None:
    """Return the branch head commit SHA, or ``None`` if the branch does not exist (empty repo)."""
    try:
        resp = await client.request("GET", f"/repos/{owner}/{repo}/branches/{quote(branch, safe='/')}")
    except GitHubNotFoundError:
        return None
    data = as_mapping(resp.data, "branch")
    sha = (data.get("commit") or {}).get("sha") if isinstance(data.get("commit"), dict) else None
    if not isinstance(sha, str):
        raise GitHubError("Unexpected GitHub branch response.")
    return sha
