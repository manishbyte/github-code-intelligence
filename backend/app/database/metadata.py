"""Imports every model so ``Base.metadata`` is complete (used by Alembic)."""

from app.database.base import Base
import app.models  # noqa: F401  (registers all tables)

metadata = Base.metadata
