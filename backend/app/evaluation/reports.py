"""Read models for the evaluation/recruiter dashboard and report export."""

from __future__ import annotations

import csv
import io
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation_case import EvaluationCase
from app.models.evaluation_case_result import EvaluationCaseResult
from app.models.evaluation_run import EvaluationRun


async def run_cases(db: AsyncSession, run_id: uuid.UUID, *, failed_only: bool = False) -> list[dict[str, Any]]:
    q = (select(EvaluationCaseResult, EvaluationCase.case_key).join(EvaluationCase, EvaluationCase.id == EvaluationCaseResult.case_id)
         .where(EvaluationCaseResult.run_id == run_id))
    if failed_only:
        q = q.where(EvaluationCaseResult.passed.is_(False))
    rows = (await db.execute(q.order_by(EvaluationCaseResult.kind, EvaluationCase.case_key))).all()
    return [{"case_key": key, "kind": r.kind, "passed": r.passed, "score": r.score, "latency_ms": r.latency_ms, "details": r.details}
            for r, key in rows]


async def _succeeded(db: AsyncSession, limit: int = 200) -> list[EvaluationRun]:
    return list((await db.execute(select(EvaluationRun).where(EvaluationRun.status == "succeeded", EvaluationRun.metrics.is_not(None))
                                  .order_by(EvaluationRun.created_at.desc()).limit(limit))).scalars())


async def overview(db: AsyncSession) -> dict[str, Any]:
    total = (await db.execute(select(func.count()).select_from(EvaluationRun))).scalar_one()
    latest: dict[str, dict[str, Any]] = {}
    runs = await _succeeded(db, 50)
    for run in runs:  # newest first: the first sighting of a kind is its latest result
        for kind, m in run.metrics.get("by_kind", {}).items():
            latest.setdefault(kind, {**m, "run_id": str(run.id), "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                                     "model": run.model})
    return {
        "total_runs": total, "latest_by_kind": latest,
        "safety_pass_rate": latest.get("safety", {}).get("pass_rate"),
        "recent_runs": [{"id": str(r.id), "kind": r.kind, "model": r.model, "created_at": r.created_at.isoformat(),
                         "pass_rate": r.metrics.get("overall", {}).get("pass_rate"),
                         "regressed": bool((r.regression or {}).get("regressed"))} for r in runs[:10]],
    }


async def comparison(db: AsyncSession) -> dict[str, Any]:
    models: dict[str, dict[str, Any]] = {}
    for run in await _succeeded(db):
        entry = models.setdefault(run.model or "unknown", {"model": run.model or "unknown", "kinds": {}, "runs": 0})
        entry["runs"] += 1
        for kind, m in run.metrics.get("by_kind", {}).items():
            entry["kinds"].setdefault(kind, {"pass_rate": m["pass_rate"], "mean_score": m["mean_score"], "latency_p50_ms": m["latency_p50_ms"]})
    return {"models": sorted(models.values(), key=lambda e: e["model"])}


async def export_run(db: AsyncSession, run_id: uuid.UUID, fmt: str) -> tuple[str, str]:
    run = (await db.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))).scalar_one()
    cases = await run_cases(db, run_id)
    if fmt == "json":
        return json.dumps({"run_id": str(run.id), "model": run.model, "metrics": run.metrics, "regression": run.regression, "cases": cases}, indent=2, default=str), "application/json"
    if fmt == "md":
        lines = [f"# Evaluation run {run.id}", f"Model: {run.model or 'n/a'}  Status: {run.status}", "", "| Kind | Total | Passed | Errors | Pass rate | Mean score | p95 ms |", "|---|---|---|---|---|---|---|"]
        for kind, m in (run.metrics or {}).get("by_kind", {}).items():
            lines.append(f"| {kind} | {m['total']} | {m['passed']} | {m['errors']} | {m['pass_rate']:.0%} | {m['mean_score']:.2f} | {m['latency_p95_ms']:.0f} |")
        return "\n".join(lines) + "\n", "text/markdown"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["case_key", "kind", "passed", "score", "latency_ms", "error"])
    for c in cases:
        writer.writerow([c["case_key"], c["kind"], c["passed"], c["score"], c["latency_ms"], (c["details"] or {}).get("error") or ""])
    return buf.getvalue(), "text/csv"
