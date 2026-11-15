"""Compare an evaluation run with the previous comparable run (same kind and model)."""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation_run import EvaluationRun

DEFAULT_TOLERANCE = 0.05
STRICT_KINDS = frozenset({"safety", "patch"})  # deterministic guardrail suites must not regress at all


def compare(previous: Mapping[str, Any], current: Mapping[str, Any], *, tolerance: float = DEFAULT_TOLERANCE) -> dict[str, Any]:
    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    prev_kinds, cur_kinds = previous.get("by_kind", {}), current.get("by_kind", {})
    for kind, cur in cur_kinds.items():
        prev = prev_kinds.get(kind)
        if not prev:
            continue
        allowed = 0.0 if kind in STRICT_KINDS else tolerance
        for metric in ("pass_rate", "mean_score"):
            delta = round(cur[metric] - prev[metric], 4)
            row = {"kind": kind, "metric": metric, "previous": prev[metric], "current": cur[metric], "delta": delta}
            if delta < -allowed:
                regressions.append(row)
            elif delta > 0:
                improvements.append(row)
    return {"regressed": bool(regressions), "regressions": regressions, "improvements": improvements, "tolerance": tolerance}


async def previous_run(db: AsyncSession, run: EvaluationRun) -> EvaluationRun | None:
    q = select(EvaluationRun).where(
        EvaluationRun.status == "succeeded", EvaluationRun.kind == run.kind, EvaluationRun.id != run.id,
        EvaluationRun.created_at < run.created_at,
    )
    q = q.where(EvaluationRun.model == run.model) if run.model else q.where(EvaluationRun.model.is_(None))
    return (await db.execute(q.order_by(EvaluationRun.created_at.desc()).limit(1))).scalar_one_or_none()


async def compare_with_previous(db: AsyncSession, run: EvaluationRun) -> dict[str, Any] | None:
    prev = await previous_run(db, run)
    if prev is None or not prev.metrics or not run.metrics:
        return None
    return {"baseline_run_id": str(prev.id), **compare(prev.metrics, run.metrics)}
