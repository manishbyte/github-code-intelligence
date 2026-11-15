"""GitHub OAuth web-flow helpers (authorize URL, code exchange, grant revocation)."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from urllib.parse import urlencode

from app.core.constants import HTTP_USER_AGENT
from app.integrations.github.client import HttpTransport
from app.integrations.github.exceptions import GitHubAuthError, GitHubError

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
WRITE_SCOPE = "public_repo"


@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    scopes: tuple[str, ...]
    token_type: str


def build_authorize_url(*, client_id: str, redirect_uri: str, state: str, access: str) -> str:
    """Read access needs no scope for public data; write access requests ``public_repo`` only."""
    params = {"client_id": client_id, "redirect_uri": redirect_uri, "state": state, "allow_signup": "true"}
    if access == "write":
        params["scope"] = WRITE_SCOPE
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(
    transport: HttpTransport, *, client_id: str, client_secret: str, code: str, redirect_uri: str
) -> OAuthToken:
    resp = await transport.send(
        "POST", TOKEN_URL,
        headers={"Accept": "application/json", "User-Agent": HTTP_USER_AGENT},
        params=None,
        json_body={"client_id": client_id, "client_secret": client_secret, "code": code, "redirect_uri": redirect_uri},
        timeout=15.0,
    )
    try:
        data = json.loads(resp.body or b"{}")
    except ValueError:
        raise GitHubError("GitHub returned an invalid OAuth response.", status=resp.status) from None
    if resp.status != 200 or not isinstance(data, dict) or "error" in data or not data.get("access_token"):
        raise GitHubAuthError("GitHub rejected the authorization code.", status=resp.status)
    scopes = tuple(s.strip() for s in str(data.get("scope", "")).split(",") if s.strip())
    return OAuthToken(str(data["access_token"]), scopes, str(data.get("token_type", "bearer")))


async def revoke_grant(transport: HttpTransport, *, client_id: str, client_secret: str, access_token: str) -> bool:
    """Revoke the user's authorization for this OAuth app. Returns True on success."""
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = await transport.send(
        "DELETE", f"https://api.github.com/applications/{client_id}/grant",
        headers={"Authorization": f"Basic {basic}", "Accept": "application/vnd.github+json", "User-Agent": HTTP_USER_AGENT},
        params=None, json_body={"access_token": access_token}, timeout=15.0,
    )
    return resp.status in (204, 404)
