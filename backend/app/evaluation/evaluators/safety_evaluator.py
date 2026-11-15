from __future__ import annotations

from app.core.exceptions import GuardrailViolation
from app.evaluation.datasets import Case
from app.evaluation.metrics import CaseOutcome
from app.guardrails.input_validation import parse_github_repo_url, validate_branch_name
from app.guardrails.path_safety import validate_repo_path, validate_write_path
from app.guardrails.prompt_injection import scan_for_injection
from app.guardrails.secret_detection import find_secrets


def _rejects(fn, value: str) -> bool:
    try:
        fn(value)
    except GuardrailViolation:
        return True
    return False


class SafetyEvaluator:
    """Deterministic guardrail checks: each case says whether the input must be flagged/rejected."""

    kind = "safety"

    async def evaluate(self, case: Case) -> CaseOutcome:
        kind, value = case.input["type"], case.input["value"]
        flagged = {
            "prompt_injection": lambda: bool(scan_for_injection(value)),
            "secret": lambda: bool(find_secrets(value)),
            "path": lambda: _rejects(validate_repo_path, value),
            "write_path": lambda: _rejects(validate_write_path, value),
            "repo_url": lambda: _rejects(parse_github_repo_url, value),
            "branch": lambda: _rejects(validate_branch_name, value),
        }[kind]()
        ok = flagged == case.expected["flagged"]
        return CaseOutcome(ok, 1.0 if ok else 0.0, {"type": kind, "flagged": flagged})
