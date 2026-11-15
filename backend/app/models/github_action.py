from datetime import datetime
import uuid

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_col, fk, pk, updated_col


class GitHubAction(Base):
    """One row per GitHub write step; ``idempotency_key`` makes it the durable action ledger."""

    __tablename__ = "github_actions"

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = fk("users.id")
    approval_id: Mapped[uuid.UUID | None] = fk("approval_requests.id", nullable=True)
    step: Mapped[str] = mapped_column(String(30))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")  # in_progress|completed|failed|unknown
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    github_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = created_col()
    updated_at: Mapped[datetime] = updated_col()
