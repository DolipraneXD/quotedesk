from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MONEY_QUANT = Decimal("0.0001")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Money(TypeDecorator[Decimal]):
    """NUMERIC(12,4) semantics stored as TEXT so no float ever touches a price.

    SQLite has no real decimal type; its NUMERIC affinity silently converts to REAL.
    """

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError("Money values must be Decimal, int or str, never float")
        return str(Decimal(value).quantize(MONEY_QUANT))

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        return None if value is None else Decimal(value)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
