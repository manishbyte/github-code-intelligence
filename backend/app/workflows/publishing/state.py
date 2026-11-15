from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, TypedDict

from app.guardrails.action_policy import ApprovedAction
from app.tools import WriteToolContext


class PublishState(TypedDict, total=False):
    results: list[dict[str, Any]]


@dataclass
class PublishDeps:
    ctx: WriteToolContext
    base: ApprovedAction  # PUBLISHING capability; per-step copies are derived from it
    action_kind: str  # create_issue | publish_code_change
    approval_payload: Mapping[str, Any]
    artifact_payload: Mapping[str, Any]
