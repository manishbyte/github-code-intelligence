"""Review request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import StrictModel
from app.schemas.finding import FindingOut


class ReviewRequest(StrictModel):
    repository_id: uuid.UUID
    file_path: str = Field(min_length=1, max_length=1024)
    commit_sha: str | None = Field(default=None, min_length=40, max_length=64)


class ReviewRunOut(StrictModel):
    id: str
    repository_id: str | None
    file_path: str | None
    commit_sha: str | None
    status: str
    decision: str | None
    reasoning: str | None
    model: str | None
    warnings: list[str]
    findings: list[FindingOut]
    latency_ms: int | None
    created_at: datetime
    completed_at: datetime | None
    error: str | None

    @classmethod
    def from_rows(cls, run, findings) -> "ReviewRunOut":  # type: ignore[no-untyped-def]
        return cls(
            id=str(run.id), repository_id=str(run.repository_id) if run.repository_id else None,
            file_path=run.file_path, commit_sha=run.commit_sha, status=run.status, decision=run.decision,
            reasoning=run.reasoning, model=run.model, warnings=list(run.warnings or []),
            findings=[FindingOut.from_row(f) for f in findings], latency_ms=run.latency_ms,
            created_at=run.created_at, completed_at=run.completed_at, error=run.error,
        )


class HistoryItemOut(StrictModel):
    id: str
    kind: str
    status: str
    decision: str | None
    file_path: str | None
    repository: str | None
    created_at: datetime
    completed_at: datetime | None
