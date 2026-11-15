"""Return the authenticated GitHub user (data comes only from GitHub)."""

from __future__ import annotations

from app.integrations.github.users import get_authenticated_user
from app.schemas.common import StrictModel
from app.schemas.github import GitHubUserProfile
from app.tools import ToolContext

TOOL_NAME = "get_user_profile"


class GetUserProfileInput(StrictModel):
    pass


async def run(ctx: ToolContext, params: GetUserProfileInput) -> GitHubUserProfile:
    user, scopes = await get_authenticated_user(ctx.client)
    return GitHubUserProfile(
        github_id=user.id, login=user.login, name=user.name, html_url=user.html_url,
        avatar_url=user.avatar_url, account_type=user.account_type, public_repos=user.public_repos,
        granted_scopes=list(scopes) if scopes is not None else None,
    )
