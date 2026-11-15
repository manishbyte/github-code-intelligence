"""Request correlation IDs and lightweight timing spans."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from app.observability import metrics

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("app.trace")


def new_request_id() -> str:
    rid = uuid.uuid4().hex
    request_id_var.set(rid)
    return rid


@contextmanager
def span(name: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        metrics.observe("gci_span", elapsed, {"name": name})
        logger.info("span", extra={"span": name, "duration_ms": int(elapsed * 1000), "request_id": request_id_var.get()})
