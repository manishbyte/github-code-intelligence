"""Liveness and readiness checks."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def check_database(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # any failure means not ready
        return False


async def readiness(engine: AsyncEngine) -> dict[str, object]:
    db_ok = await check_database(engine)
    return {"status": "ok" if db_ok else "unavailable", "checks": {"database": db_ok}}
