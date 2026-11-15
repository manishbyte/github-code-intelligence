from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, update

from app.approvals.policy import has_write_scope
from app.core.exceptions import ConflictError
from app.core.security import generate_opaque_token, hash_token
from app.dependencies import DB, CurrentUser, SettingsDep
from app.integrations.github.client import GitHubClient
from app.integrations.github.exceptions import GitHubError
from app.integrations.github.oauth import build_authorize_url, exchange_code
from app.integrations.github.users import get_authenticated_user
from app.models.github_account import GitHubAccount
from app.models.oauth_state import OAuthState
from app.models.user import User
from app.observability.audit import record_audit
from app.schemas.github import OAuthStartOut
from app.workflows.common import utcnow

router = APIRouter(prefix="/github", tags=["github"])
STATE_TTL = timedelta(minutes=10)


@router.get("/oauth/start", response_model=OAuthStartOut)
async def oauth_start(user: CurrentUser, db: DB, settings: SettingsDep, access: Literal["read", "write"] = "read") -> OAuthStartOut:
    if not settings.github_client_id or not settings.github_client_secret:
        raise ConflictError("GitHub OAuth is not configured on this server.")
    state = generate_opaque_token(32)
    db.add(OAuthState(user_id=user.id, state_hash=hash_token(state), access=access, expires_at=utcnow() + STATE_TTL))
    await db.commit()
    url = build_authorize_url(client_id=settings.github_client_id, redirect_uri=settings.github_callback_url, state=state, access=access)
    return OAuthStartOut(authorization_url=url, access=access)


_MESSAGES = {
    "connected": "GitHub connected. You can close this tab and return to the app.",
    "denied": "GitHub authorization was cancelled or incomplete. You can close this tab and try again.",
    "invalid_state": "This authorization link is invalid or has expired. Close this tab and start again from the app.",
    "github_error": "GitHub could not complete the authorization. Close this tab and try again.",
    "already_linked": "This GitHub account is already linked to another user.",
}


def _page(key: str) -> HTMLResponse:
    """Static page (no user-supplied text is ever reflected)."""
    ok = key == "connected"
    html = (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
        "<title>GitHub connection</title></head>"
        '<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem">'
        f"<h2>{'Connected' if ok else 'Not connected'}</h2><p>{_MESSAGES[key]}</p></body></html>"
    )
    return HTMLResponse(html, status_code=200 if ok else 400, headers={"Cache-Control": "no-store"})


@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(
    request: Request, db: DB, settings: SettingsDep,
    code: str | None = Query(default=None, max_length=200), state: str | None = Query(default=None, max_length=200),
    error: str | None = Query(default=None, max_length=100),
) -> HTMLResponse:
    """The browser arrives here from github.com without API credentials, so the user is identified by
    the single-use, unguessable ``state`` issued to them by ``/oauth/start`` (bound to their user id)."""
    if error or not code or not state:
        return _page("denied")
    now = utcnow()
    consumed = (await db.execute(
        update(OAuthState)
        .where(OAuthState.state_hash == hash_token(state), OAuthState.used_at.is_(None), OAuthState.expires_at > now)
        .values(used_at=now).returning(OAuthState.user_id)
    )).first()
    await db.commit()  # consumed even if the rest fails (single use)
    if consumed is None:
        return _page("invalid_state")
    user = (await db.execute(select(User).where(User.id == consumed[0], User.is_active.is_(True)))).scalar_one_or_none()
    if user is None:
        return _page("invalid_state")
    try:
        token = await exchange_code(
            request.app.state.transport, client_id=settings.github_client_id, client_secret=settings.github_client_secret,
            code=code, redirect_uri=settings.github_callback_url,
        )
        profile, header_scopes = await get_authenticated_user(GitHubClient(token.access_token, transport=request.app.state.transport))
    except GitHubError:
        return _page("github_error")
    other = (await db.execute(select(GitHubAccount.id).where(GitHubAccount.github_user_id == profile.id, GitHubAccount.user_id != user.id))).first()
    if other is not None:
        return _page("already_linked")
    scopes = list(token.scopes or header_scopes or ())
    encrypted = request.app.state.cipher.encrypt(token.access_token)
    account = (await db.execute(select(GitHubAccount).where(GitHubAccount.user_id == user.id))).scalar_one_or_none()
    if account is None:
        db.add(GitHubAccount(user_id=user.id, github_user_id=profile.id, github_username=profile.login, avatar_url=profile.avatar_url,
                             encrypted_access_token=encrypted, granted_scopes=scopes))
    else:
        account.github_user_id, account.github_username, account.avatar_url = profile.id, profile.login, profile.avatar_url
        account.encrypted_access_token, account.granted_scopes = encrypted, scopes
    await record_audit(db, event_type="github.connected", user_id=user.id, entity_type="github_account",
                       details={"login": profile.login, "write": has_write_scope(scopes)})
    await db.commit()
    return _page("connected")
