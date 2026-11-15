"""Outcome type and aggregate metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass
class CaseOutcome:
    passed: bool
    score: float
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    error: str | None = None  # infrastructure/model errors are counted separately from failures


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(p / 100 * len(ordered)) - 1))
    return float(ordered[rank])


def f1(precision: float, recall: float) -> float:
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def line_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


def summarize(outcomes: Sequence[CaseOutcome]) -> dict[str, Any]:
    scored = [o for o in outcomes if o.error is None]
    passed = sum(o.passed for o in scored)
    latencies = [o.latency_ms for o in outcomes]
    return {
        "total": len(outcomes), "passed": passed, "failed": len(scored) - passed,
        "errors": len(outcomes) - len(scored),
        "pass_rate": round(passed / len(scored), 4) if scored else 0.0,
        "mean_score": round(sum(o.score for o in scored) / len(scored), 4) if scored else 0.0,
        "latency_p50_ms": percentile(latencies, 50), "latency_p95_ms": percentile(latencies, 95),
    }


def aggregate(by_kind: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    scored = sum(m["total"] - m["errors"] for m in by_kind.values())
    passed = sum(m["passed"] for m in by_kind.values())
    safety = by_kind.get("safety")
    return {
        "total_cases": sum(m["total"] for m in by_kind.values()), "errors": sum(m["errors"] for m in by_kind.values()),
        "pass_rate": round(passed / scored, 4) if scored else 0.0,
        "safety_pass_rate": safety["pass_rate"] if safety else None,
    }
