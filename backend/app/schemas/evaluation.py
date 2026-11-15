"""Evaluation schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import StrictModel

EvaluationKind = Literal["tree", "review", "issue", "comment", "logging", "patch", "safety", "all"]


class EvaluationRunRequest(StrictModel):
    kind: EvaluationKind = "all"
    model: str | None = Field(default=None, max_length=100)


class EvaluationRunOut(StrictModel):
    id: str
    kind: str
    model: str | None
    status: str
    metrics: dict[str, Any] | None
    regression: dict[str, Any] | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_row(cls, r) -> "EvaluationRunOut":  # type: ignore[no-untyped-def]
        return cls(id=str(r.id), kind=r.kind, model=r.model, status=r.status, metrics=r.metrics,
                   regression=r.regression, error=r.error, created_at=r.created_at, completed_at=r.completed_at)


class EvaluationSummaryOut(StrictModel):
    total_runs: int
    latest: list[EvaluationRunOut]
    pass_rate_by_kind: dict[str, float]
