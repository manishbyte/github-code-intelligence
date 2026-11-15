"""Validate a proposed unified diff against the original file (no GitHub access)."""

from __future__ import annotations

import hashlib

from pydantic import Field

from app.core.constants import DEFAULT_MAX_SOURCE_FILE_BYTES, MAX_PATCH_BYTES
from app.core.exceptions import GuardrailViolation
from app.guardrails.patch_safety import validate_single_file_patch
from app.schemas.code_change import PatchValidationResult
from app.schemas.common import SecretFindingModel, StrictModel

TOOL_NAME = "validate_patch"


class ValidatePatchInput(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    original_content: str = Field(max_length=DEFAULT_MAX_SOURCE_FILE_BYTES * 2)
    diff: str = Field(min_length=1, max_length=MAX_PATCH_BYTES)
    include_patched_content: bool = True


def run(params: ValidatePatchInput) -> PatchValidationResult:
    try:
        result = validate_single_file_patch(
            params.diff, expected_path=params.path, original_content=params.original_content
        )
    except GuardrailViolation as exc:
        return PatchValidationResult(
            valid=False, errors=[exc.message], added_lines=0, removed_lines=0, hunk_count=0,
            secret_findings=[], patched_content=None, patched_sha256=None,
        )
    findings = [SecretFindingModel(rule=f.rule, line=f.line, preview=f.preview) for f in result.secret_findings]
    errors = ["Patch adds content that looks like a credential."] if findings else []
    return PatchValidationResult(
        valid=result.safe,
        errors=errors,
        added_lines=result.added_lines,
        removed_lines=result.removed_lines,
        hunk_count=result.hunk_count,
        secret_findings=findings,
        patched_content=result.patched_content if params.include_patched_content and result.safe else None,
        patched_sha256=hashlib.sha256(result.patched_content.encode("utf-8")).hexdigest(),
    )
