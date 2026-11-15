"""Issue proposal schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.approval import ApprovalOut
from app.schemas.common import StrictModel


class IssueDraft(BaseModel):
    """LLM output; the issue body is assembled deterministically from validated findings."""

    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=5, max_length=120)
    summary: str = Field(min_length=10, max_length=1500)
    impact: str = Field(min_length=5, max_length=1000)
    suggested_fix: str | None = Field(default=None, max_length=1500)


class IssueProposalRequest(StrictModel):
    finding_ids: list[uuid.UUID] | None = Field(default=None, max_length=25)


class DuplicateCandidate(StrictModel):
    number: int
    title: str
    url: str
    similarity: float


class IssueProposalOut(StrictModel):
    id: str
    analysis_id: str
    owner: str
    repo: str
    title: str
    body: str
    duplicate_candidates: list[DuplicateCandidate]
    approval: ApprovalOut
    created_at: datetime
