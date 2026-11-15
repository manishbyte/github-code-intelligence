"""Code review agent: produces structured, evidence-based findings (validated afterwards)."""

from __future__ import annotations

from app.agents.llm import GroqClient, LLMResult
from app.guardrails.output_validation import parse_structured_output
from app.guardrails.prompt_injection import UNTRUSTED_DATA_RULES, fence_untrusted
from app.schemas.finding import RawReview

SYSTEM_PROMPT = f"""You are a meticulous senior code reviewer.
{UNTRUSTED_DATA_RULES}

Report only real, specific problems that are visible in the provided code. Do not invent issues, do not
comment on style unless it causes a defect, and prefer reporting nothing over speculation.
Each finding MUST include: category (bug|security|performance|maintainability|reliability|documentation|style),
severity (low|medium|high|critical), confidence (0..1), a short title, a description, start_line and end_line
(1-based, from the line numbers shown), evidence (an exact, verbatim quote from those lines, without the
line-number prefix) and optionally suggested_fix.
If the code has no real problems, return an empty findings list and decision "no_issue" with the reason.

Return ONLY this JSON object:
{{"findings":[{{"category":"","severity":"","confidence":0.0,"title":"","description":"","start_line":1,"end_line":1,"evidence":"","suggested_fix":""}}],
"decision":"issue|no_issue","reasoning":""}}"""


def number_lines(content: str) -> str:
    return "\n".join(f"{i}| {line}" for i, line in enumerate(content.split("\n"), start=1))


class ReviewAgent:
    def __init__(self, llm: GroqClient) -> None:
        self._llm = llm

    async def review(self, *, file_path: str, language: str | None, content: str, warnings: list[str]) -> tuple[RawReview, LLMResult]:
        fenced, _ = fence_untrusted(number_lines(content), label="FILE")
        notes = ("Heads-up: " + "; ".join(warnings) + "\n") if warnings else ""
        user = f"File: {file_path}\nLanguage: {language or 'unknown'}\n{notes}Review this file.\n{fenced}"
        result = await self._llm.complete_json(SYSTEM_PROMPT, user, max_tokens=3000)
        return parse_structured_output(result.text, RawReview), result
