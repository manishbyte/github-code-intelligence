"""PostgreSQL-backed fixed-window rate limiting (atomic upsert)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RateLimitedError
from app.models.rate_limit_counter import RateLimitCounter


async def hit_rate_limit(
    session: AsyncSession, key: str, limit: int, window_seconds: int, *, now: datetime | None = None
) -> int:
    """Count one hit; raise ``RateLimitedError`` when the window limit is exceeded."""
    now = now or datetime.now(timezone.utc)
    epoch = int(now.timestamp())
    start_epoch = epoch - epoch % window_seconds
    window_start = datetime.fromtimestamp(start_epoch, tz=timezone.utc)
    stmt = (
        insert(RateLimitCounter)
        .values(key=key[:200], window_start=window_start, count=1)
        .on_conflict_do_update(
            constraint="uq_rate_limit_key_window", set_={"count": RateLimitCounter.count + 1}
        )
        .returning(RateLimitCounter.count)
    )
    count = (await session.execute(stmt)).scalar_one()
    await session.commit()
    if count > limit:
        raise RateLimitedError("Too many requests; please retry later.", retry_after=max(1, start_epoch + window_seconds - epoch))
    return count
