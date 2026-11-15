"""Declarative authorization policies (action -> permitted roles)."""

from __future__ import annotations

from app.authorization.roles import Role
from app.core.exceptions import PermissionDeniedError

_POLICY: dict[str, frozenset[Role]] = {
    "evaluation:run": frozenset({Role.ADMIN}),
    "evaluation:read": frozenset({Role.ADMIN, Role.RECRUITER}),
    "review:create": frozenset({Role.ADMIN, Role.USER}),
    "metrics:read": frozenset({Role.ADMIN}),
    "approval:decide": frozenset({Role.ADMIN, Role.USER}),
    "github:publish": frozenset({Role.ADMIN, Role.USER}),
}


def is_allowed(role: str, action: str) -> bool:
    try:
        return Role(role) in _POLICY.get(action, frozenset())
    except ValueError:
        return False


def require(role: str, action: str) -> None:
    if not is_allowed(role, action):
        raise PermissionDeniedError("You do not have permission for this action.")
