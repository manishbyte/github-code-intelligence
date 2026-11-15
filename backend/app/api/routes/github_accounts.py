from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from sqlalchemy import delete, select

from app.approvals.policy import has_write_scope
from app.core.exceptions import GitHubNotConnectedError
from app.dependencies import DB, CurrentUser, SettingsDep
from app.integrations.github.oauth import revoke_grant
from app.models.github_account import GitHubAccount
from app.observability.audit import record_audit
from app.schemas.github import GitHubAccountOut

router = APIRouter(prefix="/github", tags=["github"])
logger = logging.getLogger("app.github_accounts")


@router.get("/account", response_model=GitHubAccountOut | None)
async def get_account(user: CurrentUser, db: DB) -> GitHubAccountOut | None:
    a = (await db.execute(select(GitHubAccount).where(GitHubAccount.user_id == user.id))).scalar_one_or_none()
    if a is None:
        return None
    return GitHubAccountOut(github_user_id=a.github_user_id, login=a.github_username, avatar_url=a.avatar_url,
                            granted_scopes=a.granted_scopes, can_write=has_write_scope(a.granted_scopes),
                            connected_at=a.connected_at.isoformat())


@router.delete("/account", status_code=204)
async def disconnect(request: Request, user: CurrentUser, db: DB, settings: SettingsDep) -> Response:
    a = (await db.execute(select(GitHubAccount).where(GitHubAccount.user_id == user.id))).scalar_one_or_none()
    if a is None:
        raise GitHubNotConnectedError("No GitHub account is connected.")
    revoked = False
    try:
        token = request.app.state.cipher.decrypt(a.encrypted_access_token)
        revoked = await revoke_grant(request.app.state.transport, client_id=settings.github_client_id,
                                     client_secret=settings.github_client_secret, access_token=token)
    except Exception:  # best effort: the local token is deleted regardless
        logger.warning("github_revoke_failed", extra={"user_id": str(user.id)})
    await db.execute(delete(GitHubAccount).where(GitHubAccount.id == a.id))
    await record_audit(db, event_type="github.disconnected", user_id=user.id, details={"revoked_at_github": revoked})
    await db.commit()
    return Response(status_code=204)
