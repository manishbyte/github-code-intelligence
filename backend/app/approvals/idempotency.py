"""PostgreSQL implementation of the action ledger (duplicate-write protection)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.guardrails.action_policy import LedgerClaim
from app.models.github_action import GitHubAction

UNKNOWN_RECLAIM_AFTER = timedelta(minutes=10)
NEVER_RECLAIM_STEPS = frozenset({"create_issue"})  # a lost issue-creation result could duplicate the issue


class PostgresActionLedger:
    """Each call uses its own short transaction so state survives failures of the caller's transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], *, user_id: uuid.UUID, approval_id: uuid.UUID | None) -> None:
        self._factory = session_factory
        self._user_id = user_id
        self._approval_id = approval_id

    @staticmethod
    def _step(key: str) -> str:
        return key.rsplit(":", 1)[-1][:30]

    async def claim(self, key: str) -> LedgerClaim:
        async with self._factory() as s:
            inserted = (await s.execute(
                insert(GitHubAction)
                .values(user_id=self._user_id, approval_id=self._approval_id, step=self._step(key),
                        idempotency_key=key, status="in_progress")
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
                .returning(GitHubAction.id)
            )).scalar_one_or_none()
            if inserted is not None:
                await s.commit()
                return LedgerClaim("claimed")
            row = (await s.execute(select(GitHubAction).where(GitHubAction.idempotency_key == key).with_for_update())).scalar_one()
            if row.user_id != self._user_id:
                return LedgerClaim("in_progress")
            if row.status == "completed" and row.result is not None:
                return LedgerClaim("completed", row.result)
            age = datetime.now(timezone.utc) - row.updated_at
            if row.status == "failed" or (
                row.status == "unknown" and row.step not in NEVER_RECLAIM_STEPS and age > UNKNOWN_RECLAIM_AFTER
            ):
                row.status = "in_progress"
                await s.commit()
                return LedgerClaim("claimed")
            return LedgerClaim("in_progress")

    async def complete(self, key: str, result: Mapping[str, Any]) -> None:
        async with self._factory() as s:
            row = (await s.execute(select(GitHubAction).where(GitHubAction.idempotency_key == key).with_for_update())).scalar_one()
            row.status = "completed"
            row.result = dict(result)
            row.github_url = result.get("github_url")
            row.github_number = result.get("github_number")
            row.github_sha = result.get("github_sha")
            row.request_id = result.get("request_id")
            row.error_category = None
            await s.commit()

    async def fail(self, key: str, *, category: str, outcome_unknown: bool) -> None:
        async with self._factory() as s:
            row = (await s.execute(select(GitHubAction).where(GitHubAction.idempotency_key == key).with_for_update())).scalar_one()
            row.status = "unknown" if outcome_unknown else "failed"
            row.error_category = category[:100]
            await s.commit()
