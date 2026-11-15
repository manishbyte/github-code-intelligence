"""Minimal in-process Prometheus-style metrics (no extra dependency)."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Mapping

_lock = threading.Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_hist: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(lambda: [0.0, 0.0])
_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
_bucket_counts: dict[tuple[str, tuple[tuple[str, str], ...], float], int] = defaultdict(int)


def _key(labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((labels or {}).items()))


def inc(name: str, value: float = 1.0, labels: Mapping[str, str] | None = None) -> None:
    with _lock:
        _counters[(name, _key(labels))] += value


def observe(name: str, seconds: float, labels: Mapping[str, str] | None = None) -> None:
    k = _key(labels)
    with _lock:
        h = _hist[(name, k)]
        h[0] += 1
        h[1] += seconds
        for b in _BUCKETS:
            if seconds <= b:
                _bucket_counts[(name, k, b)] += 1


def _fmt(labels: tuple[tuple[str, str], ...], extra: str = "") -> str:
    parts = [f'{k}="{v}"' for k, v in labels] + ([extra] if extra else [])
    return "{" + ",".join(parts) + "}" if parts else ""


def render_prometheus() -> str:
    lines: list[str] = []
    with _lock:
        for (name, labels), value in sorted(_counters.items()):
            lines.append(f"{name}_total{_fmt(labels)} {value}")
        for (name, labels), (count, total) in sorted(_hist.items()):
            for b in _BUCKETS:
                lines.append(f'{name}_seconds_bucket{_fmt(labels, f"le=\"{b}\"")} {_bucket_counts[(name, labels, b)]}')
            lines.append(f'{name}_seconds_bucket{_fmt(labels, "le=\"+Inf\"")} {int(count)}')
            lines.append(f"{name}_seconds_sum{_fmt(labels)} {total}")
            lines.append(f"{name}_seconds_count{_fmt(labels)} {int(count)}")
    return "\n".join(lines) + "\n"
