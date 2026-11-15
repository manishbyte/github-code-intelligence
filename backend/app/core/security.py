"""HS256 JWTs (stdlib), opaque token generation and hashing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime
from typing import Any, Literal, Mapping

from app.core.exceptions import AuthenticationError

TokenType = Literal["access", "refresh"]
_HEADER = {"alg": "HS256", "typ": "JWT"}


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: str, signing_input: str) -> str:
    return _b64e(hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest())


def create_token(
    secret: str, *, subject: str, token_type: TokenType, ttl_seconds: int, now: datetime,
    extra: Mapping[str, Any] | None = None,
) -> str:
    if not secret or not subject or ttl_seconds <= 0:
        raise ValueError("secret, subject and a positive ttl are required")
    issued = int(now.timestamp())
    claims = {**(extra or {}), "sub": subject, "typ": token_type, "iat": issued, "exp": issued + ttl_seconds,
              "jti": secrets.token_urlsafe(12)}
    signing_input = f"{_b64e(json.dumps(_HEADER, separators=(',', ':')).encode())}.{_b64e(json.dumps(claims, separators=(',', ':')).encode())}"
    return f"{signing_input}.{_sign(secret, signing_input)}"


def decode_token(secret: str, token: str, *, expected_type: TokenType, now: datetime) -> dict[str, Any]:
    """Verify signature, algorithm, expiry and token type. Raises ``AuthenticationError``."""
    fail = AuthenticationError("Invalid or expired token.")
    try:
        header_b64, payload_b64, signature = token.split(".")
        header = json.loads(_b64d(header_b64))
        if header != _HEADER:  # rejects alg=none and algorithm confusion
            raise fail
        if not hmac.compare_digest(_sign(secret, f"{header_b64}.{payload_b64}"), signature):
            raise fail
        claims = json.loads(_b64d(payload_b64))
    except AuthenticationError:
        raise
    except (ValueError, TypeError, UnicodeError):
        raise fail from None
    if (
        not isinstance(claims, dict) or claims.get("typ") != expected_type
        or not isinstance(claims.get("sub"), str) or not claims["sub"]
        or not isinstance(claims.get("exp"), int) or claims["exp"] <= int(now.timestamp())
    ):
        raise fail
    return claims


def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """SHA-256 of a high-entropy opaque token (refresh tokens, OAuth state) for DB storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
