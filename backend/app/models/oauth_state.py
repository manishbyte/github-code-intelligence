from datetime import datetime
import uuid

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_col, fk, pk


class OAuthState(Base):
    """Single-use OAuth ``state`` values (only a hash is stored)."""

    __tablename__ = "oauth_states"

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = fk("users.id")
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    access: Mapped[str] = mapped_column(String(10))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_col()
