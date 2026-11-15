from datetime import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_col, fk, pk


class GitHubRepository(Base):
    __tablename__ = "github_repositories"
    __table_args__ = (UniqueConstraint("user_id", "owner", "name", name="uq_user_repo"),)

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = fk("users.id")
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id")
    connected_github_account_id: Mapped[uuid.UUID | None] = fk("github_accounts.id", nullable=True, ondelete="SET NULL")
    github_repository_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    owner: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    html_url: Mapped[str] = mapped_column(String(300))
    default_branch: Mapped[str] = mapped_column(String(200))
    visibility: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_col()
