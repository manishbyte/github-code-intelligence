"""Workspace membership checks."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authorization.roles import WorkspaceRole, workspace_role_at_least
from app.core.exceptions import NotFoundError
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember


async def get_personal_workspace(db: AsyncSession, user_id: uuid.UUID) -> Workspace:
    ws = (await db.execute(select(Workspace).where(Workspace.owner_id == user_id).order_by(Workspace.created_at))).scalars().first()
    if ws is None:
        raise NotFoundError("Workspace not found.")
    return ws


async def require_workspace_access(
    db: AsyncSession, user_id: uuid.UUID, workspace_id: uuid.UUID, minimum: WorkspaceRole = WorkspaceRole.MEMBER
) -> WorkspaceMember:
    member = (await db.execute(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
    )).scalar_one_or_none()
    if member is None or not workspace_role_at_least(member.role, minimum):
        raise NotFoundError("Workspace not found.")
    return member
