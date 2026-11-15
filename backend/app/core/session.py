"""Server-side sessions: refresh-token rotation with reuse detection, and auth cookies."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.security import create_token, generate_opaque_token, hash_token
from app.models.user import User
from app.models.user_session import UserSession

ACCESS_COOKIE = "gci_access"
REFRESH_COOKIE = "gci_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


async def _issue(db: AsyncSession, user: User, settings: Settings, now: datetime, user_agent: str | None):
    refresh = generate_opaque_token(48)
    session = UserSession(
        user_id=user.id, refresh_token_hash=hash_token(refresh),
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(session)
    await db.flush()
    access = create_token(
        settings.app_secret_key, subject=str(user.id), token_type="access",
        ttl_seconds=settings.access_token_expire_minutes * 60, now=now, extra={"sid": str(session.id)},
    )
    return session, access, refresh


async def create_session(db: AsyncSession, user: User, settings: Settings, now: datetime, user_agent: str | None = None):
    return await _issue(db, user, settings, now, user_agent)


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID, now: datetime) -> None:
    await db.execute(
        update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None)).values(revoked_at=now)
    )


async def rotate_session(db: AsyncSession, refresh_token: str, settings: Settings, now: datetime, user_agent: str | None = None):
    """Exchange a refresh token for a new pair. Reuse of a revoked token revokes all sessions."""
    row = (await db.execute(
        select(UserSession).where(UserSession.refresh_token_hash == hash_token(refresh_token)).with_for_update()
    )).scalar_one_or_none()
    if row is None:
        raise AuthenticationError("Invalid or expired session.")
    if row.revoked_at is not None:
        await revoke_all_sessions(db, row.user_id, now)
        await db.commit()
        raise AuthenticationError("Invalid or expired session.")
    if row.expires_at <= now:
        raise AuthenticationError("Invalid or expired session.")
    user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired session.")
    row.revoked_at = now
    return user, *(await _issue(db, user, settings, now, user_agent))


async def revoke_session(db: AsyncSession, refresh_token: str, now: datetime) -> None:
    await db.execute(
        update(UserSession)
        .where(UserSession.refresh_token_hash == hash_token(refresh_token), UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def set_auth_cookies(response: Response, settings: Settings, access: str, refresh: str) -> None:
    common = dict(httponly=True, secure=settings.is_production, samesite="lax")
    response.set_cookie(ACCESS_COOKIE, access, max_age=settings.access_token_expire_minutes * 60, path="/", **common)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=settings.refresh_token_expire_days * 86400,
                        path=REFRESH_COOKIE_PATH, **common)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
