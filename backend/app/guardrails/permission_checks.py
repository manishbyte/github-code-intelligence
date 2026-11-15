"""Deterministic permission decisions based on GitHub-reported evidence only."""

from __future__ import annotations

from typing import Literal

from app.core.exceptions import PermissionDeniedError
from app.integrations.github.permissions import RepositoryAccess

RequiredPermission = Literal["push", "issue"]


def require_write_permission(access: RepositoryAccess, required: RequiredPermission) -> None:
    if required == "push" and not access.can_push:
        raise PermissionDeniedError("The connected GitHub account cannot write to this repository.")
    if required == "issue" and not access.can_create_issue:
        raise PermissionDeniedError("Issues cannot be created in this repository.")
