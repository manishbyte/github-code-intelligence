"""Validate that reported line ranges and evidence exist in the analyzed file."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from app.guardrails.patch_safety import split_lines

_WS_RE = re.compile(r"\s+")
MAX_RANGE_SPAN = 500


@dataclass(frozen=True)
class LineRangeCheck:
    start_line: int
    end_line: int
    evidence: str | None = None


@dataclass(frozen=True)
class LineRangeVerdict:
    valid: bool
    reason: str | None = None


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def validate_line_range(
    content: str, check: LineRangeCheck, *, require_evidence: bool = True
) -> LineRangeVerdict:
    lines = split_lines(content)
    total = len(lines)
    if check.start_line < 1 or check.end_line < check.start_line:
        return LineRangeVerdict(False, "Line range is malformed.")
    if check.end_line > total:
        return LineRangeVerdict(False, f"Line range exceeds file length ({total} lines).")
    if check.end_line - check.start_line + 1 > MAX_RANGE_SPAN:
        return LineRangeVerdict(False, "Line range is too large.")
    evidence = _norm(check.evidence) if check.evidence else ""
    if not evidence:
        if require_evidence:
            return LineRangeVerdict(False, "Evidence is required.")
        return LineRangeVerdict(True)
    if len(evidence) < 3:
        return LineRangeVerdict(False, "Evidence is too short.")
    window = _norm(" ".join(lines[check.start_line - 1 : check.end_line]))
    if evidence not in window:
        return LineRangeVerdict(False, "Evidence does not appear in the referenced lines.")
    return LineRangeVerdict(True)


def validate_line_ranges(
    content: str, checks: Sequence[LineRangeCheck], *, require_evidence: bool = True
) -> list[LineRangeVerdict]:
    return [validate_line_range(content, c, require_evidence=require_evidence) for c in checks]
