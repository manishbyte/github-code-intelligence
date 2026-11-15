"""Repository path validation: traversal, control characters, protected paths."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote

from app.core.constants import MAX_PATH_LENGTH, PROTECTED_WRITE_PATH_PREFIXES
from app.core.exceptions import InvalidInputError

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _check_segments(path: str) -> None:
    for segment in path.split("/"):
        if segment in {"", ".", ".."} or segment.lower() == ".git":
            raise InvalidInputError("Path contains a forbidden segment.")


def validate_repo_path(
    path: str, *, allow_trailing_slash: bool = False, allow_root: bool = False
) -> str:
    """Return a normalized repository-relative path or raise ``InvalidInputError``."""
    if not isinstance(path, str):
        raise InvalidInputError("Path must be a string.")
    if path in {"", "/"} and allow_root:
        return ""
    if not path or len(path) > MAX_PATH_LENGTH:
        raise InvalidInputError("Path is empty or too long.")
    if "\\" in path or path.startswith("/") or _DRIVE_RE.match(path):
        raise InvalidInputError("Path must be relative and use forward slashes.")
    for ch in path:
        if unicodedata.category(ch) in {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}:
            raise InvalidInputError("Path contains control or invisible characters.")
    normalized = path
    if allow_trailing_slash and normalized.endswith("/"):
        normalized = normalized[:-1]
    _check_segments(normalized)
    decoded = unquote(normalized)
    if decoded != normalized:
        if "\\" in decoded or decoded.startswith("/"):
            raise InvalidInputError("Path contains an encoded separator.")
        _check_segments(decoded)
    return normalized


def validate_write_path(path: str) -> str:
    """Validate a path the application is allowed to modify on GitHub."""
    normalized = validate_repo_path(path)
    lowered = normalized.lower() + "/"
    if any(lowered.startswith(prefix) for prefix in PROTECTED_WRITE_PATH_PREFIXES):
        raise InvalidInputError("Writing to this path is not permitted.")
    return normalized
