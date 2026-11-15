"""Parse GitHub rate-limit headers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class RateLimitInfo:
    limit: int | None
    remaining: int | None
    reset_epoch: int | None
    resource: str | None


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def parse_rate_limit(headers: Mapping[str, str]) -> RateLimitInfo | None:
    if "x-ratelimit-remaining" not in headers and "x-ratelimit-limit" not in headers:
        return None
    return RateLimitInfo(
        limit=_int(headers.get("x-ratelimit-limit")),
        remaining=_int(headers.get("x-ratelimit-remaining")),
        reset_epoch=_int(headers.get("x-ratelimit-reset")),
        resource=headers.get("x-ratelimit-resource"),
    )


def parse_retry_after(headers: Mapping[str, str]) -> float | None:
    value = _int(headers.get("retry-after"))
    return float(value) if value is not None and value >= 0 else None


def seconds_until_reset(info: RateLimitInfo | None, now_epoch: float) -> float | None:
    if info is None or info.reset_epoch is None:
        return None
    return max(0.0, info.reset_epoch - now_epoch)
