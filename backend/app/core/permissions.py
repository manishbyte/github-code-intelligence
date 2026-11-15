"""Ownership and role checks. Cross-user access always looks like 'not found'."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.exceptions import NotFoundError, PermissionDeniedError

ADMIN_ROLES = frozenset({"admin"})


def ensure_owner(resource: Any, user_id: uuid.UUID, what: str = "Resource") -> Any:
    """Return ``resource`` only if it exists and belongs to ``user_id`` (404 otherwise, never 403)."""
    if resource is None or getattr(resource, "user_id", None) != user_id:
        raise NotFoundError(f"{what} not found.")
    return resource


def require_admin_role(role: str) -> None:
    if role not in ADMIN_ROLES:
        raise PermissionDeniedError("Administrator access is required.")
