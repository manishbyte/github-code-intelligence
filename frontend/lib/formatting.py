"""Display helpers."""

from __future__ import annotations

from datetime import datetime

SEVERITY_BADGE = {"critical": "🟣 critical", "high": "🔴 high", "medium": "🟠 medium", "low": "🟡 low"}
STATE_BADGE = {
    "PENDING_REVIEW": "🕒 Pending review", "APPROVED": "✅ Approved", "REJECTED": "⛔ Rejected", "EXPIRED": "⌛ Expired",
    "PUBLISHING": "⏳ Publishing", "PUBLISHED": "🚀 Published", "FAILED": "❌ Failed",
}


def short_sha(sha: str | None) -> str:
    return (sha or "")[:8]


def fmt_dt(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "—"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return str(n)
