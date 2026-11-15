"""Approval schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import StrictModel


class ActionRecordOut(StrictModel):
    id: str
    step: str
    status: str
    github_url: str | None
    github_number: int | None
    github_sha: str | None
    error_category: str | None
    created_at: datetime


class ApprovalOut(StrictModel):
    id: str
    artifact_id: str | None
    action_type: str
    owner: str
    repo: str
    state: str
    payload: dict[str, Any]
    payload_digest: str
    expires_at: datetime
    decided_at: datetime | None
    created_at: datetime
    actions: list[ActionRecordOut] = Field(default_factory=list)

    @classmethod
    def from_rows(cls, a, actions=()) -> "ApprovalOut":  # type: ignore[no-untyped-def]
        return cls(
            id=str(a.id), artifact_id=str(a.artifact_id) if a.artifact_id else None, action_type=a.action_type, owner=a.owner, repo=a.repo, state=a.state,
            payload=a.payload, payload_digest=a.payload_digest, expires_at=a.expires_at,
            decided_at=a.decided_at, created_at=a.created_at,
            actions=[ActionRecordOut(id=str(x.id), step=x.step, status=x.status, github_url=x.github_url,
                                     github_number=x.github_number, github_sha=x.github_sha,
                                     error_category=x.error_category, created_at=x.created_at) for x in actions],
        )


class DecisionBody(StrictModel):
    """Body for approve/reject: the digest of the content the user was shown."""

    displayed_payload_digest: str = Field(min_length=64, max_length=64)
