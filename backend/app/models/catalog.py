from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Money, TimestampMixin

if TYPE_CHECKING:
    from app.models.imports import Import
    from app.models.quotes import ProductImage

PRODUCT_STATUSES = ("active", "discontinued", "stock_only", "no_supply", "inactive")
PRICE_TIERS = ("standard", "forecast")


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name_en: Mapped[str] = mapped_column(String(120))
    name_zh: Mapped[str] = mapped_column(String(120))
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)
    # ordered list of {key, label_en, label_zh, type, unit, options, in_fingerprint}
    attribute_schema: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    default_margin_pct: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Brand(TimestampMixin, Base):
    __tablename__ = "brands"

    canonical: Mapped[str] = mapped_column(String(120), unique=True)
    name_en: Mapped[str | None] = mapped_column(String(120))
    name_zh: Mapped[str | None] = mapped_column(String(120))
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    aliases: Mapped[list[BrandAlias]] = relationship(
        back_populates="brand", cascade="all, delete-orphan", order_by="BrandAlias.id"
    )


class BrandAlias(TimestampMixin, Base):
    __tablename__ = "brand_aliases"

    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(120))
    # normalized form used for lookups; unique so one alias resolves to one brand
    alias_key: Mapped[str] = mapped_column(String(120), unique=True)
    lang: Mapped[str] = mapped_column(String(8), default="en")

    brand: Mapped[Brand] = relationship(back_populates="aliases")


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (Index("ix_products_category", "category_id"),)

    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    erp_code: Mapped[str | None] = mapped_column(String(60), unique=True, nullable=True)
    erp_code_alt: Mapped[list[str]] = mapped_column(JSON, default=list)
    mpn: Mapped[str | None] = mapped_column(String(120), index=True)
    name_zh: Mapped[str] = mapped_column(String(300))
    name_en: Mapped[str | None] = mapped_column(String(300))
    name_en_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(40), unique=True)

    current_price_usd: Mapped[Decimal | None] = mapped_column(Money)
    current_price_tier_forecast_usd: Mapped[Decimal | None] = mapped_column(Money)
    price_date: Mapped[date | None] = mapped_column(Date)
    last_import_id: Mapped[int | None] = mapped_column(
        ForeignKey("imports.id", ondelete="SET NULL"), nullable=True
    )
    # the import whose commit created the product (None: entered by hand)
    created_import_id: Mapped[int | None] = mapped_column(
        ForeignKey("imports.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(20), default="active")
    confirm_before_order: Mapped[bool] = mapped_column(Boolean, default=False)
    lead_time_confirm: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_validation: Mapped[bool] = mapped_column(Boolean, default=False)
    quote_on_request: Mapped[bool] = mapped_column(Boolean, default=False)
    recommended: Mapped[bool] = mapped_column(Boolean, default=False)

    stock_qty: Mapped[int | None] = mapped_column(Integer)
    demand_qty: Mapped[int | None] = mapped_column(Integer)
    stock_after_qty: Mapped[int | None] = mapped_column(Integer)
    max_order_qty: Mapped[int | None] = mapped_column(Integer)
    from_stock_qty: Mapped[int | None] = mapped_column(Integer)
    payment_terms: Mapped[str | None] = mapped_column(Text)
    supply_note: Mapped[str | None] = mapped_column(Text)
    market: Mapped[str | None] = mapped_column(String(40))
    notes_raw: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(String(120))
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    description_zh: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    model_no: Mapped[str | None] = mapped_column(String(120))  # "ST Products No." on quotes
    material: Mapped[str | None] = mapped_column(String(120))

    category: Mapped[Category] = relationship()
    brand: Mapped[Brand | None] = relationship()
    created_import: Mapped[Import | None] = relationship(foreign_keys=[created_import_id])
    last_import: Mapped[Import | None] = relationship(foreign_keys=[last_import_id])
    images: Mapped[list[ProductImage]] = relationship(
        order_by="ProductImage.sort_order, ProductImage.id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def image_ids(self) -> list[int]:
        return [link.image_id for link in self.images]


class ProductAlias(TimestampMixin, Base):
    """A fingerprint that used to belong to a product merged into ``product_id``."""

    __tablename__ = "product_aliases"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    fingerprint: Mapped[str] = mapped_column(String(40), unique=True)
    name_zh: Mapped[str | None] = mapped_column(String(300))


class PriceHistory(TimestampMixin, Base):
    __tablename__ = "price_history"
    __table_args__ = (Index("ix_price_history_product", "product_id", "tier", "is_current"),)

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    import_id: Mapped[int | None] = mapped_column(
        ForeignKey("imports.id", ondelete="SET NULL"), nullable=True
    )
    price_usd: Mapped[Decimal] = mapped_column(Money)
    tier: Mapped[str] = mapped_column(String(20), default="standard")
    amount_original: Mapped[Decimal | None] = mapped_column(Money)
    currency_original: Mapped[str | None] = mapped_column(String(8))
    fx_rate: Mapped[Decimal | None] = mapped_column(Money)
    price_date: Mapped[date | None] = mapped_column(Date)
    source_ref: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)


class NoteRule(TimestampMixin, Base):
    """Maps a remark pattern (``备注``) to a product flag. See plan §1.4.

    kind: ``set`` writes ``value`` to ``field``; ``qty`` parses capture group 1 as a
    quantity (group 2 ``K`` multiplies by 1000); ``text`` stores the whole note.
    """

    __tablename__ = "note_rules"

    pattern: Mapped[str] = mapped_column(String(300))
    field: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(10), default="set")
    value: Mapped[str | None] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
