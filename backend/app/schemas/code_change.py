"""Schemas for patch validation, quality checks and evidence validation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.approval import ApprovalOut
from app.schemas.common import SecretFindingModel, StrictModel


class PatchValidationResult(StrictModel):
    valid: bool
    errors: list[str]
    added_lines: int
    removed_lines: int
    hunk_count: int
    secret_findings: list[SecretFindingModel]
    patched_content: str | None
    patched_sha256: str | None


class QualityCheck(StrictModel):
    name: str
    status: Literal["passed", "failed", "skipped"]
    message: str


class QualityCheckResult(StrictModel):
    passed: bool
    checks: list[QualityCheck]
    executed_repository_code: Literal[False] = False


class LineRangeResult(StrictModel):
    index: int
    valid: bool
    reason: str | None


class LanguageResult(StrictModel):
    language: str | None
    method: Literal["filename", "extension", "shebang", "unknown"]


class RawEdit(BaseModel):
    """One insertion proposed by the model: ``text`` goes after line ``after_line`` (0 = file start)."""

    model_config = ConfigDict(extra="ignore")
    after_line: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=600)
    


class RawEdits(BaseModel):
    model_config = ConfigDict(extra="ignore")
    edits: list[RawEdit] = Field(default_factory=list, max_length=20)
    summary: str = Field(default="Proposed insertions.", min_length=3, max_length=2000)


class CodeChangeRequest(StrictModel):
    repository_id: uuid.UUID
    file_path: str = Field(min_length=1, max_length=1024)
    commit_sha: str | None = Field(default=None, min_length=40, max_length=64)


class CodeChangeProposalOut(StrictModel):
    id: str
    kind: str
    owner: str
    repo: str
    file_path: str
    base_commit_sha: str
    base_blob_sha: str
    summary: str
    diff: str
    quality: QualityCheckResult
    approval: ApprovalOut
    created_at: datetime
