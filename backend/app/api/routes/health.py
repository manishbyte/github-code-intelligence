from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.dependencies import permission
from app.observability import metrics
from app.observability.health import readiness

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, object]:
    return await readiness(request.app.state.engine)


@router.get("/metrics", response_class=PlainTextResponse, dependencies=[permission("metrics:read")])
async def prometheus_metrics() -> str:
    return metrics.render_prometheus()
