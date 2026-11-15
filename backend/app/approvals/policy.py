"""Approval policy: lifetimes, action types and required GitHub scopes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from app.core.exceptions import ApprovalError

APPROVAL_TTL = timedelta(hours=24)
ACTION_CREATE_ISSUE = "create_issue"
ACTION_CODE_CHANGE = "publish_code_change"
ACTION_TYPES = frozenset({ACTION_CREATE_ISSUE, ACTION_CODE_CHANGE})
WRITE_SCOPES = frozenset({"public_repo", "repo"})
CODE_CHANGE_STEPS = ("create_branch", "commit_file", "create_pull_request")
STEP_PAYLOAD_KEYS = {"create_branch": "branch", "commit_file": "commit", "create_pull_request": "pull_request"}


def expiry(now: datetime) -> datetime:
    return now + APPROVAL_TTL


def has_write_scope(scopes: Sequence[str] | None) -> bool:
    return bool(scopes) and bool(WRITE_SCOPES.intersection(scopes))


def step_payloads(action_type: str, payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Map each GitHub write step to the exact payload that was approved."""
    if action_type == ACTION_CREATE_ISSUE:
        return {"create_issue": payload}
    if action_type == ACTION_CODE_CHANGE:
        try:
            return {step: payload[key] for step, key in STEP_PAYLOAD_KEYS.items()}
        except KeyError:
            raise ApprovalError("The approval payload is malformed.") from None
    raise ApprovalError("Unsupported approval action type.")
