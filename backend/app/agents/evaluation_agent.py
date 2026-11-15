"""LLM-as-judge agent used by the evaluation module (scores quality; never gates safety)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.agents.llm import GroqClient, LLMResult
from app.guardrails.output_validation import parse_structured_output
from app.guardrails.prompt_injection import UNTRUSTED_DATA_RULES, fence_untrusted


class JudgeVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore")
    score: int = Field(ge=1, le=5)
    reasoning: str = Field(min_length=3, max_length=1000)


SYSTEM_PROMPT = f"""You are a strict evaluator of AI-generated software engineering output.
{UNTRUSTED_DATA_RULES}
Score 1 (unusable) to 5 (excellent) against the given criteria only. Return ONLY: {{"score":1,"reasoning":""}}"""


class EvaluationAgent:
    def __init__(self, llm: GroqClient) -> None:
        self._llm = llm

    async def judge(self, *, criteria: str, task_input: str, output: str) -> tuple[JudgeVerdict, LLMResult]:
        fenced_in, _ = fence_untrusted(task_input[:6000], label="INPUT")
        fenced_out, _ = fence_untrusted(output[:6000], label="OUTPUT")
        user = f"Criteria: {criteria}\n{fenced_in}\n{fenced_out}"
        result = await self._llm.complete_json(SYSTEM_PROMPT, user, max_tokens=400)
        return parse_structured_output(result.text, JudgeVerdict), result
