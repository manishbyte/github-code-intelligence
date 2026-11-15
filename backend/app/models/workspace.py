from datetime import datetime
import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_col, fk, pk


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[uuid.UUID] = fk("users.id")
    created_at: Mapped[datetime] = created_col()
