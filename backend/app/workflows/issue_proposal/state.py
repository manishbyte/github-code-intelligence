from __future__ import annotations

from typing import Any, TypedDict


class IssueState(TypedDict, total=False):
    analysis_id: str
    finding_ids: list[str] | None
    run: Any
    repo: Any
    findings: list[dict[str, Any]]
    draft: Any
    duplicates: list[dict[str, Any]]
    warnings: list[str]
    payload: dict[str, Any]
    artifact_id: str
    approval_id: str
