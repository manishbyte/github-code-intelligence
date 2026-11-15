"""FastAPI dependencies: settings, database session, authentication, GitHub tool contexts."""

from __future__ import annotations

import uuid
from typing import Annotated, AsyncIterator

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.idempotency import PostgresActionLedger
from app.approvals.policy import has_write_scope
from app.authorization.policies import require as require_permission
from app.config import Settings
from app.core.exceptions import AuthenticationError, ConflictError, GitHubNotConnectedError
from app.core.security import decode_token
from app.core.session import ACCESS_COOKIE
from app.integrations.github.client import GitHubClient
from app.models.github_account import GitHubAccount
from app.models.user import User
from app.models.user_session import UserSession
from app.tools import ToolContext, WriteToolContext
from app.workflows.common import WorkflowDeps, utcnow


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


SettingsDep = Annotated[Settings, Depends(get_settings)]
DB = Annotated[AsyncSession, Depends(get_db)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def get_current_user(request: Request, db: DB, settings: SettingsDep) -> User:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise AuthenticationError("Authentication required.")
    now = utcnow()
    claims = decode_token(settings.app_secret_key, token, expected_type="access", now=now)
    try:
        user_id, session_id = uuid.UUID(claims["sub"]), uuid.UUID(str(claims.get("sid")))
    except (ValueError, KeyError):
        raise AuthenticationError("Invalid or expired token.") from None
    row = (await db.execute(
        select(User).join(UserSession, UserSession.user_id == User.id).where(
            User.id == user_id, User.is_active.is_(True), UserSession.id == session_id,
            UserSession.revoked_at.is_(None), UserSession.expires_at > now)
    )).scalar_one_or_none()
    if row is None:
        raise AuthenticationError("Invalid or expired token.")
    return row


CurrentUser = Annotated[User, Depends(get_current_user)]


def permission(action: str):
    """Dependency factory: current user must hold ``action`` (role-based access control)."""

    async def dep(user: CurrentUser) -> User:
        require_permission(user.role, action)
        return user

    return Depends(dep)


async def get_github_account(db: AsyncSession, user_id: uuid.UUID) -> GitHubAccount:
    account = (await db.execute(select(GitHubAccount).where(GitHubAccount.user_id == user_id))).scalar_one_or_none()
    if account is None:
        raise GitHubNotConnectedError("Connect your GitHub account first.")
    return account


async def build_workflow_deps(request: Request, user: User, db: AsyncSession, settings: Settings) -> WorkflowDeps:
    account = await get_github_account(db, user.id)
    token = request.app.state.cipher.decrypt(account.encrypted_access_token)
    client = GitHubClient(token, transport=request.app.state.transport)
    ctx = ToolContext(user_id=str(user.id), client=client, max_file_bytes=settings.max_source_file_bytes)
    return WorkflowDeps(db=db, user_id=user.id, read_ctx=ctx, settings=settings, llm=request.app.state.llm,
                        github_account_id=account.id)


async def get_workflow_deps(request: Request, user: CurrentUser, db: DB, settings: SettingsDep) -> WorkflowDeps:
    return await build_workflow_deps(request, user, db, settings)


WorkflowDepsDep = Annotated[WorkflowDeps, Depends(get_workflow_deps)]


async def build_write_context(
    request: Request, user: User, db: AsyncSession, settings: Settings, approval_id: uuid.UUID
) -> WriteToolContext:
    account = await get_github_account(db, user.id)
    if not has_write_scope(account.granted_scopes):
        raise ConflictError("Write access to GitHub has not been granted. Reconnect GitHub and allow write access.")
    token = request.app.state.cipher.decrypt(account.encrypted_access_token)
    client = GitHubClient(token, transport=request.app.state.transport, allow_writes=True)
    ledger = PostgresActionLedger(request.app.state.session_factory, user_id=user.id, approval_id=approval_id)
    return WriteToolContext(user_id=str(user.id), client=client, ledger=ledger, max_file_bytes=settings.max_source_file_bytes)
