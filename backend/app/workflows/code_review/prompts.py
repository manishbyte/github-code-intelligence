"""User-facing warning and reasoning templates for the review workflow."""

from __future__ import annotations

NO_ISSUE_DEFAULT = "No validated problems were found in this file."
ALL_REJECTED = " The model reported findings, but none passed evidence and line validation."


def injection_warning(lines: list[int]) -> str:
    shown = ", ".join(str(n) for n in lines[:5])
    return f"Possible prompt-injection text was found in the file (lines {shown}); it was treated strictly as data."


def secret_warning(count: int) -> str:
    return f"{count} potential secret(s) were detected and redacted before analysis."
