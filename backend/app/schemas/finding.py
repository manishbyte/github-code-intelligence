"""Review finding schemas: strict LLM output contract and API output."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import StrictModel

Severity = Literal["low", "medium", "high", "critical"]
Category = Literal["bug", "security", "performance", "maintainability", "reliability", "documentation", "style"]


class RawFinding(BaseModel):
    """One finding as produced by the model; validated deterministically afterwards."""

    model_config = ConfigDict(extra="ignore")
    category: Category
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=2000)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    evidence: str = Field(min_length=3, max_length=1000)
    suggested_fix: str | None = Field(default=None, max_length=2000)


class RawReview(BaseModel):
    model_config = ConfigDict(extra="ignore")
    findings: list[RawFinding] = Field(default_factory=list, max_length=50)
    decision: Literal["issue", "no_issue"]
    reasoning: str = Field(min_length=3, max_length=2000)


class FindingOut(StrictModel):
    id: str
    category: str
    severity: str
    confidence: float
    title: str
    description: str
    start_line: int
    end_line: int
    evidence: str
    suggested_fix: str | None
    validated: bool

    @classmethod
    def from_row(cls, f) -> "FindingOut":  # type: ignore[no-untyped-def]
        return cls(id=str(f.id), category=f.category, severity=f.severity, confidence=f.confidence,
                   title=f.title, description=f.description, start_line=f.start_line, end_line=f.end_line,
                   evidence=f.evidence, suggested_fix=f.suggested_fix, validated=f.validated)


def parse_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)
