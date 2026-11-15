from __future__ import annotations

from app.core.exceptions import GuardrailViolation
from app.evaluation.datasets import Case
from app.evaluation.metrics import CaseOutcome
from app.guardrails.patch_safety import validate_single_file_patch


class PatchEvaluator:
    kind = "patch"

    async def evaluate(self, case: Case) -> CaseOutcome:
        i, exp = case.input, case.expected
        reason = ""
        try:
            result = validate_single_file_patch(i["diff"], expected_path=i["path"], original_content=i["original"])
            valid = result.safe
            reason = "secret" if not result.safe else ""
        except GuardrailViolation as exc:
            valid, reason = False, exc.message
        checks = {"validity": valid == exp["valid"]}
        if exp.get("reason_contains"):
            checks["reason"] = exp["reason_contains"].lower() in reason.lower()
        passed = all(checks.values())
        return CaseOutcome(passed, sum(checks.values()) / len(checks), {"valid": valid, "reason": reason[:200]})
