"""Role checks mirrored from the backend (the backend remains the source of truth)."""

from __future__ import annotations

from typing import Any, Mapping

EVALUATION_READ_ROLES = ("admin", "recruiter")
EVALUATION_RUN_ROLES = ("admin",)


def can_view_evaluation(user: Mapping[str, Any]) -> bool:
    return user.get("role") in EVALUATION_READ_ROLES


def can_run_evaluation(user: Mapping[str, Any]) -> bool:
    return user.get("role") in EVALUATION_RUN_ROLES
