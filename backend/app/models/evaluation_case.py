import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, fk, pk


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (UniqueConstraint("dataset_id", "case_key", name="uq_case_key"),)

    id: Mapped[uuid.UUID] = pk()
    dataset_id: Mapped[uuid.UUID] = fk("evaluation_datasets.id")
    case_key: Mapped[str] = mapped_column(String(100))
    input: Mapped[dict] = mapped_column(JSONB)
    expected: Mapped[dict] = mapped_column(JSONB)
