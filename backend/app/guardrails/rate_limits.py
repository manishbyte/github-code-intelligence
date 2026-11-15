"""Rate-limit policies (limits per window). Enforcement uses PostgreSQL counters."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import hit_rate_limit


@dataclass(frozen=True)
class Policy:
    name: str
    limit: int
    window_seconds: int


POLICIES: dict[str, Policy] = {
    "register": Policy("register", 10, 3600),
    "login": Policy("login", 10, 900),
    "inspect": Policy("inspect", 60, 3600),
    "review": Policy("review", 30, 3600),
    "proposal": Policy("proposal", 30, 3600),
    "publish": Policy("publish", 30, 3600),
    "evaluation": Policy("evaluation", 10, 3600),
}


async def enforce(session: AsyncSession, policy: str, subject: str) -> None:
    p = POLICIES[policy]
    await hit_rate_limit(session, f"{p.name}:{subject}", p.limit, p.window_seconds)
