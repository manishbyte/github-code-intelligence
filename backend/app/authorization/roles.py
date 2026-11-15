"""Application and workspace roles."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    USER = "user"
    RECRUITER = "recruiter"
    ADMIN = "admin"


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"
    VIEWER = "viewer"


_RANK = {WorkspaceRole.VIEWER: 0, WorkspaceRole.MEMBER: 1, WorkspaceRole.OWNER: 2}


def workspace_role_at_least(actual: str, minimum: WorkspaceRole) -> bool:
    try:
        return _RANK[WorkspaceRole(actual)] >= _RANK[minimum]
    except ValueError:
        return False
