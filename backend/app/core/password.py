"""Password hashing with scrypt (stdlib) and a minimum-strength policy."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from app.core.exceptions import InvalidInputError

_N, _R, _P, _DKLEN = 2**15, 8, 1, 32
_MAXMEM = 128 * _N * _R * 2
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256


def validate_password_strength(password: str) -> None:
    if not isinstance(password, str) or not (MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH):
        raise InvalidInputError(f"Password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters.")
    if len(set(password)) < 5 or password.strip() == "":
        raise InvalidInputError("Password is too simple.")


def _derive(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=128 * n * r * 2 + 1024 * 1024)


def hash_password(password: str) -> str:
    validate_password_strength(password)
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt, _N, _R, _P, _DKLEN)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification; returns False for malformed hashes."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = _derive(password, base64.b64decode(salt), int(n), int(r), int(p), len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str) -> bool:
    return not stored.startswith(f"scrypt${_N}${_R}${_P}$")
