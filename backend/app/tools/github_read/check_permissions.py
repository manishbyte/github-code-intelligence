"""Report the connected account's access to a repository from GitHub evidence."""

from __future__ import annotations

from pydantic import Field

from app.guardrails.input_validation import validate_owner_repo
from app.integrations.github.permissions import get_repository_access
from app.integrations.github.users import get_authenticated_user
from app.schemas.common import StrictModel
from app.schemas.github import RepositoryPermissionStatus
from app.tools import ToolContext

TOOL_NAME = "check_permissions"


class CheckPermissionsInput(StrictModel):
    owner: str = Field(min_length=1, max_length=39)
    repo: str = Field(min_length=1, max_length=100)


async def run(ctx: ToolContext, params: CheckPermissionsInput) -> RepositoryPermissionStatus:
    ref = validate_owner_repo(params.owner, params.repo)
    user, scopes = await get_authenticated_user(ctx.client)
    access = await get_repository_access(ctx.client, ref.owner, ref.name)
    return RepositoryPermissionStatus(
        github_login=user.login, owner=ref.owner, repo=ref.name,
        can_read=access.can_read, can_push=access.can_push, can_admin=access.can_admin,
        can_create_issue=access.can_create_issue, archived=access.archived, disabled=access.disabled,
        has_issues=access.has_issues, permissions_reported=access.permissions_reported,
        granted_scopes=list(scopes) if scopes is not None else None,
    )
