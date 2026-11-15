"""Deterministic pieces of issue creation: finding selection, duplicate detection, body assembly."""

from __future__ import annotations

import difflib
import re
from typing import Any, Sequence

from app.core.constants import MAX_ISSUE_BODY_LENGTH
from app.core.exceptions import InvalidInputError
from app.guardrails.output_validation import sanitize_text
from app.guardrails.secret_detection import find_secrets
from app.schemas.issue import IssueDraft

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_WORD = re.compile(r"[a-z0-9]+")


def select_findings(rows: Sequence[Any], finding_ids: Sequence[Any] | None, *, default_limit: int = 10) -> list[Any]:
    if finding_ids:
        wanted = {str(i) for i in finding_ids}
        chosen = [r for r in rows if str(r.id) in wanted]
        if len(chosen) != len(wanted):
            raise InvalidInputError("One or more findings do not belong to this review.")
        return chosen
    return sorted(rows, key=lambda r: (_SEVERITY_ORDER.get(r.severity, 9), -r.confidence, r.start_line))[:default_limit]


def title_similarity(a: str, b: str) -> float:
    wa, wb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    jaccard = len(wa & wb) / len(wa | wb) if wa | wb else 0.0
    ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return round(max(jaccard, ratio), 3)


def find_duplicates(title: str, existing: Sequence[tuple[int, str, str]], *, threshold: float = 0.8) -> list[dict[str, Any]]:
    """``existing`` holds (number, title, url) of open issues; returns likely duplicates, best first."""
    scored = [{"number": n, "title": t, "url": u, "similarity": title_similarity(title, t)} for n, t, u in existing]
    return sorted((s for s in scored if s["similarity"] >= threshold), key=lambda s: -s["similarity"])


def validate_issue_draft(draft: IssueDraft) -> IssueDraft:
    clean = IssueDraft(
        title=sanitize_text(draft.title, max_length=120).replace("\n", " "),
        summary=sanitize_text(draft.summary, max_length=1500), impact=sanitize_text(draft.impact, max_length=1000),
        suggested_fix=sanitize_text(draft.suggested_fix, max_length=1500) if draft.suggested_fix else None,
    )
    if find_secrets("\n".join([clean.title, clean.summary, clean.impact, clean.suggested_fix or ""])):
        raise InvalidInputError("The drafted issue contains what looks like a credential and was rejected.")
    return clean


def _fence(text: str) -> str:
    fence = "```"
    while fence in text:
        fence += "`"
    return fence


def compose_issue_body(draft: IssueDraft, findings: Sequence[dict[str, Any]], *, file_path: str, html_url: str, commit_sha: str) -> str:
    parts = [f"## Summary\n{draft.summary}", f"## Impact\n{draft.impact}", "## Findings"]
    for f in findings:
        link = f"{html_url}/blob/{commit_sha}/{file_path}#L{f['start_line']}-L{f['end_line']}"
        fence = _fence(f["evidence"])
        parts.append(
            f"### {f['title']}\n`{f['severity']}` · {f['category']} · confidence {int(f['confidence'] * 100)}%\n"
            f"`{file_path}` lines {f['start_line']}–{f['end_line']} ([view at commit]({link}))\n\n"
            f"{fence}\n{f['evidence']}\n{fence}\n\n{f['description']}"
        )
    if draft.suggested_fix:
        parts.append(f"## Suggested fix\n{draft.suggested_fix}")
    parts.append("---\n_Drafted with AI assistance (GitHub Code Intelligence) from validated evidence; reviewed and approved by a human before posting._")
    return "\n\n".join(parts)[:MAX_ISSUE_BODY_LENGTH]
