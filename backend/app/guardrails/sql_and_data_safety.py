"""Safe handling of dynamic query inputs. All queries use bound parameters; these cover the rest."""

from __future__ import annotations

import uuid
from typing import Iterable

from app.core.exceptions import InvalidInputError


def parse_uuid(value: str | uuid.UUID) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except ValueError:
        raise InvalidInputError("Invalid identifier.") from None


def safe_sort_column(requested: str | None, allowed: Iterable[str], default: str) -> str:
    """Only ever return a column from the allowlist (never interpolate user text)."""
    allowed_set = set(allowed)
    if default not in allowed_set:
        raise ValueError("default must be allowed")
    return requested if requested in allowed_set else default


def clamp_page(limit: int | None, offset: int | None, *, max_limit: int = 100) -> tuple[int, int]:
    limit = 20 if limit is None else max(1, min(int(limit), max_limit))
    offset = 0 if offset is None else max(0, min(int(offset), 100_000))
    return limit, offset


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
