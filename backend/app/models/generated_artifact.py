from datetime import datetime
import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_col, fk, pk


class GeneratedArtifact(Base):
    """kind: issue_proposal | comment_patch | logging_patch."""

    __tablename__ = "generated_artifacts"

    id: Mapped[uuid.UUID] = pk()
    analysis_run_id: Mapped[uuid.UUID | None] = fk("analysis_runs.id", nullable=True)
    user_id: Mapped[uuid.UUID] = fk("users.id")
    kind: Mapped[str] = mapped_column(String(30), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    payload_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_col()
