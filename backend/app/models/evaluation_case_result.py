import uuid

from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, fk, pk


class EvaluationCaseResult(Base):
    __tablename__ = "evaluation_case_results"

    id: Mapped[uuid.UUID] = pk()
    run_id: Mapped[uuid.UUID] = fk("evaluation_runs.id")
    case_id: Mapped[uuid.UUID] = fk("evaluation_cases.id")
    kind: Mapped[str] = mapped_column(String(30))
    passed: Mapped[bool] = mapped_column(Boolean)
    score: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
