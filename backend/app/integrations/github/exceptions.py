"""GitHub integration errors. Never include tokens or raw response bodies."""

from __future__ import annotations

from app.core.exceptions import AppError, GuardrailViolation


class GitHubError(AppError):
    code = "github_error"

    def __init__(self, message: str, *, status: int | None = None, request_id: str | None = None) -> None:
        super().__init__(message, details={"status": status, "request_id": request_id})
        self.status = status
        self.request_id = request_id


class GitHubAuthError(GitHubError):
    code = "github_auth_error"


class GitHubPermissionError(GitHubError):
    code = "github_permission_error"


class GitHubNotFoundError(GitHubError):
    code = "github_not_found"


class GitHubConflictError(GitHubError):
    code = "github_conflict"


class GitHubValidationError(GitHubError):
    code = "github_validation_error"


class GitHubServerError(GitHubError):
    code = "github_server_error"


class GitHubRateLimitError(GitHubError):
    code = "github_rate_limited"

    def __init__(self, message: str, *, retry_after: float | None, status: int | None, request_id: str | None) -> None:
        super().__init__(message, status=status, request_id=request_id)
        self.retry_after = retry_after


class GitHubTransportError(GitHubError):
    """Network failure. For writes the outcome is unknown (``outcome_unknown``)."""

    code = "github_transport_error"

    def __init__(self, message: str, *, outcome_unknown: bool = False) -> None:
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


class TransportFailure(Exception):
    """Raised by transports for timeouts and connection errors."""


class ForbiddenOperationError(GuardrailViolation):
    code = "forbidden_github_operation"
