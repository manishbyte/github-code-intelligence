"""FastAPI application factory."""

from __future__ import annotations

import time
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.errors import install_error_handlers
from app.api.router import api_router
from app.config import Settings
from app.core.session import ACCESS_COOKIE, REFRESH_COOKIE
from app.lifespan import lifespan
from app.observability import metrics
from app.observability.tracing import new_request_id, request_id_var

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _origin(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title=settings.app_name, lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs", redoc_url=None, openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings
    allowed = {_origin(settings.frontend_base_url), _origin(settings.app_base_url)} - {None}

    @app.middleware("http")
    async def csrf_origin_check(request: Request, call_next):  # cookie-authenticated unsafe requests must come from our origins
        if (request.method in _UNSAFE and "authorization" not in request.headers
                and (ACCESS_COOKIE in request.cookies or REFRESH_COOKIE in request.cookies)):
            origin = _origin(request.headers.get("origin")) or _origin(request.headers.get("referer"))
            if origin not in allowed:
                return JSONResponse({"error": {"code": "csrf_rejected", "message": "Cross-site request rejected.", "request_id": request_id_var.get()}}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = new_request_id()
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started
        route = request.scope.get("route")
        label = {"method": request.method, "route": getattr(route, "path", "unmatched"), "status": f"{response.status_code // 100}xx"}
        metrics.inc("gci_http_requests", labels=label)
        metrics.observe("gci_http_request", elapsed, {"route": label["route"]})
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(
        CORSMiddleware, allow_origins=[o for o in allowed if o == _origin(settings.frontend_base_url)],
        allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "Authorization"],
    )
    install_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
