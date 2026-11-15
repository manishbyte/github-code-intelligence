"""Logging generation agent: proposes single-line log statements only."""

from __future__ import annotations

from typing import Mapping

from app.agents.llm import GroqClient, LLMResult
from app.agents.review_agent import number_lines
from app.guardrails.output_validation import parse_structured_output
from app.guardrails.prompt_injection import UNTRUSTED_DATA_RULES, fence_untrusted
from app.schemas.code_change import RawEdits

SYSTEM_PROMPT = f"""You add useful, safe logging statements to source code.
{UNTRUSTED_DATA_RULES}
Rules: propose ONLY single-line log statements using the logger named in the conventions. Never log passwords, tokens,
secrets, API keys, credentials or whole request bodies. Prefer logging at function entry/exit of important operations
and in error-handling paths. Each edit inserts the statement AFTER line `after_line` using the line numbers shown, at a
position where a new statement is syntactically valid. Use at most 10 edits.
Return ONLY: {{"edits":[{{"after_line":1,"text":""}}],"summary":""}}"""


class LoggingAgent:
    def __init__(self, llm: GroqClient) -> None:
        self._llm = llm

    async def propose(self, *, file_path: str, language: str, content: str, conventions: Mapping[str, object]) -> tuple[RawEdits, LLMResult]:
        fenced, _ = fence_untrusted(number_lines(content), label="FILE")
        user = (f"File: {file_path}\nLanguage: {language}\nLogger to use: {conventions.get('logger')}\n"
                f"Example statement form: {conventions.get('example')}\nAdd logging.\n{fenced}")
        result = await self._llm.complete_json(SYSTEM_PROMPT, user, max_tokens=1500)
        return parse_structured_output(result.text, RawEdits), result
