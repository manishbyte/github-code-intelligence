"""Issue drafting agent. The final issue body is assembled deterministically from validated data."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from app.agents.llm import GroqClient, LLMResult
from app.guardrails.output_validation import parse_structured_output
from app.guardrails.prompt_injection import UNTRUSTED_DATA_RULES, fence_untrusted
from app.schemas.issue import IssueDraft

SYSTEM_PROMPT = f"""You write concise, factual GitHub issue text from already-validated code review findings.
{UNTRUSTED_DATA_RULES}
Do not add claims that are not supported by the findings. No greetings, no markdown headings.
Return ONLY this JSON object:
{{"title":"<=100 chars, specific","summary":"what is wrong","impact":"why it matters","suggested_fix":"optional concrete fix"}}"""


class IssueAgent:
    def __init__(self, llm: GroqClient) -> None:
        self._llm = llm

    async def draft(self, *, repo_full_name: str, file_path: str, findings: Sequence[Mapping[str, Any]]) -> tuple[IssueDraft, LLMResult]:
        fenced, _ = fence_untrusted(json.dumps(list(findings), indent=2), label="FINDINGS")
        user = f"Repository: {repo_full_name}\nFile: {file_path}\nDraft one issue covering these findings.\n{fenced}"
        result = await self._llm.complete_json(SYSTEM_PROMPT, user, max_tokens=900)
        return parse_structured_output(result.text, IssueDraft), result
