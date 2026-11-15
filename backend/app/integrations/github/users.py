"""Authenticated user lookup (read-only)."""

from __future__ import annotations

from dataclasses import dataclass

from app.integrations.github.client import GitHubClient, as_mapping
from app.integrations.github.exceptions import GitHubError


@dataclass(frozen=True)
class GitHubUser:
    id: int
    login: str
    html_url: str
    avatar_url: str | None
    name: str | None
    account_type: str | None
    public_repos: int | None


async def get_authenticated_user(client: GitHubClient) -> tuple[GitHubUser, tuple[str, ...] | None]:
    resp = await client.request("GET", "/user")
    data = as_mapping(resp.data, "user")
    if not isinstance(data.get("id"), int) or not isinstance(data.get("login"), str):
        raise GitHubError("Unexpected GitHub user response.")
    raw_scopes = resp.headers.get("x-oauth-scopes")
    scopes = None if raw_scopes is None else tuple(s.strip() for s in raw_scopes.split(",") if s.strip())
    user = GitHubUser(
        id=data["id"],
        login=data["login"],
        html_url=str(data.get("html_url", f"https://github.com/{data['login']}")),
        avatar_url=data.get("avatar_url"),
        name=data.get("name"),
        account_type=data.get("type"),
        public_repos=data.get("public_repos") if isinstance(data.get("public_repos"), int) else None,
    )
    return user, scopes
