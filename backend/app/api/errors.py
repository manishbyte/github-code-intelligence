"""Uniform error responses. Messages never include secrets, tokens or raw upstream bodies."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    ActionInProgressError, AppError, ApprovalError, AuthenticationError, ConfigurationError, ConflictError,
    GuardrailViolation, LLMError, NotFoundError, OutputValidationError, PermissionDeniedError,
    RateLimitedError, StaleSourceError, UnverifiedResultError,
)
from app.integrations.github.exceptions import (
    ForbiddenOperationError, GitHubAuthError, GitHubConflictError, GitHubError, GitHubNotFoundError,
    GitHubPermissionError, GitHubRateLimitError, GitHubValidationError,
)
from app.observability.tracing import request_id_var

logger = logging.getLogger("app.errors")

_STATUS: tuple[tuple[type[Exception], int], ...] = (
    (AuthenticationError, 401),
    (ApprovalError, 403),
    (PermissionDeniedError, 403),
    (NotFoundError, 404),
    (RateLimitedError, 429),
    (ActionInProgressError, 409),
    (StaleSourceError, 409),
    (ConflictError, 409),
    (ForbiddenOperationError, 500),
    (OutputValidationError, 502),
    (UnverifiedResultError, 502),
    (LLMError, 502),
    (GuardrailViolation, 422),
    (ConfigurationError, 500),
    (GitHubAuthError, 409),
    (GitHubRateLimitError, 429),
    (GitHubNotFoundError, 404),
    (GitHubPermissionError, 403),
    (GitHubConflictError, 409),
    (GitHubValidationError, 422),
    (GitHubError, 502),
)


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id_var.get()}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        status = next((s for cls, s in _STATUS if isinstance(exc, cls)), 500)
        headers = {}
        retry = getattr(exc, "retry_after", None)
        if status == 429 and retry is not None:
            headers["Retry-After"] = str(int(retry))
        message = exc.message if status != 500 else "The request could not be completed."
        if status >= 500:
            logger.error("server_error", extra={"error_code": exc.code, "error_message": exc.message[:300], "path": request.url.path})
        if isinstance(exc, GitHubAuthError):
            message = "GitHub rejected the stored token. Please reconnect your GitHub account."
        return JSONResponse(_body(exc.code, message), status_code=status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]) for e in exc.errors()})
        return JSONResponse(_body("validation_error", "Invalid request: " + ", ".join(fields)[:300]), status_code=422)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", extra={"path": request.url.path})
        return JSONResponse(_body("internal_error", "An unexpected error occurred."), status_code=500)
