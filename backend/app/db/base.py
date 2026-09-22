from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData()


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    metadata = metadata


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


def json_column(default: Any = dict) -> Mapped[Any]:
    return mapped_column(JSON, default=default, nullable=False)


def id_column() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)
