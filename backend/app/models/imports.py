from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

IMPORT_STATUSES = (
    "uploaded", "extracting", "review", "committed", "reverted", "failed", "cancelled",
)  # fmt: skip
ROW_STATUSES = ("new", "updated", "unchanged", "possible_match", "problem")
ROW_DECISIONS = ("create", "update", "skip", "merge_into")


class Import(TimestampMixin, Base):
    __tablename__ = "imports"

    filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(10))
    sheets_selected: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    llm_model: Mapped[str | None] = mapped_column(String(80))
    llm_tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    llm_tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    # pre-extraction summary per sheet (rows, header, preview, preselected)
    sheets: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # sheet name -> category code hint chosen in the wizard
    hints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # {total_chunks, done_chunks, failed_chunks, sheets: {name: {total, done}}}
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ImportRow(TimestampMixin, Base):
    __tablename__ = "import_rows"

    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id", ondelete="CASCADE"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    sheet: Mapped[str | None] = mapped_column(String(120))
    source_ref: Mapped[str | None] = mapped_column(String(300))
    raw: Mapped[Any] = mapped_column(JSON, default=dict)
    parsed: Mapped[Any] = mapped_column(JSON, default=dict)
    match_type: Mapped[str | None] = mapped_column(String(20))
    matched_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    candidates: Mapped[list[Any]] = mapped_column(JSON, default=list)
    decision: Mapped[str | None] = mapped_column(String(20))
    user_edits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float)
    issues: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    # what commit changed, so revert can undo it exactly
    commit_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
