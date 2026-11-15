"""Authentication request/response schemas."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import StrictModel
from app.schemas.user import UserOut


class RegisterRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class AuthResponse(StrictModel):
    user: UserOut
