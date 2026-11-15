"""PostgreSQL-backed job queue (FOR UPDATE SKIP LOCKED). Run with: python -m app.workers.queue"""

from __future__ import annotations

import asyncio
import logging
import signal
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.llm import GroqClient
from app.config import Settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from app.core.token_encryption import TokenCipher
from app.integrations.github.client import HttpTransport
from app.models.background_job import BackgroundJob

logger = logging.getLogger("app.worker")
STALE_AFTER = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    kind: str
    user_id: uuid.UUID | None
    payload: Mapping[str, Any]
    attempts: int
    max_attempts: int


@dataclass
class WorkerContext:
    session_factory: async_sessionmaker[AsyncSession]
    settings: Settings
    transport: HttpTransport
    llm: GroqClient | None
    cipher: TokenCipher


JobHandler = Callable[[WorkerContext, ClaimedJob], Awaitable[dict[str, Any]]]


async def enqueue(
    db: AsyncSession, *, kind: str, payload: Mapping[str, Any], user_id: uuid.UUID | None = None,
    max_attempts: int = 3, run_after: datetime | None = None,
) -> BackgroundJob:
    job = BackgroundJob(kind=kind, payload=dict(payload), user_id=user_id, max_attempts=max_attempts,
                        run_after=run_after or _now(), status="queued")
    db.add(job)
    await db.flush()
    return job


async def claim_next(factory: async_sessionmaker[AsyncSession], worker_id: str, kinds: list[str]) -> ClaimedJob | None:
    async with factory() as s:
        row = (await s.execute(
            select(BackgroundJob)
            .where(BackgroundJob.status == "queued", BackgroundJob.run_after <= _now(), BackgroundJob.kind.in_(kinds))
            .order_by(BackgroundJob.created_at).limit(1).with_for_update(skip_locked=True)
        )).scalar_one_or_none()
        if row is None:
            return None
        row.status, row.locked_by, row.locked_at, row.attempts = "running", worker_id, _now(), row.attempts + 1
        await s.commit()
        return ClaimedJob(row.id, row.kind, row.user_id, dict(row.payload), row.attempts, row.max_attempts)


async def complete(factory: async_sessionmaker[AsyncSession], job_id: uuid.UUID, result: Mapping[str, Any]) -> None:
    async with factory() as s:
        await s.execute(update(BackgroundJob).where(BackgroundJob.id == job_id)
                        .values(status="succeeded", result=dict(result), error=None, locked_by=None))
        await s.commit()


async def fail(factory: async_sessionmaker[AsyncSession], job: ClaimedJob, error: str) -> None:
    """Retry with exponential backoff until ``max_attempts`` is reached."""
    retry = job.attempts < job.max_attempts
    async with factory() as s:
        await s.execute(update(BackgroundJob).where(BackgroundJob.id == job.id).values(
            status="queued" if retry else "failed", error=error[:1000], locked_by=None,
            run_after=_now() + timedelta(seconds=30 * 2 ** job.attempts) if retry else _now(),
        ))
        await s.commit()


async def requeue_stale(factory: async_sessionmaker[AsyncSession]) -> int:
    async with factory() as s:
        result = await s.execute(update(BackgroundJob).where(
            BackgroundJob.status == "running", BackgroundJob.locked_at < _now() - STALE_AFTER
        ).values(status="queued", locked_by=None))
        await s.commit()
        return result.rowcount or 0


async def run_worker(
    ctx: WorkerContext, handlers: Mapping[str, JobHandler], *, poll_interval: float = 2.0,
    stop: asyncio.Event | None = None, worker_id: str | None = None,
) -> None:
    worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
    stop = stop or asyncio.Event()
    kinds = list(handlers)
    ticks = 0
    logger.info("worker_started", extra={"worker_id": worker_id, "kinds": kinds})
    while not stop.is_set():
        ticks += 1
        if ticks % 30 == 1:
            await requeue_stale(ctx.session_factory)
        job = await claim_next(ctx.session_factory, worker_id, kinds)
        if job is None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                pass
            continue
        try:
            result = await handlers[job.kind](ctx, job)
            await complete(ctx.session_factory, job.id, result)
            logger.info("job_succeeded", extra={"job_id": str(job.id), "kind": job.kind})
        except Exception as exc:
            message = exc.message if isinstance(exc, AppError) else f"{type(exc).__name__}"
            logger.exception("job_failed", extra={"job_id": str(job.id), "kind": job.kind})
            await fail(ctx.session_factory, job, message)


async def main() -> None:
    from app.database.connection import create_engine, create_session_factory
    from app.integrations.github.client import HttpxTransport
    from app.lifespan import build_cipher
    from app.workers import evaluation_jobs, repository_jobs

    settings = Settings.from_env()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    transport = HttpxTransport()
    llm = GroqClient(settings.groq_api_key, settings.groq_model, transport) if settings.groq_api_key and settings.groq_model else None
    ctx = WorkerContext(create_session_factory(engine), settings, transport, llm,
                        build_cipher(settings.github_token_encryption_key, production=settings.is_production))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await run_worker(ctx, {**repository_jobs.HANDLERS, **evaluation_jobs.HANDLERS}, stop=stop)
    finally:
        await transport.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
