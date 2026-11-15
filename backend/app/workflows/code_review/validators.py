"""Deterministic validation of model findings: schema is checked upstream; here we verify evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.guardrails.evidence_validation import LineRangeCheck, validate_line_range
from app.guardrails.output_validation import sanitize_text
from app.guardrails.secret_detection import SecretFinding
from app.schemas.finding import RawReview
from app.workflows.code_review.prompts import ALL_REJECTED, NO_ISSUE_DEFAULT

MIN_CONFIDENCE = 0.4
MAX_FINDINGS = 25
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass(frozen=True)
class ValidatedFinding:
    category: str
    severity: str
    confidence: float
    title: str
    description: str
    start_line: int
    end_line: int
    evidence: str
    suggested_fix: str | None


@dataclass(frozen=True)
class ValidatedReview:
    findings: tuple[ValidatedFinding, ...]
    rejected: tuple[str, ...]
    decision: str  # derived from validated findings only
    reasoning: str


def validate_review(raw: RawReview, *, content: str, secret_findings: Sequence[SecretFinding]) -> ValidatedReview:
    """``content`` must be exactly the text the model saw (redacted), so evidence matches verbatim."""
    accepted: list[ValidatedFinding] = []
    rejected: list[str] = []
    seen: set[tuple[int, int, str, str]] = set()
    for f in raw.findings:
        verdict = validate_line_range(content, LineRangeCheck(f.start_line, f.end_line, f.evidence))
        if not verdict.valid:
            rejected.append(f"{f.title[:60]}: {verdict.reason}")
            continue
        if f.confidence < MIN_CONFIDENCE:
            rejected.append(f"{f.title[:60]}: confidence below threshold")
            continue
        key = (f.start_line, f.end_line, f.category, f.title.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        accepted.append(ValidatedFinding(
            category=f.category, severity=f.severity, confidence=round(f.confidence, 3),
            title=sanitize_text(f.title, max_length=200), description=sanitize_text(f.description, max_length=2000),
            start_line=f.start_line, end_line=f.end_line, evidence=sanitize_text(f.evidence, max_length=1000),
            suggested_fix=sanitize_text(f.suggested_fix, max_length=2000) if f.suggested_fix else None,
        ))
    lines = content.split("\n")
    covered = {(a.start_line, a.category) for a in accepted}
    for s in secret_findings:  # deterministic findings never depend on the model
        if (s.line, "security") in covered:
            continue
        shown = lines[s.line - 1].strip()[:200] if 0 < s.line <= len(lines) else ""
        accepted.append(ValidatedFinding(
            category="security", severity="high", confidence=0.95, title="Potential hard-coded credential",
            description=f"A value matching the '{s.rule}' pattern appears in the source. Credentials should come from "
                        "a secret manager or environment, and exposed ones must be rotated.",
            start_line=s.line, end_line=s.line, evidence=shown or "[redacted]", suggested_fix="Remove the value from source control and rotate it.",
        ))
    accepted.sort(key=lambda a: (_SEVERITY_ORDER[a.severity], -a.confidence, a.start_line))
    accepted = accepted[:MAX_FINDINGS]
    reasoning = sanitize_text(raw.reasoning, max_length=1500)
    if not accepted:
        reasoning = (reasoning or NO_ISSUE_DEFAULT) + (ALL_REJECTED if raw.findings else "")
    return ValidatedReview(tuple(accepted), tuple(rejected), "issue" if accepted else "no_issue", reasoning)
