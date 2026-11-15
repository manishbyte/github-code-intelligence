from datetime import datetime
import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_col, fk, pk


class ApprovalDecision(Base):
    """Immutable record of each human decision (audit trail)."""

    __tablename__ = "approval_decisions"

    id: Mapped[uuid.UUID] = pk()
    approval_id: Mapped[uuid.UUID] = fk("approval_requests.id")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    decision: Mapped[str] = mapped_column(String(10))  # approve | reject
    payload_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_col()
