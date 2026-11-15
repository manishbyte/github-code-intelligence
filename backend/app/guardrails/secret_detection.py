"""Heuristic credential detection. Findings never contain the full secret."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

_PLACEHOLDER_MARKERS = (
    "example", "changeme", "change_me", "placeholder", "your_", "your-", "replace",
    "xxxx", "****", "<", "${", "{{", "dummy", "sample", "fake", "redacted", "todo",
    "password", "secret_key", "localhost",
)

# (rule name, pattern, apply placeholder filter)
_RULES: tuple[tuple[str, re.Pattern[str], bool], ...] = (
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})\b"), False),
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), False),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY(?: BLOCK)?-----"), False),
    ("groq_api_key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"), False),
    ("llm_api_key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b"), False),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), False),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), False),
    ("stripe_live_key", re.compile(r"\b[rs]k_live_[0-9A-Za-z]{20,}\b"), False),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), False),
    (
        "hardcoded_credential",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|passwd|password|client[_-]?secret|access[_-]?key)\b"
            r"\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"
        ),
        True,
    ),
    (
        "credentials_in_url",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:@/]+:[^\s:@/]+@[^\s/]+", re.IGNORECASE),
        True,
    ),
)


@dataclass(frozen=True)
class SecretFinding:
    rule: str
    line: int
    preview: str  # redacted, never the full secret


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def find_secrets_in_lines(lines: Iterable[tuple[int, str]]) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for line_no, text in lines:
        for rule, pattern, filter_placeholders in _RULES:
            for match in pattern.finditer(text):
                value = match.group(0)
                if filter_placeholders and _is_placeholder(value):
                    continue
                findings.append(SecretFinding(rule=rule, line=line_no, preview=value[:4] + "***"))
    return findings


def find_secrets(text: str) -> list[SecretFinding]:
    return find_secrets_in_lines(enumerate(text.split("\n"), start=1))


def redact_secrets(text: str) -> str:
    """Replace detected secrets with ``[REDACTED:<rule>]`` (line structure preserved)."""
    out_lines = []
    for line in text.split("\n"):
        for rule, pattern, filter_placeholders in _RULES:
            line = pattern.sub(
                lambda m, r=rule, f=filter_placeholders: m.group(0)
                if f and _is_placeholder(m.group(0))
                else f"[REDACTED:{r}]",
                line,
            )
        out_lines.append(line)
    return "\n".join(out_lines)


def find_secrets_in_added_lines(old: str, new: str) -> list[SecretFinding]:
    """Scan only lines present in ``new`` that are not already in ``old`` (multiset diff)."""
    remaining = Counter(old.split("\n"))
    candidates: list[tuple[int, str]] = []
    for line_no, line in enumerate(new.split("\n"), start=1):
        if remaining[line] > 0:
            remaining[line] -= 1
        else:
            candidates.append((line_no, line))
    return find_secrets_in_lines(candidates)
