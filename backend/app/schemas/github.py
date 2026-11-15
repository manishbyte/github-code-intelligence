"""GitHub identity and permission schemas."""

from __future__ import annotations

from typing import Literal

from app.schemas.common import StrictModel


class GitHubUserProfile(StrictModel):
    github_id: int
    login: str
    name: str | None
    html_url: str
    avatar_url: str | None
    account_type: str | None
    public_repos: int | None
    granted_scopes: list[str] | None  # None: GitHub did not report scopes


class RepositoryPermissionStatus(StrictModel):
    github_login: str
    owner: str
    repo: str
    can_read: bool
    can_push: bool
    can_admin: bool
    can_create_issue: bool
    archived: bool
    disabled: bool
    has_issues: bool
    permissions_reported: bool
    granted_scopes: list[str] | None
    evidence_source: Literal["github_api"] = "github_api"


class GitHubAccountOut(StrictModel):
    github_user_id: int
    login: str
    avatar_url: str | None
    granted_scopes: list[str] | None
    can_write: bool
    connected_at: str


class OAuthStartOut(StrictModel):
    authorization_url: str
    access: Literal["read", "write"]
