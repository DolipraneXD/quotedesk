from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AttributeField(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label_en: str
    label_zh: str
    type: str = "text"
    unit: str | None = None
    options: list[str] | None = None
    in_fingerprint: bool = False


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_en: str
    name_zh: str
    is_main: bool
    attribute_schema: list[AttributeField]
    default_margin_pct: Decimal | None
    sort_order: int
    product_count: int = 0


class CategoryCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=40)
    name_en: str
    name_zh: str
    is_main: bool = False
    attribute_schema: list[AttributeField] = Field(default_factory=list)
    default_margin_pct: Decimal | None = None
    sort_order: int = 100


class CategoryUpdate(BaseModel):
    name_en: str | None = None
    name_zh: str | None = None
    is_main: bool | None = None
    attribute_schema: list[AttributeField] | None = None
    default_margin_pct: Decimal | None = None
    sort_order: int | None = None


class BrandAliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alias: str
    lang: str


class BrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    canonical: str
    name_en: str | None
    name_zh: str | None
    needs_review: bool
    aliases: list[BrandAliasOut]
    product_count: int = 0


class BrandCreate(BaseModel):
    canonical: str = Field(min_length=1, max_length=120)
    name_en: str | None = None
    name_zh: str | None = None


class BrandUpdate(BaseModel):
    canonical: str | None = Field(default=None, min_length=1, max_length=120)
    name_en: str | None = None
    name_zh: str | None = None
    needs_review: bool | None = None


class AliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=120)
    lang: str = "en"


class BrandRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    canonical: str
    name_zh: str | None


class ImportRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str
    committed_at: datetime | None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    erp_code: str | None
    erp_code_alt: list[str]
    mpn: str | None
    name_zh: str
    name_en: str | None
    name_en_auto: bool
    brand_id: int | None
    brand: BrandRef | None
    attributes: dict[str, Any]
    fingerprint: str
    current_price_usd: Decimal | None
    current_price_tier_forecast_usd: Decimal | None
    price_date: date | None
    last_import_id: int | None
    created_import_id: int | None
    created_import: ImportRef | None
    last_import: ImportRef | None
    status: str
    confirm_before_order: bool
    lead_time_confirm: bool
    needs_validation: bool
    quote_on_request: bool
    recommended: bool
    stock_qty: int | None
    demand_qty: int | None
    stock_after_qty: int | None
    max_order_qty: int | None
    from_stock_qty: int | None
    payment_terms: str | None
    supply_note: str | None
    market: str | None
    notes_raw: str | None
    platform: str | None
    is_manual: bool
    description_zh: str | None
    description_en: str | None
    model_no: str | None
    material: str | None
    image_ids: list[int] = []
    created_at: datetime
    updated_at: datetime


class ProductList(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int


class _ProductFields(BaseModel):
    erp_code: str | None = None
    erp_code_alt: list[str] | None = None
    mpn: str | None = None
    name_en: str | None = None
    brand_id: int | None = None
    attributes: dict[str, Any] | None = None
    status: str | None = None
    confirm_before_order: bool | None = None
    lead_time_confirm: bool | None = None
    needs_validation: bool | None = None
    quote_on_request: bool | None = None
    recommended: bool | None = None
    stock_qty: int | None = None
    demand_qty: int | None = None
    stock_after_qty: int | None = None
    max_order_qty: int | None = None
    from_stock_qty: int | None = None
    payment_terms: str | None = None
    supply_note: str | None = None
    market: str | None = None
    notes_raw: str | None = None
    platform: str | None = None
    description_zh: str | None = None
    description_en: str | None = None
    model_no: str | None = None
    material: str | None = None


class ProductCreate(_ProductFields):
    category_id: int
    name_zh: str = Field(min_length=1, max_length=300)
    is_manual: bool = False
    price_usd: Decimal | None = Field(default=None, ge=0)
    price_date: date | None = None


class ProductUpdate(_ProductFields):
    category_id: int | None = None
    name_zh: str | None = Field(default=None, min_length=1, max_length=300)


class PriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    import_id: int | None
    price_usd: Decimal
    tier: str
    amount_original: Decimal | None
    currency_original: str | None
    fx_rate: Decimal | None
    price_date: date | None
    source_ref: str | None
    note: str | None
    is_current: bool
    created_at: datetime


class PriceCreate(BaseModel):
    price_usd: Decimal = Field(ge=0)
    tier: str = "standard"
    price_date: date | None = None
    note: str | None = None


class MergeRequest(BaseModel):
    into_id: int


class ProductAliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fingerprint: str
    name_zh: str | None
    created_at: datetime


class NoteRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pattern: str
    field: str
    kind: str
    value: str | None
    sort_order: int
    enabled: bool
