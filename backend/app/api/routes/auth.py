from __future__ import annotations

import asyncio
import re
from functools import lru_cache

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AuthenticationError, ConflictError, InvalidInputError
from app.core.password import hash_password, verify_password
from app.core.session import (
    REFRESH_COOKIE, clear_auth_cookies, create_session, revoke_session, rotate_session, set_auth_cookies,
)
from app.dependencies import DB, CurrentUser, SettingsDep, client_ip
from app.guardrails.output_validation import sanitize_text
from app.guardrails.rate_limits import enforce
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.observability.audit import record_audit
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from app.schemas.user import UserOut
from app.workflows.common import utcnow

router = APIRouter(prefix="/auth", tags=["auth"])
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password("not-a-real-password-for-timing")


@router.post("/register", status_code=201, response_model=AuthResponse)
async def register(body: RegisterRequest, request: Request, db: DB) -> AuthResponse:
    await enforce(db, "register", client_ip(request))
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise InvalidInputError("Invalid email address.")
    name = sanitize_text(body.display_name, max_length=100)
    if not name:
        raise InvalidInputError("Display name is required.")
    if (await db.execute(select(User.id).where(User.email == email))).first():
        raise ConflictError("An account with this email already exists.")
    password_hash = await asyncio.to_thread(hash_password, body.password)
    user = User(email=email, password_hash=password_hash, display_name=name, role="user")
    db.add(user)
    try:
        await db.flush()
        workspace = Workspace(name=f"{name}'s workspace", owner_id=user.id)
        db.add(workspace)
        await db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        await record_audit(db, event_type="user.registered", user_id=user.id, entity_type="user", entity_id=str(user.id))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("An account with this email already exists.") from None
    return AuthResponse(user=UserOut.from_row(user))


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, request: Request, response: Response, db: DB, settings: SettingsDep) -> AuthResponse:
    email = body.email.strip().lower()
    await enforce(db, "login", f"{client_ip(request)}:{email}")
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    valid = await asyncio.to_thread(verify_password, body.password, user.password_hash if user else _dummy_hash())
    if user is None or not valid or not user.is_active:
        await record_audit(db, event_type="auth.login_failed", details={"ip": client_ip(request)})
        await db.commit()
        raise AuthenticationError("Invalid email or password.")
    _, access, refresh = await create_session(db, user, settings, utcnow(), request.headers.get("user-agent"))
    await record_audit(db, event_type="auth.login", user_id=user.id, entity_type="user", entity_id=str(user.id))
    await db.commit()
    set_auth_cookies(response, settings, access, refresh)
    return AuthResponse(user=UserOut.from_row(user))


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: DB) -> Response:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        await revoke_session(db, token, utcnow())
        await db.commit()
    out = Response(status_code=204)
    clear_auth_cookies(out)
    return out


@router.post("/refresh", response_model=AuthResponse)
async def refresh(request: Request, response: Response, db: DB, settings: SettingsDep) -> AuthResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise AuthenticationError("Invalid or expired session.")
    user, _, access, new_refresh = await rotate_session(db, token, settings, utcnow(), request.headers.get("user-agent"))
    await db.commit()
    set_auth_cookies(response, settings, access, new_refresh)
    return AuthResponse(user=UserOut.from_row(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.from_row(user)
