from datetime import datetime
import uuid

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_col, fk, pk


class FileSnapshot(Base):
    __tablename__ = "file_snapshots"
    __table_args__ = (UniqueConstraint("snapshot_id", "path", name="uq_snapshot_path"),)

    id: Mapped[uuid.UUID] = pk()
    snapshot_id: Mapped[uuid.UUID] = fk("repository_snapshots.id")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    path: Mapped[str] = mapped_column(String(1024))
    blob_sha: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(30), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_col()
