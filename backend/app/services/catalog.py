"""Catalog writes: product create/update, attribute validation, prices, merge.

Every product write goes through here so the fingerprint, the denormalized current
price and the search index can never drift from the source rows.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.errors import ProblemError
from app.models import Brand, Category, PriceHistory, Product, ProductAlias
from app.models.catalog import PRICE_TIERS, PRODUCT_STATUSES
from app.services import search
from app.services.brands import BrandResolver
from app.services.importer.normalize import (
    compute_fingerprint,
    normalize_bool,
    parse_number,
    to_halfwidth,
)

PRODUCT_FIELDS = (
    "erp_code_alt", "mpn", "name_zh", "name_en", "name_en_auto", "status",
    "confirm_before_order", "lead_time_confirm", "needs_validation", "quote_on_request",
    "recommended", "stock_qty", "demand_qty", "stock_after_qty", "max_order_qty",
    "from_stock_qty", "payment_terms", "supply_note", "market", "notes_raw", "platform",
    "is_manual", "description_zh", "description_en", "model_no", "material",
)  # fmt: skip


def clean_attributes(schema: list[dict[str, Any]], attributes: dict[str, Any]) -> dict[str, Any]:
    """Validate attribute values against the category schema.

    Unknown keys are kept (source sheets carry extra columns worth preserving); empty
    values are dropped; number fields are stored as canonical decimal strings so no
    float round-trips through JSON. A number may carry the field's unit ("28W" for a
    field in W is stored as 28).
    """
    types = {field["key"]: field.get("type", "text") for field in schema}
    units = {field["key"]: field.get("unit") for field in schema}
    out: dict[str, Any] = {}
    for key, value in (attributes or {}).items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        attr_type = types.get(key, "text")
        if attr_type in ("number", "int"):
            number = parse_number(value, units.get(key))
            if number is None:
                raise ProblemError(
                    422, "product.invalid_attribute", f"{key} must be a number", key=key
                )
            if attr_type == "int" and number != number.to_integral_value():
                raise ProblemError(
                    422, "product.invalid_attribute", f"{key} must be an integer", key=key
                )
            out[key] = format(number.normalize(), "f")
        elif attr_type == "bool":
            out[key] = normalize_bool(value) == "1"
        else:
            out[key] = value.strip() if isinstance(value, str) else value
    return out


def _clean_erp(code: str | None) -> str | None:
    if code is None:
        return None
    code = to_halfwidth(code).strip().upper()
    return code or None


def fingerprint_for(
    session: Session,
    category: Category,
    brand: Brand | None,
    attributes: dict[str, Any],
    name_zh: str,
    resolver: BrandResolver | None = None,
    erp_qualifier: str | None = None,
) -> str:
    resolver = resolver or BrandResolver(session)
    return compute_fingerprint(
        category.code,
        brand.canonical if brand else None,
        category.attribute_schema,
        attributes,
        resolver.canonical,
        name_zh,
        erp_qualifier,
    )


def erp_codes_of(product: Product) -> set[str]:
    return {c.upper() for c in [product.erp_code, *(product.erp_code_alt or [])] if c}


def _fingerprint_holder(session: Session, fingerprint: str) -> Product | None:
    holder = session.scalar(select(Product).where(Product.fingerprint == fingerprint))
    if holder is None:
        alias = session.scalar(select(ProductAlias).where(ProductAlias.fingerprint == fingerprint))
        if alias is not None:
            holder = session.get(Product, alias.product_id)
    return holder


def resolve_fingerprint(
    session: Session,
    category: Category,
    brand: Brand | None,
    attributes: dict[str, Any],
    name_zh: str,
    erp_code: str | None,
    exclude_id: int | None,
) -> str:
    """The attribute fingerprint, qualified by the ERP code when another product with the
    same attributes carries a different ERP code (two boards "XN35" with their own codes)."""
    fingerprint = fingerprint_for(session, category, brand, attributes, name_zh)
    holder = _fingerprint_holder(session, fingerprint)
    if holder is None or holder.id == exclude_id or not erp_code:
        return fingerprint
    codes = erp_codes_of(holder)
    if codes and erp_code.upper() not in codes:
        return fingerprint_for(
            session, category, brand, attributes, name_zh, erp_qualifier=erp_code
        )
    return fingerprint


def _assert_unique(
    session: Session, fingerprint: str, erp_code: str | None, exclude_id: int | None
) -> None:
    clash = _fingerprint_holder(session, fingerprint)
    if clash is not None and clash.id != exclude_id:
        raise ProblemError(
            409,
            "product.duplicate",
            "A product with the same identifying attributes already exists",
            existing_id=clash.id,
            existing_name=clash.name_zh,
        )
    if erp_code:
        clash = session.scalar(select(Product).where(Product.erp_code == erp_code))
        if clash is not None and clash.id != exclude_id:
            raise ProblemError(
                409,
                "product.duplicate_erp",
                "ERP code already used",
                existing_id=clash.id,
                existing_name=clash.name_zh,
            )


def _get_category(session: Session, category_id: int) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise ProblemError(422, "category.not_found", "Unknown category", id=category_id)
    return category


def _get_brand(session: Session, brand_id: int | None) -> Brand | None:
    if brand_id is None:
        return None
    brand = session.get(Brand, brand_id)
    if brand is None:
        raise ProblemError(422, "brand.not_found", "Unknown brand", id=brand_id)
    return brand


def _check_status(status: str | None) -> None:
    if status is not None and status not in PRODUCT_STATUSES:
        raise ProblemError(422, "product.invalid_status", "Unknown status", status=status)


def create_product(session: Session, data: dict[str, Any]) -> Product:
    category = _get_category(session, data["category_id"])
    brand = _get_brand(session, data.get("brand_id"))
    _check_status(data.get("status"))
    attributes = clean_attributes(category.attribute_schema, data.get("attributes") or {})
    name_zh = data["name_zh"].strip()
    erp_code = _clean_erp(data.get("erp_code"))
    fingerprint = resolve_fingerprint(session, category, brand, attributes, name_zh, erp_code, None)
    _assert_unique(session, fingerprint, erp_code, None)

    product = Product(
        category=category,
        brand=brand,
        attributes=attributes,
        fingerprint=fingerprint,
        erp_code=erp_code,
        **{k: v for k, v in data.items() if k in PRODUCT_FIELDS and v is not None},
    )
    product.name_zh = name_zh
    session.add(product)
    session.flush()

    price = data.get("price_usd")
    if price is not None:
        set_price(session, product, Decimal(price), price_date=data.get("price_date"))
    search.index_product(session, product)
    return product


def update_product(session: Session, product: Product, data: dict[str, Any]) -> Product:
    _check_status(data.get("status"))
    category = _get_category(session, data["category_id"]) if "category_id" in data else None
    if category is not None:
        product.category = category
    if "brand_id" in data:
        product.brand = _get_brand(session, data["brand_id"])
    if "attributes" in data:
        product.attributes = clean_attributes(
            product.category.attribute_schema, data["attributes"] or {}
        )
    elif category is not None:
        product.attributes = clean_attributes(category.attribute_schema, product.attributes)
    if "erp_code" in data:
        product.erp_code = _clean_erp(data["erp_code"])
    for key in PRODUCT_FIELDS:
        if key in data:
            setattr(product, key, data[key])
    if not (product.name_zh or "").strip():
        raise ProblemError(422, "product.name_required", "Chinese name is required")
    product.name_zh = product.name_zh.strip()

    fingerprint = resolve_fingerprint(
        session,
        product.category,
        product.brand,
        product.attributes,
        product.name_zh,
        product.erp_code,
        product.id,
    )
    _assert_unique(session, fingerprint, product.erp_code, product.id)
    product.fingerprint = fingerprint
    session.flush()
    search.index_product(session, product)
    return product


def delete_product(session: Session, product: Product) -> None:
    search.remove_product(session, product.id)
    session.delete(product)
    session.flush()


def refresh_current_price(session: Session, product: Product) -> None:
    rows = session.scalars(
        select(PriceHistory).where(
            PriceHistory.product_id == product.id, PriceHistory.is_current.is_(True)
        )
    ).all()
    by_tier = {row.tier: row for row in rows}
    standard = by_tier.get("standard")
    forecast = by_tier.get("forecast")
    product.current_price_usd = standard.price_usd if standard else None
    product.current_price_tier_forecast_usd = forecast.price_usd if forecast else None
    dated = standard or forecast
    product.price_date = dated.price_date if dated else None


def set_price(
    session: Session,
    product: Product,
    price_usd: Decimal,
    tier: str = "standard",
    price_date: date | None = None,
    import_id: int | None = None,
    source_ref: str | None = None,
    note: str | None = None,
    amount_original: Decimal | None = None,
    currency_original: str | None = None,
    fx_rate: Decimal | None = None,
) -> PriceHistory:
    """Record a new current price. The newest write always wins ("last upload wins")."""
    if tier not in PRICE_TIERS:
        raise ProblemError(422, "price.invalid_tier", "Unknown price tier", tier=tier)
    if price_usd < 0:
        raise ProblemError(422, "price.negative", "Price cannot be negative")
    session.execute(
        update(PriceHistory)
        .where(PriceHistory.product_id == product.id, PriceHistory.tier == tier)
        .values(is_current=False)
    )
    row = PriceHistory(
        product_id=product.id,
        import_id=import_id,
        price_usd=price_usd,
        tier=tier,
        amount_original=amount_original if amount_original is not None else price_usd,
        currency_original=currency_original or "USD",
        fx_rate=fx_rate,
        price_date=price_date or date.today(),
        source_ref=source_ref,
        note=note,
        is_current=True,
    )
    session.add(row)
    session.flush()
    refresh_current_price(session, product)
    return row


def merge_products(session: Session, keep: Product, drop: Product) -> Product:
    """Fold ``drop`` into ``keep``; future imports of ``drop``'s fingerprint resolve to keep."""
    if keep.id == drop.id:
        raise ProblemError(422, "product.merge_self", "Cannot merge a product into itself")

    # The kept product's current prices stay current unless it has none for a tier.
    keep_tiers = set(
        session.scalars(
            select(PriceHistory.tier).where(
                PriceHistory.product_id == keep.id, PriceHistory.is_current.is_(True)
            )
        )
    )
    for row in session.scalars(select(PriceHistory).where(PriceHistory.product_id == drop.id)):
        row.product_id = keep.id
        if row.tier in keep_tiers:
            row.is_current = False

    session.execute(
        update(ProductAlias).where(ProductAlias.product_id == drop.id).values(product_id=keep.id)
    )
    session.add(
        ProductAlias(product_id=keep.id, fingerprint=drop.fingerprint, name_zh=drop.name_zh)
    )

    dropped_codes = [c for c in [drop.erp_code, *(drop.erp_code_alt or [])] if c]
    drop.erp_code = None
    session.flush()
    if dropped_codes:
        if keep.erp_code is None:
            keep.erp_code = dropped_codes.pop(0)
        keep.erp_code_alt = list(dict.fromkeys([*(keep.erp_code_alt or []), *dropped_codes]))
    for key in ("mpn", "name_en", "brand_id", "description_zh", "description_en"):
        if getattr(keep, key) in (None, "") and getattr(drop, key) not in (None, ""):
            setattr(keep, key, getattr(drop, key))

    search.remove_product(session, drop.id)
    session.delete(drop)
    session.flush()
    refresh_current_price(session, keep)
    search.index_product(session, keep)
    return keep
