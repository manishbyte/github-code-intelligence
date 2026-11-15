from datetime import datetime
import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_col, pk


class EvaluationDataset(Base):
    __tablename__ = "evaluation_datasets"
    __table_args__ = (UniqueConstraint("kind", "version", name="uq_dataset_kind_version"),)

    id: Mapped[uuid.UUID] = pk()
    kind: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(64))  # content hash
    created_at: Mapped[datetime] = created_col()
