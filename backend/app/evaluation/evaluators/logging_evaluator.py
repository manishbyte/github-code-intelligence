from __future__ import annotations

import re

from app.agents.llm import GroqClient
from app.agents.logging_agent import LoggingAgent
from app.agents.patch_agent import PatchAgent, detect_logging_convention, validate_logging_edits
from app.core.exceptions import GuardrailViolation
from app.evaluation.datasets import Case
from app.evaluation.judges.llm_judge import LLMJudge
from app.evaluation.metrics import CaseOutcome
from app.guardrails.patch_safety import validate_single_file_patch
from app.guardrails.secret_detection import redact_secrets
from app.tools.code_analysis.detect_language import guess_language
from app.tools.code_analysis.run_quality_checks import RunQualityChecksInput, run as quality

_SENSITIVE = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|credential)")


class LoggingEvaluator:
    kind = "logging"

    def __init__(self, llm: GroqClient | None, judge: LLMJudge | None = None) -> None:
        self.llm, self.judge = llm, judge

    async def evaluate(self, case: Case) -> CaseOutcome:
        if self.llm is None:
            return CaseOutcome(False, 0.0, error="LLM is not configured")
        path, content = case.input["file_path"], case.input["content"]
        language = guess_language(path).language or ""
        conventions = detect_logging_convention(language, content)
        raw, result = await LoggingAgent(self.llm).propose(file_path=path, language=language, content=redact_secrets(content), conventions=conventions)
        checks = {"patch_built": False, "patch_safe": False, "quality": False, "no_code_removed": False, "no_sensitive_logging": False, "min_edits": False}
        diff = ""
        try:
            edits, dropped = validate_logging_edits(language, content, raw.edits, conventions)
            built = PatchAgent.build(path, content, edits, dropped)
            v = validate_single_file_patch(built.diff, expected_path=path, original_content=content)
            added = [ln for ln in built.diff.split("\n") if ln.startswith("+") and not ln.startswith("+++")]
            checks.update(patch_built=True, patch_safe=v.safe, no_code_removed=v.removed_lines == 0,
                          no_sensitive_logging=not any(_SENSITIVE.search(ln) for ln in added),
                          min_edits=built.applied_edits >= case.expected.get("min_edits", 1))
            checks["quality"] = quality(RunQualityChecksInput(path=path, original_content=content, patched_content=built.new_content)).passed
            diff = built.diff
        except GuardrailViolation:
            pass
        details = {"checks": checks}
        if self.judge is not None and diff:
            details.update(await self.judge.score("logging", content, diff) or {})
        return CaseOutcome(all(checks.values()), sum(checks.values()) / len(checks), details, result.latency_ms)
