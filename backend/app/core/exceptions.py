"""Application exception hierarchy. Messages must never contain secrets."""

from __future__ import annotations

from typing import Any, Mapping


class AppError(Exception):
    """Base class. ``code`` is a stable machine-readable identifier."""

    code = "app_error"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details or {})

    def __str__(self) -> str:
        return self.message


class GuardrailViolation(AppError):
    code = "guardrail_violation"


class InvalidInputError(GuardrailViolation):
    code = "invalid_input"


class PatchSafetyError(GuardrailViolation):
    code = "unsafe_patch"


class PatchApplyError(PatchSafetyError):
    code = "patch_does_not_apply"


class PermissionDeniedError(AppError):
    code = "permission_denied"


class ApprovalError(PermissionDeniedError):
    code = "approval_invalid"


class StaleSourceError(AppError):
    code = "stale_source"


class ActionInProgressError(AppError):
    code = "action_in_progress"


class UnverifiedResultError(AppError):
    """GitHub accepted a write but the result could not be verified."""

    code = "unverified_result"


class AuthenticationError(AppError):
    code = "authentication_failed"


class ConfigurationError(AppError):
    """Invalid or missing configuration. Messages name settings, never values."""

    code = "configuration_error"


class NotFoundError(AppError):
    code = "not_found"


class ConflictError(AppError):
    code = "conflict"


class RateLimitedError(AppError):
    code = "rate_limited"

    def __init__(self, message: str, *, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class GitHubNotConnectedError(ConflictError):
    code = "github_not_connected"


class OutputValidationError(GuardrailViolation):
    code = "invalid_model_output"


class LLMError(AppError):
    code = "llm_error"
