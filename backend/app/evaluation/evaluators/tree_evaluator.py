from __future__ import annotations

from app.evaluation.datasets import Case
from app.evaluation.metrics import CaseOutcome
from app.integrations.github.trees import normalize_tree_entries


class TreeEvaluator:
    kind = "tree"

    async def evaluate(self, case: Case) -> CaseOutcome:
        entries, skipped = normalize_tree_entries(case.input["entries"])
        checks: dict[str, bool] = {}
        exp = case.expected
        if "paths" in exp:
            checks["paths"] = [e.path for e in entries] == exp["paths"]
        if "skipped" in exp:
            checks["skipped"] = skipped == exp["skipped"]
        if "kinds" in exp:
            kinds = {e.path: e.kind for e in entries}
            checks["kinds"] = all(kinds.get(p) == k for p, k in exp["kinds"].items())
        passed = all(checks.values()) if checks else False
        return CaseOutcome(passed, sum(checks.values()) / len(checks) if checks else 0.0, {"checks": checks, "skipped": skipped})
