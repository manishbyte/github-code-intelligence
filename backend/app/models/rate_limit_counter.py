from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class RateLimitCounter(Base):
    """Fixed-window counters kept in PostgreSQL (no Redis)."""

    __tablename__ = "rate_limit_counters"
    __table_args__ = (UniqueConstraint("key", "window_start", name="uq_rate_limit_key_window"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(200), index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    count: Mapped[int] = mapped_column(Integer, default=0)
