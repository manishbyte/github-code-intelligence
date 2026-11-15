from __future__ import annotations

from app.agents.llm import GroqClient
from app.agents.review_agent import ReviewAgent
from app.evaluation.datasets import Case
from app.evaluation.judges.llm_judge import LLMJudge
from app.evaluation.metrics import CaseOutcome, line_overlap
from app.guardrails.secret_detection import find_secrets, redact_secrets
from app.tools.code_analysis.detect_language import guess_language
from app.workflows.code_review.validators import validate_review


class ReviewEvaluator:
    """Runs the real review pipeline (model + deterministic validation) against labelled cases."""

    kind = "review"

    def __init__(self, llm: GroqClient | None, judge: LLMJudge | None = None) -> None:
        self.llm, self.judge = llm, judge

    async def evaluate(self, case: Case) -> CaseOutcome:
        if self.llm is None:
            return CaseOutcome(False, 0.0, error="LLM is not configured")
        path, content = case.input["file_path"], case.input["content"]
        redacted = redact_secrets(content)
        raw, result = await ReviewAgent(self.llm).review(file_path=path, language=guess_language(path).language, content=redacted, warnings=[])
        v = validate_review(raw, content=redacted, secret_findings=find_secrets(content))
        expected = case.expected.get("findings", [])

        def matches(e: dict, f) -> bool:
            return line_overlap(e["start_line"], e["end_line"], f.start_line, f.end_line) and e.get("category") in (None, f.category)

        recall = sum(any(matches(e, f) for f in v.findings) for e in expected) / len(expected) if expected else 1.0
        precision = (sum(any(matches(e, f) for e in expected) for f in v.findings) / len(v.findings)) if v.findings else 1.0
        decision_ok = v.decision == case.expected["decision"]
        hallucinated = len(raw.findings) - len(v.findings) if raw.findings else 0
        score = round(0.4 * decision_ok + 0.3 * recall + 0.3 * precision, 4)
        details = {"decision": v.decision, "recall": recall, "precision": precision, "findings": len(v.findings),
                   "rejected_by_validation": max(0, hallucinated), "tokens": result.usage}
        if self.judge is not None:
            details.update(await self.judge.score("review", content, "\n".join(f"{f.title}: {f.description}" for f in v.findings) or v.reasoning) or {})
        return CaseOutcome(decision_ok and recall >= 0.5, score, details, result.latency_ms)
