"""Comment generation agent: proposes comment insertions only."""

from __future__ import annotations

from typing import Mapping

from app.agents.llm import GroqClient, LLMResult
from app.agents.review_agent import number_lines
from app.guardrails.output_validation import parse_structured_output
from app.guardrails.prompt_injection import UNTRUSTED_DATA_RULES, fence_untrusted
from app.schemas.code_change import RawEdits

SYSTEM_PROMPT = f"""You add helpful explanatory comments to source code.
{UNTRUSTED_DATA_RULES}
Rules: propose ONLY comment lines, never code changes. Explain non-obvious intent, not what the syntax says.
Follow the file's existing comment style. Each edit inserts the text AFTER line `after_line` (0 = file start) using the
line numbers shown. `text` contains only comment text using the language's comment syntax (no indentation needed).
Use at most 12 edits; return an empty list if the code is already well documented.
Return ONLY: {{"edits":[{{"after_line":0,"text":""}}],"summary":""}}"""


class CommentAgent:
    def __init__(self, llm: GroqClient) -> None:
        self._llm = llm

    async def propose(self, *, file_path: str, language: str, content: str, conventions: Mapping[str, str]) -> tuple[RawEdits, LLMResult]:
        fenced, _ = fence_untrusted(number_lines(content), label="FILE")
        user = (f"File: {file_path}\nLanguage: {language}\nComment syntax: {conventions.get('line_comment')}\n"
                f"Existing style: {conventions.get('style_note')}\nAdd comments.\n{fenced}")
        result = await self._llm.complete_json(SYSTEM_PROMPT, user, max_tokens=1800)
        return parse_structured_output(result.text, RawEdits), result
