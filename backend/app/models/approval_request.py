from datetime import datetime
import uuid

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_col, fk, pk, updated_col


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = fk("users.id")
    artifact_id: Mapped[uuid.UUID | None] = fk("generated_artifacts.id", nullable=True)
    action_type: Mapped[str] = mapped_column(String(30))  # create_issue | publish_code_change
    owner: Mapped[str] = mapped_column(String(100))
    repo: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(20), default="PENDING_REVIEW", index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    payload_digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()
