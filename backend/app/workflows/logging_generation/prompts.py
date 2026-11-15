"""Commit and pull-request text for logging proposals."""

from __future__ import annotations

SLUG = "logging"
KIND = "logging"
ARTIFACT_KIND = "logging_patch"


def commit_message(path: str, summary: str) -> str:
    return f"chore: add logging to {path}\n\n{summary}"[:900]


def pr_title(path: str) -> str:
    return f"Add logging to {path}"[:200]


def pr_body(path: str, summary: str, edits: int) -> str:
    return (
        "Proposed by GitHub Code Intelligence and approved by a human before publishing.\n\n"
        f"**File:** `{path}`\n**Change:** {summary}\n**Edits:** {edits} log statement insertion(s) using the file's existing logger; "
        "no existing code lines were modified and no sensitive identifiers are logged.\n\n"
        "The change passed patch-safety, secret and syntax validation before approval."
    )[:20000]
