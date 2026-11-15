"""Verify LLM-reported line ranges and evidence against the real file content."""

from __future__ import annotations

from pydantic import Field

from app.core.constants import DEFAULT_MAX_SOURCE_FILE_BYTES
from app.guardrails.evidence_validation import LineRangeCheck, validate_line_ranges
from app.schemas.code_change import LineRangeResult
from app.schemas.common import StrictModel

TOOL_NAME = "validate_line_ranges"


class LineRangeInput(StrictModel):
    start_line: int
    end_line: int
    evidence: str | None = Field(default=None, max_length=2000)


class ValidateLineRangesInput(StrictModel):
    content: str = Field(max_length=DEFAULT_MAX_SOURCE_FILE_BYTES * 2)
    ranges: list[LineRangeInput] = Field(min_length=1, max_length=200)
    require_evidence: bool = True


def run(params: ValidateLineRangesInput) -> list[LineRangeResult]:
    checks = [LineRangeCheck(r.start_line, r.end_line, r.evidence) for r in params.ranges]
    verdicts = validate_line_ranges(params.content, checks, require_evidence=params.require_evidence)
    return [LineRangeResult(index=i, valid=v.valid, reason=v.reason) for i, v in enumerate(verdicts)]
