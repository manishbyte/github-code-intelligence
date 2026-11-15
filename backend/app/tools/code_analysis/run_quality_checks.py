"""Static quality checks on patched content. Never executes repository code."""

from __future__ import annotations

import ast
import json
import tomllib

from pydantic import Field

from app.core.constants import DEFAULT_MAX_SOURCE_FILE_BYTES
from app.guardrails.patch_safety import is_binary_text, split_lines
from app.schemas.code_change import QualityCheck, QualityCheckResult
from app.schemas.common import StrictModel
from app.tools.code_analysis.detect_language import guess_language

TOOL_NAME = "run_quality_checks"


class RunQualityChecksInput(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    original_content: str = Field(max_length=DEFAULT_MAX_SOURCE_FILE_BYTES * 2)
    patched_content: str = Field(max_length=DEFAULT_MAX_SOURCE_FILE_BYTES * 2)
    max_bytes: int = Field(default=DEFAULT_MAX_SOURCE_FILE_BYTES, ge=1, le=5_000_000)


def _syntax_ok(language: str | None, text: str) -> tuple[bool | None, str]:
    """Return (ok, message); ok is None when no checker exists for the language."""
    try:
        if language == "python":
            ast.parse(text)
        elif language == "json":
            json.loads(text)
        elif language == "toml":
            tomllib.loads(text)
        else:
            return None, "No static syntax checker available for this language."
    except (SyntaxError, ValueError, RecursionError) as exc:  # tomllib errors subclass ValueError
        return False, f"Syntax error: {type(exc).__name__}"
    return True, "Syntax is valid."


def _eol_style(text: str) -> str:
    lines = split_lines(text)
    crlf = sum(1 for ln in lines if ln.endswith("\r\n"))
    lf = sum(1 for ln in lines if ln.endswith("\n") and not ln.endswith("\r\n"))
    return "mixed" if crlf and lf else "crlf" if crlf else "lf"


def run(params: RunQualityChecksInput) -> QualityCheckResult:
    new, old = params.patched_content, params.original_content
    checks: list[QualityCheck] = []

    size = len(new.encode("utf-8"))
    checks.append(QualityCheck(
        name="size_limit", status="passed" if size <= params.max_bytes else "failed",
        message=f"Patched file is {size} bytes (limit {params.max_bytes}).",
    ))
    checks.append(QualityCheck(
        name="text_content", status="failed" if is_binary_text(new) else "passed",
        message="Content contains NUL bytes." if is_binary_text(new) else "Content is text.",
    ))
    before, after = _eol_style(old), _eol_style(new)
    eol_ok = after == before or after == "lf" and not split_lines(old)
    checks.append(QualityCheck(
        name="line_endings", status="passed" if eol_ok else "failed",
        message=f"Line endings {before} -> {after}.",
    ))
    trailing_ok = old.endswith("\n") == new.endswith("\n") if old and new else True
    checks.append(QualityCheck(
        name="trailing_newline", status="passed" if trailing_ok else "failed",
        message="Trailing newline preserved." if trailing_ok else "Trailing newline changed.",
    ))

    language = guess_language(params.path, split_lines(new)[0].strip() if new else None).language
    new_ok, message = _syntax_ok(language, new)
    if new_ok is None:
        checks.append(QualityCheck(name="syntax", status="skipped", message=message))
    elif new_ok:
        checks.append(QualityCheck(name="syntax", status="passed", message=message))
    else:
        old_ok, _ = _syntax_ok(language, old)
        if old_ok is False:
            checks.append(QualityCheck(name="syntax", status="skipped", message="Original file was already invalid."))
        else:
            checks.append(QualityCheck(name="syntax", status="failed", message=message))

    return QualityCheckResult(passed=all(c.status != "failed" for c in checks), checks=checks)
