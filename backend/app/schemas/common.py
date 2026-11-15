"""Shared Pydantic base models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Immutable model that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SecretFindingModel(StrictModel):
    rule: str
    line: int
    preview: str  # redacted; never the full secret
