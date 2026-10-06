"""Customers, quotes and proforma invoices (plan §3.8, §3.9, §3.9a, §5.4), and images.

Quote and proforma lines are snapshots: name, description, cost and price are copied
when a line is added, so later catalog changes never alter a document.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Money, TimestampMixin
from app.models.catalog import Product

QUOTE_STATUSES = ("draft", "sent", "accepted", "lost", "expired")
SECTION_LAYOUTS = ("offer", "list")
LINE_KINDS = ("product", "manual", "config")
PI_STATUSES = ("draft", "issued", "cancelled")


class Image(TimestampMixin, Base):
    """An uploaded picture (product photo, logo, signature) under data/images/."""

    __tablename__ = "images"

    path: Mapped[str] = mapped_column(String(300))  # relative to data/images
    original_name: Mapped[str | None] = mapped_column(String(300))
    media_type: Mapped[str] = mapped_column(String(40))
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)


class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(60))
    address: Mapped[str | None] = mapped_column(Text)
    trade_term: Mapped[str | None] = mapped_column(String(120))
    payment_terms: Mapped[str | None] = mapped_column(Text)
    default_margin_pct: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="en")


class Quote(TimestampMixin, Base):
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("offer_no", "revision"),)

    offer_no: Mapped[str] = mapped_column(String(60), index=True)  # WKZ20260811-01
    revision: Mapped[int] = mapped_column(Integer, default=1)
    parent_quote_id: Mapped[int | None] = mapped_column(
        ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    offer_date: Mapped[date] = mapped_column(Date)
    validity_days: Mapped[int | None] = mapped_column(Integer)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # name, code, address... as they were when the quote was last edited
    customer_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    contact: Mapped[str | None] = mapped_column(String(120))
    contact_email: Mapped[str | None] = mapped_column(String(200))
    trade_term: Mapped[str | None] = mapped_column(String(120))
    payment_terms: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    language: Mapped[str] = mapped_column(String(8), default="en")
    notes_header: Mapped[str | None] = mapped_column(Text)
    notes_footer: Mapped[str | None] = mapped_column(Text)
    discount_pct: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    grand_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))

    customer: Mapped[Customer | None] = relationship()
    sections: Mapped[list[QuoteSection]] = relationship(
        back_populates="quote",
        order_by="QuoteSection.sort_order",
        cascade="all, delete-orphan",
    )

    @property
    def display_no(self) -> str:
        return self.offer_no if self.revision <= 1 else f"{self.offer_no} R{self.revision}"


class QuoteSection(TimestampMixin, Base):
    """One option table on the document."""

    __tablename__ = "quote_sections"

    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(String(200))  # printed above a list table
    layout: Mapped[str] = mapped_column(String(10), default="offer")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    subtotal: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))

    quote: Mapped[Quote] = relationship(back_populates="sections")
    lines: Mapped[list[QuoteLine]] = relationship(
        back_populates="section",
        order_by="QuoteLine.sort_order",
        cascade="all, delete-orphan",
    )


class Configuration(TimestampMixin, Base):
    """A saved build (laptop, PC, tablet …) that quotes insert as one combined product
    (plan §3.10). Its parts price live from the catalog; the customer sees one row."""

    __tablename__ = "configurations"

    name: Mapped[str] = mapped_column(String(300))
    name_zh: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)  # internal, never printed
    platform: Mapped[str | None] = mapped_column(String(120))
    device_type: Mapped[str | None] = mapped_column(String(20))  # filters the part picker
    model_no: Mapped[str | None] = mapped_column(String(120))
    material: Mapped[str | None] = mapped_column(String(120))
    base_margin_pct: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    image_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    saved_cost: Mapped[Decimal | None] = mapped_column(Money, nullable=True)  # at last save

    items: Mapped[list[ConfigurationItem]] = relationship(
        back_populates="configuration",
        cascade="all, delete-orphan",
        order_by="ConfigurationItem.sort_order",
        lazy="selectin",
    )


class ConfigurationItem(TimestampMixin, Base):
    """One part, also one printed description line. A catalog part takes the product's
    current price; a part typed by hand (``product_id`` None) keeps ``cost_usd``."""

    __tablename__ = "configuration_items"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("configurations.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(300))  # the printed text
    cost_usd: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    condition: Mapped[str | None] = mapped_column(String(10))  # new | used
    emphasis: Mapped[bool] = mapped_column(Boolean, default=False)  # printed in red
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    configuration: Mapped[Configuration] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship(lazy="joined")


class QuoteLine(TimestampMixin, Base):
    __tablename__ = "quote_lines"

    section_id: Mapped[int] = mapped_column(
        ForeignKey("quote_sections.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    line_no: Mapped[str | None] = mapped_column(String(20))  # printed NO; None = position
    kind: Mapped[str] = mapped_column(String(10), default="product")
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    # config lines inserted from a saved configuration ("where used")
    configuration_id: Mapped[int | None] = mapped_column(
        ForeignKey("configurations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(300))
    name_emphasis: Mapped[bool] = mapped_column(Boolean, default=False)  # printed in red
    # [{text, emphasis}] - one spec per printed line; emphasized lines print in red
    description_lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    model_no: Mapped[str | None] = mapped_column(String(120))
    material: Mapped[str | None] = mapped_column(String(120))
    image_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    cost_usd: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    margin_pct: Mapped[Decimal | None] = mapped_column(Money, nullable=True)  # line override
    unit_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    unit_price_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    # {price_date, import_id, tier} of the cost when the line was added
    price_source: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # config lines: the parts combined into this one product, each a snapshot
    # {product_id, name, qty (per unit), cost_usd, condition, emphasis, price_date};
    # the line's cost_usd = Σ qty × cost
    components: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, server_default="[]"
    )

    section: Mapped[QuoteSection] = relationship(back_populates="lines")


class ProformaInvoice(TimestampMixin, Base):
    __tablename__ = "proforma_invoices"

    pi_no: Mapped[str] = mapped_column(String(60), unique=True)
    quote_id: Mapped[int | None] = mapped_column(
        ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft")
    po_no: Mapped[str | None] = mapped_column(String(80))
    issue_date: Mapped[date] = mapped_column(Date)
    customer_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attention: Mapped[str | None] = mapped_column(String(120))
    seller_contact: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    foc_pct: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    freight: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    # [{title, text}] numbered on the document
    terms: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    subtotal: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    issued_at: Mapped[date | None] = mapped_column(Date)
    revised_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("proforma_invoices.id", ondelete="SET NULL"), nullable=True
    )

    quote: Mapped[Quote | None] = relationship()
    lines: Mapped[list[ProformaLine]] = relationship(
        back_populates="invoice",
        order_by="ProformaLine.sort_order",
        cascade="all, delete-orphan",
    )


class ProformaLine(TimestampMixin, Base):
    __tablename__ = "proforma_lines"

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("proforma_invoices.id", ondelete="CASCADE"), index=True
    )
    source_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("quote_lines.id", ondelete="SET NULL"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    model_no: Mapped[str | None] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    description_lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    image_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))

    invoice: Mapped[ProformaInvoice] = relationship(back_populates="lines")
