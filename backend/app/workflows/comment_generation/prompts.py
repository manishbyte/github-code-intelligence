"""Commit and pull-request text for comment proposals."""

from __future__ import annotations

SLUG = "comments"
KIND = "comment"
ARTIFACT_KIND = "comment_patch"


def commit_message(path: str, summary: str) -> str:
    return f"docs: add explanatory comments to {path}\n\n{summary}"[:900]


def pr_title(path: str) -> str:
    return f"Add explanatory comments to {path}"[:200]


def pr_body(path: str, summary: str, edits: int) -> str:
    return (
        "Proposed by GitHub Code Intelligence and approved by a human before publishing.\n\n"
        f"**File:** `{path}`\n**Change:** {summary}\n**Edits:** {edits} comment insertion(s); no existing code lines were modified.\n\n"
        "The change passed patch-safety, secret and syntax validation before approval."
    )[:20000]
