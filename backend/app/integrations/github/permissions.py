"""Repository access evaluated only from evidence GitHub returned."""

from __future__ import annotations

from dataclasses import dataclass

from app.integrations.github.client import GitHubClient
from app.integrations.github.repositories import RepositoryData, get_repository


@dataclass(frozen=True)
class RepositoryAccess:
    can_read: bool
    can_push: bool
    can_admin: bool
    can_create_issue: bool
    archived: bool
    disabled: bool
    has_issues: bool
    permissions_reported: bool


def evaluate_access(repo: RepositoryData) -> RepositoryAccess:
    perms = repo.permissions
    writable_state = not repo.archived and not repo.disabled
    if perms is None:
        # No evidence of permissions: never assume write access.
        return RepositoryAccess(
            can_read=repo.visibility == "public", can_push=False, can_admin=False,
            can_create_issue=repo.has_issues and writable_state,
            archived=repo.archived, disabled=repo.disabled, has_issues=repo.has_issues,
            permissions_reported=False,
        )
    can_push = writable_state and any(perms.get(k, False) for k in ("push", "maintain", "admin"))
    return RepositoryAccess(
        can_read=perms.get("pull", False) or repo.visibility == "public",
        can_push=can_push,
        can_admin=perms.get("admin", False),
        can_create_issue=repo.has_issues and writable_state,
        archived=repo.archived, disabled=repo.disabled, has_issues=repo.has_issues,
        permissions_reported=True,
    )


async def get_repository_access(client: GitHubClient, owner: str, repo: str) -> RepositoryAccess:
    return evaluate_access(await get_repository(client, owner, repo))
