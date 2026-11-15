"""Audit trail writes (details are redacted before storage)."""

from __future__ import annotations

import uuid
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.guardrails.secret_detection import redact_secrets
from app.models.audit_event import AuditEvent

_SENSITIVE = ("password", "token", "secret", "authorization", "cookie", "key", "code")


def _clean(value: Any, depth: int = 0) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)[:500]
    if isinstance(value, Mapping) and depth < 3:
        return {str(k): "[REDACTED]" if any(s in str(k).lower() for s in _SENSITIVE) else _clean(v, depth + 1)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)) and depth < 3:
        return [_clean(v, depth + 1) for v in list(value)[:50]]
    return value if isinstance(value, (int, float, bool, type(None))) else str(value)[:200]


async def record_audit(
    db: AsyncSession, *, event_type: str, user_id: uuid.UUID | None = None,
    entity_type: str | None = None, entity_id: str | None = None, details: Mapping[str, Any] | None = None,
) -> None:
    db.add(AuditEvent(user_id=user_id, event_type=event_type, entity_type=entity_type,
                      entity_id=entity_id, details=_clean(details or {})))
    await db.flush()
