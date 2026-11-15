from datetime import datetime
import uuid

from sqlalchemy import BigInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_col, fk, pk


class GitHubAccount(Base):
    __tablename__ = "github_accounts"

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = fk("users.id", index=False)
    github_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    github_username: Mapped[str] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    encrypted_access_token: Mapped[str] = mapped_column(Text)
    granted_scopes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    connected_at: Mapped[datetime] = created_col()

    __table_args__ = (UniqueConstraint("user_id", name="uq_github_accounts_user"),)
