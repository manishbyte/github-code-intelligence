"""Declarative base and column helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Uuid
from sqlalchemy.orm import DeclarativeBase, MappedColumn, mapped_column


class Base(DeclarativeBase):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def pk() -> MappedColumn:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def fk(target: str, *, nullable: bool = False, index: bool = True, ondelete: str = "CASCADE") -> MappedColumn:
    return mapped_column(Uuid(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index)


def created_col() -> MappedColumn:
    return mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


def updated_col() -> MappedColumn:
    return mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
