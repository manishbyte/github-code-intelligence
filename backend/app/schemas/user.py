"""User schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import StrictModel


class UserOut(StrictModel):
    id: str
    email: str
    display_name: str
    role: str
    created_at: datetime

    @classmethod
    def from_row(cls, user) -> "UserOut":  # type: ignore[no-untyped-def]
        return cls(id=str(user.id), email=user.email, display_name=user.display_name,
                   role=user.role, created_at=user.created_at)


class UserUpdate(StrictModel):
    display_name: str = Field(min_length=1, max_length=100)
