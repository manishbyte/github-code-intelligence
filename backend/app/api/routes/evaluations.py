from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.dependencies import DB, CurrentUser, permission
from app.evaluation import reports
from app.guardrails.rate_limits import enforce
from app.guardrails.sql_and_data_safety import clamp_page
from app.models.evaluation_run import EvaluationRun
from app.observability.audit import record_audit
from app.schemas.evaluation import EvaluationRunOut, EvaluationRunRequest
from app.workers.queue import enqueue

router = APIRouter(prefix="/evaluations", tags=["evaluations"])
READ = permission("evaluation:read")
RUN = permission("evaluation:run")


async def _run(db, run_id: uuid.UUID) -> EvaluationRun:
    run = (await db.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise NotFoundError("Evaluation run not found.")
    return run


@router.post("/runs", status_code=202, response_model=EvaluationRunOut, dependencies=[RUN])
async def start_run(body: EvaluationRunRequest, user: CurrentUser, db: DB) -> EvaluationRunOut:
    await enforce(db, "evaluation", str(user.id))
    run = EvaluationRun(requested_by=user.id, kind=body.kind, model=body.model, status="queued")
    db.add(run)
    await db.flush()
    await enqueue(db, kind="evaluation_run", user_id=user.id, payload={"run_id": str(run.id)})
    await record_audit(db, event_type="evaluation.queued", user_id=user.id, entity_type="evaluation_run", entity_id=str(run.id))
    await db.commit()
    return EvaluationRunOut.from_row(run)


@router.get("/runs", response_model=list[EvaluationRunOut], dependencies=[READ])
async def list_runs(db: DB, limit: int = 20, offset: int = 0, kind: str | None = Query(default=None, max_length=30)) -> list[EvaluationRunOut]:
    limit, offset = clamp_page(limit, offset)
    q = select(EvaluationRun)
    if kind:
        q = q.where(EvaluationRun.kind == kind)
    rows = (await db.execute(q.order_by(EvaluationRun.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return [EvaluationRunOut.from_row(r) for r in rows]


@router.get("/overview", dependencies=[READ])
async def overview(db: DB) -> dict:
    return await reports.overview(db)


@router.get("/comparison", dependencies=[READ])
async def comparison(db: DB) -> dict:
    return await reports.comparison(db)


@router.get("/runs/{run_id}", response_model=EvaluationRunOut, dependencies=[READ])
async def get_run(run_id: uuid.UUID, db: DB) -> EvaluationRunOut:
    return EvaluationRunOut.from_row(await _run(db, run_id))


@router.get("/runs/{run_id}/metrics", dependencies=[READ])
async def get_metrics(run_id: uuid.UUID, db: DB) -> dict:
    run = await _run(db, run_id)
    return {"run_id": str(run.id), "status": run.status, "metrics": run.metrics or {}, "regression": run.regression}


@router.get("/runs/{run_id}/cases", dependencies=[READ])
async def get_cases(run_id: uuid.UUID, db: DB, failed_only: bool = False) -> list[dict]:
    await _run(db, run_id)
    return await reports.run_cases(db, run_id, failed_only=failed_only)


@router.get("/reports/{run_id}/export", response_class=PlainTextResponse, dependencies=[READ])
async def export_report(run_id: uuid.UUID, db: DB, format: str = Query(default="csv", pattern="^(csv|md|json)$")) -> PlainTextResponse:
    await _run(db, run_id)
    content, media = await reports.export_run(db, run_id, format)
    return PlainTextResponse(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="evaluation-{run_id}.{format}"'})
