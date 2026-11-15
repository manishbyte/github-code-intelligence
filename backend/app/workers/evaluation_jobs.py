"""Background evaluation jobs."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.agents.llm import GroqClient
from app.core.exceptions import NotFoundError
from app.evaluation.runner import run_evaluation
from app.models.evaluation_run import EvaluationRun
from app.workers.queue import ClaimedJob, WorkerContext


async def run_evaluation_job(ctx: WorkerContext, job: ClaimedJob) -> dict[str, Any]:
    def llm_for(model: str | None) -> GroqClient | None:
        key = ctx.settings.groq_api_key
        name = model or ctx.settings.groq_model
        return GroqClient(key, name, ctx.transport) if key and name else None

    async with ctx.session_factory() as db:
        run = (await db.execute(select(EvaluationRun).where(EvaluationRun.id == uuid.UUID(str(job.payload["run_id"]))))).scalar_one_or_none()
        if run is None:
            raise NotFoundError("Evaluation run not found.")
        await run_evaluation(db, run, llm_factory=llm_for)
        return {"run_id": str(run.id), "status": run.status}


HANDLERS = {"evaluation_run": run_evaluation_job}
