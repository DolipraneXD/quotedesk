from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.catalog import DeviceType


class CustomerFields(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    trade_term: str | None = None
    payment_terms: str | None = None
    default_margin_pct: Decimal | None = Field(default=None, ge=-100, le=1000)
    notes: str | None = None
    language: Literal["en", "zh"] | None = None


class CustomerCreate(CustomerFields):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)


class CustomerUpdate(CustomerFields):
    code: str | None = Field(default=None, min_length=1, max_length=40)


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    contact_name: str | None
    email: str | None
    phone: str | None
    address: str | None
    trade_term: str | None
    payment_terms: str | None
    default_margin_pct: Decimal | None
    notes: str | None
    language: str
    created_at: datetime


class DescriptionLine(BaseModel):
    text: str
    emphasis: bool = False


class Component(BaseModel):
    """A part of a combined product. Send only ``product_id`` (and qty) to copy a catalog
    product; parts sent back with their name keep the values given."""

    product_id: int | None = None
    name: str | None = Field(default=None, max_length=300)
    qty: int = Field(default=1, ge=1)
    cost_usd: Decimal | None = Field(default=None, ge=0)
    condition: Literal["new", "used"] | None = None
    emphasis: bool = False  # printed in red
    price_date: date | None = None


class LineOut(BaseModel):
    id: int
    section_id: int
    sort_order: int
    line_no: str | None
    printed_no: str
    kind: str
    product_id: int | None
    category_id: int | None
    configuration_id: int | None
    name: str
    name_emphasis: bool
    description_lines: list[DescriptionLine]
    model_no: str | None
    material: str | None
    image_ids: list[int]
    qty: int
    cost_usd: Decimal | None
    margin_pct: Decimal | None  # the line's own override
    effective_margin_pct: Decimal | None  # what the price carries now
    unit_price: Decimal
    unit_price_manual: bool
    total: Decimal
    price_source: dict[str, Any]
    components: list[Component]
    warnings: list[dict[str, Any]]


class SectionOut(BaseModel):
    id: int
    title: str | None
    layout: str
    sort_order: int
    subtotal: Decimal
    lines: list[LineOut]


class QuoteOut(BaseModel):
    id: int
    offer_no: str
    revision: int
    display_no: str
    parent_quote_id: int | None
    status: str
    offer_date: date
    validity_days: int | None
    valid_until: date | None
    customer_id: int | None
    customer_snapshot: dict[str, Any]
    contact: str | None
    contact_email: str | None
    trade_term: str | None
    payment_terms: str | None
    currency: str
    language: str
    notes_header: str | None
    notes_footer: str | None
    discount_pct: Decimal | None
    discount_amount: Decimal | None
    subtotal: Decimal
    grand_total: Decimal
    sections: list[SectionOut]
    revisions: list[dict[str, Any]]
    proformas: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class QuoteSummary(BaseModel):
    id: int
    display_no: str
    status: str
    offer_date: date
    customer_name: str | None
    customer_code: str | None
    grand_total: Decimal
    lines: int
    warnings: int
    updated_at: datetime


class QuoteList(BaseModel):
    items: list[QuoteSummary]
    total: int


class QuoteCreate(BaseModel):
    customer_id: int | None = None
    offer_date: date | None = None
    validity_days: int | None = Field(default=None, ge=1, le=365)
    language: Literal["en", "zh"] | None = None
    layout: Literal["offer", "list"] = "offer"


class QuotePatch(BaseModel):
    customer_id: int | None = None
    status: Literal["draft", "sent", "accepted", "lost", "expired"] | None = None
    offer_date: date | None = None
    validity_days: int | None = Field(default=None, ge=1, le=365)
    contact: str | None = None
    contact_email: str | None = None
    trade_term: str | None = None
    payment_terms: str | None = None
    language: Literal["en", "zh"] | None = None
    notes_header: str | None = None
    notes_footer: str | None = None
    discount_pct: Decimal | None = Field(default=None, ge=0, le=100)
    discount_amount: Decimal | None = Field(default=None, ge=0)


class SectionIn(BaseModel):
    title: str | None = None
    layout: Literal["offer", "list"] | None = None
    sort_order: int | None = None


class LineCreate(BaseModel):
    section_id: int
    kind: Literal["product", "manual", "config"] | None = None  # default: from product_id
    product_id: int | None = None
    configuration_id: int | None = None  # insert a saved configuration
    components: list[Component] | None = None  # config lines
    qty: int = Field(default=1, ge=1)
    # manual items (product_id is None)
    name: str | None = Field(default=None, max_length=300)
    description_lines: list[DescriptionLine] | None = None
    model_no: str | None = None
    material: str | None = None
    cost_usd: Decimal | None = Field(default=None, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    category_id: int | None = None
    save_to_catalog: bool = False


class LinePatch(BaseModel):
    section_id: int | None = None
    line_no: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=300)
    name_emphasis: bool | None = None
    description_lines: list[DescriptionLine] | None = None
    model_no: str | None = None
    material: str | None = None
    image_ids: list[int] | None = None
    qty: int | None = Field(default=None, ge=1)
    cost_usd: Decimal | None = Field(default=None, ge=0)
    margin_pct: Decimal | None = Field(default=None, ge=-100, le=1000)
    unit_price: Decimal | None = Field(default=None, ge=0)
    components: list[Component] | None = None  # config lines: the full new list
    describe: bool = False  # config lines: rebuild the description from the parts


class CombineIn(BaseModel):
    line_ids: list[int]
    name: str = Field(min_length=1, max_length=300)


class ReorderIn(BaseModel):
    section_id: int
    line_ids: list[int]


class ProformaCreate(BaseModel):
    line_ids: list[int]
    po_no: str | None = None


class TermIn(BaseModel):
    title: str
    text: str


class ProformaPatch(BaseModel):
    pi_no: str | None = None
    po_no: str | None = None
    issue_date: date | None = None
    attention: str | None = None
    foc_pct: Decimal | None = Field(default=None, ge=0, le=100)
    freight: Decimal | None = Field(default=None, ge=0)
    terms: list[TermIn] | None = None
    seller_contact: dict[str, str] | None = None
    customer_snapshot: dict[str, Any] | None = None


class ProformaLinePatch(BaseModel):
    model_no: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description_lines: list[DescriptionLine] | None = None
    image_ids: list[int] | None = None
    qty: int | None = Field(default=None, ge=1)
    unit_price: Decimal | None = Field(default=None, ge=0)


class ProformaLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_line_id: int | None
    sort_order: int
    model_no: str | None
    name: str
    description_lines: list[DescriptionLine]
    image_ids: list[int]
    qty: int
    unit_price: Decimal
    total: Decimal


class ProformaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pi_no: str
    quote_id: int | None
    status: str
    po_no: str | None
    issue_date: date
    customer_snapshot: dict[str, Any]
    attention: str | None
    seller_contact: dict[str, Any]
    currency: str
    foc_pct: Decimal | None
    freight: Decimal | None
    terms: list[dict[str, Any]]
    subtotal: Decimal
    total: Decimal
    issued_at: date | None
    revised_from_id: int | None
    lines: list[ProformaLineOut]
    created_at: datetime


class ProformaSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pi_no: str
    quote_id: int | None
    status: str
    issue_date: date
    customer_snapshot: dict[str, Any]
    total: Decimal


# ----------------------------------------------------------- configurations


class ConfigurationItemIn(BaseModel):
    """A catalog part (``product_id``) prices from the catalog; a part typed by hand keeps
    ``cost_usd``. ``name`` is the printed text (default: the product's name)."""

    product_id: int | None = None
    name: str | None = Field(default=None, max_length=300)
    cost_usd: Decimal | None = Field(default=None, ge=0)
    qty: int = Field(default=1, ge=1)
    condition: Literal["new", "used"] | None = None
    emphasis: bool = False


class ConfigurationFields(BaseModel):
    name_zh: str | None = Field(default=None, max_length=300)
    notes: str | None = None
    platform: str | None = Field(default=None, max_length=120)
    device_type: DeviceType | None = None
    model_no: str | None = Field(default=None, max_length=120)
    material: str | None = Field(default=None, max_length=120)
    base_margin_pct: Decimal | None = Field(default=None, ge=-100, le=1000)
    image_ids: list[int] | None = None
    items: list[ConfigurationItemIn] | None = None


class ConfigurationCreate(ConfigurationFields):
    name: str = Field(min_length=1, max_length=300)


class ConfigurationPatch(ConfigurationFields):
    name: str | None = Field(default=None, min_length=1, max_length=300)


class ConfigurationItemOut(BaseModel):
    id: int
    product_id: int | None
    name: str
    qty: int
    condition: str | None
    emphasis: bool
    cost_usd: Decimal | None  # the part's own cost (typed by hand)
    unit_cost: Decimal | None  # what it costs now: catalog price or own cost
    product_name: str | None
    product_status: str | None
    price_date: date | None


class ConfigurationOut(BaseModel):
    id: int
    name: str
    name_zh: str | None
    notes: str | None
    platform: str | None
    device_type: str | None = None
    model_no: str | None
    material: str | None
    base_margin_pct: Decimal | None
    image_ids: list[int]
    items: list[ConfigurationItemOut]
    description_lines: list[DescriptionLine]  # as a quote prints it (English)
    unit_cost: Decimal | None
    saved_cost: Decimal | None
    cost_changed: bool
    missing_cost: int
    used_in: int  # quote lines
    updated_at: datetime


class ConfigurationSummary(BaseModel):
    id: int
    name: str
    name_zh: str | None
    platform: str | None
    device_type: str | None = None
    model_no: str | None
    parts: int
    unit_cost: Decimal | None
    saved_cost: Decimal | None
    cost_changed: bool
    missing_cost: int
    used_in: int
    image_id: int | None
    updated_at: datetime


class ConfigurationUsage(BaseModel):
    quote_id: int
    display_no: str
    status: str
    offer_date: date
    customer_name: str | None
    line_id: int
    qty: int
    unit_price: Decimal


class SaveLineAsConfiguration(BaseModel):
    quote_id: int
    line_id: int
    name: str | None = Field(default=None, max_length=300)
