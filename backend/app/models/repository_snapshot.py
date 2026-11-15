from datetime import datetime
import uuid

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_col, fk, pk


class RepositorySnapshot(Base):
    """Complete tree for one commit; doubles as the commit-SHA-keyed tree cache."""

    __tablename__ = "repository_snapshots"
    __table_args__ = (UniqueConstraint("repository_id", "commit_sha", name="uq_repo_commit"),)

    id: Mapped[uuid.UUID] = pk()
    repository_id: Mapped[uuid.UUID] = fk("github_repositories.id")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    branch: Mapped[str] = mapped_column(String(200))
    commit_sha: Mapped[str] = mapped_column(String(64))
    tree_sha: Mapped[str] = mapped_column(String(64))
    entry_count: Mapped[int] = mapped_column(Integer)
    skipped_unsafe_entries: Mapped[int] = mapped_column(Integer, default=0)
    tree: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_col()
