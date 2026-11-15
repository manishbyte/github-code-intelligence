"""Optional LLM-as-judge quality scoring (never used for safety verdicts)."""

from __future__ import annotations

import logging

from app.agents.evaluation_agent import EvaluationAgent

logger = logging.getLogger("app.evaluation.judge")

CRITERIA = {
    "review": "Findings are specific, correct, and grounded in the code; no invented problems; useful fixes.",
    "comment": "Comments are accurate, concise, explain intent rather than syntax, and match the file's style.",
    "logging": "Log statements are useful, well placed, appropriately leveled and never expose sensitive data.",
    "issue": "The issue text is clear, factual, actionable and supported by the evidence.",
}


class LLMJudge:
    def __init__(self, agent: EvaluationAgent) -> None:
        self._agent = agent

    async def score(self, kind: str, task_input: str, output: str) -> dict | None:
        criteria = CRITERIA.get(kind)
        if criteria is None:
            return None
        try:
            verdict, _ = await self._agent.judge(criteria=criteria, task_input=task_input, output=output)
        except Exception:  # judging is best-effort and must not fail a case
            logger.warning("judge_failed", extra={"kind": kind})
            return None
        return {"judge_score": verdict.score, "judge_reasoning": verdict.reasoning}
