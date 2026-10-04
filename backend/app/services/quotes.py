"""Quote building: pricing, numbering, line snapshots, warnings (plan §5.2).

Pricing, all Decimal:
    margin     = line.margin ?? customer.default ?? category.default ?? settings.default
    unit_price = round_half_up(cost × (1 + margin / 100), rounding)   unless typed by hand
    total      = round_half_up(qty × unit_price, 2)
    subtotal   = Σ section subtotals; grand_total = subtotal − discount
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import AppSettings, load_settings
from app.errors import ProblemError
from app.models import (
    Category,
    Customer,
    Product,
    ProductImage,
    Quote,
    QuoteLine,
    QuoteSection,
)
from app.models.quotes import QUOTE_STATUSES, SECTION_LAYOUTS
from app.services import catalog

CENT = Decimal("0.01")
HUNDRED = Decimal("100")
CUSTOMER_FIELDS = ("code", "name", "contact_name", "email", "phone", "address")


def round_money(value: Decimal, places: int = 2) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def today() -> date:
    return datetime.now(UTC).astimezone().date()


# ---------------------------------------------------------------- pricing


def resolve_margin(
    line: QuoteLine,
    customer: Customer | None,
    category: Category | None,
    settings: AppSettings,
) -> Decimal:
    for candidate in (
        line.margin_pct,
        customer.default_margin_pct if customer else None,
        category.default_margin_pct if category else None,
    ):
        if candidate is not None:
            return Decimal(candidate)
    return Decimal(settings.default_margin_pct)


def price_line(line: QuoteLine, margin: Decimal, rounding: int) -> None:
    """Unit price from cost and margin, unless the seller typed the unit price."""
    if not line.unit_price_manual and line.cost_usd is not None:
        line.unit_price = round_money(line.cost_usd * (1 + margin / HUNDRED), rounding)
    line.total = round_money(Decimal(line.qty) * Decimal(line.unit_price or 0))


def effective_margin(line: QuoteLine, resolved: Decimal) -> Decimal | None:
    """The margin the unit price actually carries (shown when the price was typed)."""
    if not line.unit_price_manual:
        return resolved
    if not line.cost_usd:
        return None
    return round_money((Decimal(line.unit_price) / line.cost_usd - 1) * HUNDRED, 2)


def recalculate(session: Session, quote: Quote, settings: AppSettings | None = None) -> None:
    settings = settings or load_settings()
    categories = {c.id: c for c in session.scalars(select(Category))}
    subtotal = Decimal("0")
    for section in quote.sections:
        section_total = Decimal("0")
        for line in section.lines:
            if line.kind == "config":
                line.cost_usd = components_cost(line.components or [])
            category = categories.get(line.category_id) if line.category_id else None
            margin = resolve_margin(line, quote.customer, category, settings)
            price_line(line, margin, settings.rounding)
            section_total += line.total
        section.subtotal = section_total
        subtotal += section_total
    quote.subtotal = subtotal
    discount = Decimal("0")
    if quote.discount_amount is not None:
        discount = Decimal(quote.discount_amount)
    elif quote.discount_pct is not None:
        discount = round_money(subtotal * Decimal(quote.discount_pct) / HUNDRED)
    quote.grand_total = subtotal - discount


# -------------------------------------------------------------- numbering


def next_offer_no(session: Session, prefix: str, day: date) -> str:
    """WKZ20260811-01, -02 … one sequence per day (plan A6)."""
    base = f"{prefix}{day:%Y%m%d}-"
    taken = session.scalars(select(Quote.offer_no).where(Quote.offer_no.like(f"{base}%")))
    numbers = [
        int(m.group(1)) for no in taken if (m := re.fullmatch(rf"{re.escape(base)}(\d+)", no))
    ]
    return f"{base}{max(numbers, default=0) + 1:02d}"


# ------------------------------------------------------------- customers


def customer_snapshot(customer: Customer | None) -> dict[str, Any]:
    if customer is None:
        return {}
    return {key: getattr(customer, key) for key in CUSTOMER_FIELDS}


def apply_customer(quote: Quote, customer: Customer | None, fill_defaults: bool) -> None:
    quote.customer = customer
    quote.customer_id = customer.id if customer else None
    quote.customer_snapshot = customer_snapshot(customer)
    if customer is not None and fill_defaults:
        quote.contact = customer.contact_name
        quote.contact_email = customer.email
        quote.trade_term = customer.trade_term
        quote.payment_terms = customer.payment_terms
        quote.language = customer.language or quote.language


# ---------------------------------------------------------------- quotes


def get_customer(session: Session, customer_id: int | None) -> Customer | None:
    if customer_id is None:
        return None
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise ProblemError(422, "customer.not_found", "Unknown customer", id=customer_id)
    return customer


def create_quote(session: Session, data: dict[str, Any]) -> Quote:
    settings = load_settings()
    offer_date = data.get("offer_date") or today()
    quote = Quote(
        offer_no=next_offer_no(session, settings.offer_prefix, offer_date),
        revision=1,
        status="draft",
        offer_date=offer_date,
        validity_days=data.get("validity_days", settings.default_validity_days),
        currency="USD",
        language=data.get("language") or "en",
    )
    apply_customer(quote, get_customer(session, data.get("customer_id")), fill_defaults=True)
    quote.sections = [QuoteSection(layout=data.get("layout") or "offer", sort_order=0)]
    session.add(quote)
    session.flush()
    return quote


QUOTE_FIELDS = (
    "offer_date", "validity_days", "contact", "contact_email", "trade_term",
    "payment_terms", "language", "notes_header", "notes_footer", "discount_pct",
    "discount_amount",
)  # fmt: skip


def update_quote(session: Session, quote: Quote, data: dict[str, Any]) -> Quote:
    if "status" in data:
        set_status(quote, data["status"])
    if "customer_id" in data and data["customer_id"] != quote.customer_id:
        apply_customer(quote, get_customer(session, data["customer_id"]), fill_defaults=True)
    for key in QUOTE_FIELDS:
        if key in data:
            setattr(quote, key, data[key])
    if quote.customer is not None:
        quote.customer_snapshot = customer_snapshot(quote.customer)
    recalculate(session, quote)
    session.flush()
    return quote


def set_status(quote: Quote, status: str) -> None:
    if status not in QUOTE_STATUSES:
        raise ProblemError(422, "quote.invalid_status", "Unknown status", status=status)
    quote.status = status


def valid_until(quote: Quote) -> date | None:
    return quote.offer_date + timedelta(days=quote.validity_days) if quote.validity_days else None


def copy_quote(session: Session, source: Quote, *, revision: bool) -> Quote:
    """A new revision keeps the offer number (``… R2``); a duplicate gets a new number."""
    settings = load_settings()
    if revision:
        top = session.scalar(
            select(func.max(Quote.revision)).where(Quote.offer_no == source.offer_no)
        )
        offer_no, number, offer_date = source.offer_no, (top or 1) + 1, today()
    else:
        offer_date = today()
        offer_no, number = next_offer_no(session, settings.offer_prefix, offer_date), 1
    quote = Quote(
        offer_no=offer_no,
        revision=number,
        parent_quote_id=source.id if revision else None,
        status="draft",
        offer_date=offer_date,
        currency=source.currency,
        customer_id=source.customer_id,
        customer=source.customer,
        customer_snapshot=dict(source.customer_snapshot or {}),
    )
    for key in QUOTE_FIELDS:
        if key != "offer_date":
            setattr(quote, key, getattr(source, key))
    quote.sections = [
        QuoteSection(
            title=section.title,
            layout=section.layout,
            sort_order=section.sort_order,
            lines=[_copy_line(line) for line in section.lines],
        )
        for section in source.sections
    ]
    session.add(quote)
    recalculate(session, quote, settings)
    session.flush()
    return quote


LINE_COPY_FIELDS = (
    "sort_order", "line_no", "kind", "product_id", "category_id", "name", "name_emphasis",
    "description_lines", "model_no", "material", "image_ids", "qty", "cost_usd",
    "margin_pct", "unit_price", "unit_price_manual", "total", "price_source", "components",
    "configuration_id",
)  # fmt: skip


def _copy_line(line: QuoteLine) -> QuoteLine:
    copy = QuoteLine()
    for key in LINE_COPY_FIELDS:
        value = getattr(line, key)
        setattr(copy, key, list(value) if isinstance(value, list) else value)
    return copy


# --------------------------------------------------------------- sections


def get_section(quote: Quote, section_id: int) -> QuoteSection:
    for section in quote.sections:
        if section.id == section_id:
            return section
    raise ProblemError(404, "quote.section_not_found", "Section not found", id=section_id)


def add_section(session: Session, quote: Quote, data: dict[str, Any]) -> QuoteSection:
    layout = data.get("layout") or (quote.sections[-1].layout if quote.sections else "offer")
    _check_layout(layout)
    section = QuoteSection(
        title=data.get("title"),
        layout=layout,
        sort_order=max((s.sort_order for s in quote.sections), default=-1) + 1,
    )
    quote.sections.append(section)
    session.flush()
    return section


def update_section(section: QuoteSection, data: dict[str, Any]) -> None:
    if "layout" in data:
        _check_layout(data["layout"])
        section.layout = data["layout"]
    if "title" in data:
        section.title = data["title"]
    if "sort_order" in data:
        section.sort_order = data["sort_order"]


def _check_layout(layout: str) -> None:
    if layout not in SECTION_LAYOUTS:
        raise ProblemError(422, "quote.invalid_layout", "Unknown layout", layout=layout)


# ------------------------------------------------------------------ lines


def description_from_product(product: Product, language: str) -> list[dict[str, Any]]:
    text = (product.description_zh if language == "zh" else product.description_en) or (
        product.description_en or product.description_zh
    )
    if not text:
        text = str(product.attributes.get("description") or "")
    if not text:
        summary = [
            str(value)
            for key, value in product.attributes.items()
            if key not in ("model", "description") and not key.startswith("cost_")
            and value not in (None, "", False)
        ]  # fmt: skip
        text = " ".join(summary)
    return [{"text": t.strip(), "emphasis": False} for t in text.splitlines() if t.strip()]


def product_image_ids(session: Session, product_id: int) -> list[int]:
    return list(
        session.scalars(
            select(ProductImage.image_id)
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.sort_order, ProductImage.id)
        )
    )


def _next_sort(section: QuoteSection) -> int:
    return max((line.sort_order for line in section.lines), default=-1) + 1


def add_product_line(
    session: Session, quote: Quote, section: QuoteSection, product: Product, qty: int
) -> QuoteLine:
    language = quote.language
    name = product.name_en if language == "en" and product.name_en else product.name_zh
    line = QuoteLine(
        kind="product",
        product_id=product.id,
        category_id=product.category_id,
        name=name,
        description_lines=description_from_product(product, language),
        model_no=product.model_no or product.attributes.get("model") or product.mpn,
        material=product.material,
        image_ids=product_image_ids(session, product.id),
        qty=qty,
        cost_usd=product.current_price_usd,
        sort_order=_next_sort(section),
        price_source={
            "price_date": product.price_date.isoformat() if product.price_date else None,
            "import_id": product.last_import_id,
            "tier": "standard",
        },
    )
    section.lines.append(line)
    recalculate(session, quote)
    session.flush()
    return line


def add_manual_line(
    session: Session, quote: Quote, section: QuoteSection, data: dict[str, Any]
) -> QuoteLine:
    """A component typed by hand; optionally saved to the catalog (plan A7)."""
    cost = data.get("cost_usd")
    category_id = data.get("category_id")
    product_id = None
    if data.get("save_to_catalog"):
        if category_id is None:
            raise ProblemError(422, "quote.category_required", "Pick a category to save it")
        description = "\n".join(d["text"] for d in data.get("description_lines") or [])
        product = catalog.create_product(
            session,
            {
                "category_id": category_id,
                "name_zh": data["name"],
                "name_en": data["name"],
                "attributes": {},
                "is_manual": True,
                "description_en": description or None,
                "model_no": data.get("model_no"),
                "material": data.get("material"),
                "price_usd": cost,
            },
        )
        product_id = product.id
    line = QuoteLine(
        kind="manual",
        product_id=product_id,
        category_id=category_id,
        name=data["name"],
        description_lines=data.get("description_lines") or [],
        model_no=data.get("model_no"),
        material=data.get("material"),
        qty=data.get("qty") or 1,
        cost_usd=cost,
        sort_order=_next_sort(section),
    )
    if data.get("unit_price") is not None:
        line.unit_price = Decimal(data["unit_price"])
        line.unit_price_manual = True
    section.lines.append(line)
    recalculate(session, quote)
    session.flush()
    return line


# ------------------------------------------------------- combined products

CONDITIONS = {"en": {"new": "(New)", "used": "(Used)"}, "zh": {"new": "(全新)", "used": "(二手)"}}


def components_cost(components: list[dict[str, Any]]) -> Decimal | None:
    """Cost of one combined unit: Σ qty × cost over the parts that have a cost."""
    costs = [
        Decimal(c["qty"]) * Decimal(c["cost_usd"])
        for c in components
        if c.get("cost_usd") is not None
    ]
    return sum(costs, Decimal("0")) if costs else None


def describe_components(components: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    """One description line per part, the way the 2-in-1 sample lists a laptop's specs."""
    words = CONDITIONS["zh" if language == "zh" else "en"]
    lines = []
    for c in components:
        text = str(c["name"])
        if c.get("condition") in words:
            text = f"{text} {words[c['condition']]}"
        if c["qty"] > 1:
            text = f"{c['qty']}*{text}"
        lines.append({"text": text, "emphasis": bool(c.get("emphasis"))})
    return lines


def _product_name(product: Product, language: str) -> str:
    return product.name_en if language == "en" and product.name_en else product.name_zh


def _component(session: Session, data: dict[str, Any], language: str) -> dict[str, Any]:
    """A part as stored on the line. A part given only by product_id is copied from the
    catalog now (a snapshot); parts sent back with their name keep their values."""
    product_id = data.get("product_id")
    item: dict[str, Any] = {
        "product_id": product_id,
        "name": (data.get("name") or "").strip(),
        "qty": int(data.get("qty") or 1),
        "cost_usd": None if data.get("cost_usd") is None else str(Decimal(data["cost_usd"])),
        "condition": data.get("condition"),
        "emphasis": bool(data.get("emphasis")),
        "price_date": data.get("price_date"),
    }
    if isinstance(item["price_date"], date):
        item["price_date"] = item["price_date"].isoformat()
    if product_id is not None and not item["name"]:
        product = session.get(Product, product_id)
        if product is None:
            raise ProblemError(404, "product.not_found", "Product not found", id=product_id)
        item["name"] = _product_name(product, language)
        if product.current_price_usd is not None:
            item["cost_usd"] = str(product.current_price_usd)
        item["price_date"] = product.price_date.isoformat() if product.price_date else None
    if not item["name"]:
        raise ProblemError(422, "quote.name_required", "A part needs a name")
    if item["qty"] < 1:
        raise ProblemError(422, "quote.invalid_qty", "Quantity must be at least 1")
    return item


def set_components(
    session: Session, quote: Quote, line: QuoteLine, items: list[dict[str, Any]]
) -> None:
    """Replace the parts. The description follows them unless the seller edited it."""
    if line.kind != "config":
        raise ProblemError(409, "quote.not_combined", "This line is not a combined product")
    old = line.components or []
    auto = (line.description_lines or []) == describe_components(old, quote.language)
    line.components = [_component(session, item, quote.language) for item in items]
    if auto:
        line.description_lines = describe_components(line.components, quote.language)
    if not line.image_ids:
        line.image_ids = _first_photos(session, line.components)
    recalculate(session, quote)
    session.flush()


def _first_photos(session: Session, components: list[dict[str, Any]]) -> list[int]:
    for c in components:
        if c.get("product_id") and (ids := product_image_ids(session, c["product_id"])):
            return ids
    return []


def add_config_line(
    session: Session, quote: Quote, section: QuoteSection, data: dict[str, Any]
) -> QuoteLine:
    components = [_component(session, c, quote.language) for c in data.get("components") or []]
    line = QuoteLine(
        kind="config",
        name=data["name"],
        model_no=data.get("model_no"),
        material=data.get("material"),
        qty=data.get("qty") or 1,
        components=components,
        description_lines=describe_components(components, quote.language),
        image_ids=_first_photos(session, components),
        sort_order=_next_sort(section),
    )
    section.lines.append(line)
    recalculate(session, quote)
    session.flush()
    return line


def combine_lines(session: Session, quote: Quote, line_ids: list[int], name: str) -> QuoteLine:
    """Several lines of one table become one combined product, at the first line's place.
    Its quantity is the largest number that divides every line's quantity, so lines of
    8,202 CPUs and 16,404 RAM sticks give 8,202 units with 2 sticks each."""
    lines = [get_line(quote, line_id) for line_id in dict.fromkeys(line_ids)]
    if len(lines) < 2:
        raise ProblemError(422, "quote.combine_two", "Pick at least two lines to combine")
    section = lines[0].section
    if any(line.section is not section for line in lines):
        raise ProblemError(422, "quote.combine_one_table", "The lines must be in one table")
    if any(line.kind == "config" for line in lines):
        raise ProblemError(422, "quote.combine_nested", "A combined product can't be combined")
    lines.sort(key=lambda line: section.lines.index(line))
    units = 0
    for line in lines:
        units = math.gcd(units, line.qty)
    components = [
        {
            "product_id": line.product_id,
            "name": line.name,
            "qty": line.qty // units,
            "cost_usd": None if line.cost_usd is None else str(line.cost_usd),
            "condition": None,
            "emphasis": False,
            "price_date": (line.price_source or {}).get("price_date"),
        }
        for line in lines
    ]
    combined = QuoteLine(
        kind="config",
        name=name,
        qty=units,
        components=components,
        description_lines=describe_components(components, quote.language),
        image_ids=next((list(line.image_ids) for line in lines if line.image_ids), []),
        sort_order=lines[0].sort_order,
    )
    position = section.lines.index(lines[0])
    for line in lines:
        section.lines.remove(line)
        session.delete(line)
    section.lines.insert(position, combined)
    _renumber(section)
    recalculate(session, quote)
    session.flush()
    return combined


def split_line(session: Session, quote: Quote, line: QuoteLine) -> list[QuoteLine]:
    """The opposite of combining: one line per part, quantity = parts per unit × units."""
    if line.kind != "config":
        raise ProblemError(409, "quote.not_combined", "This line is not a combined product")
    section = line.section
    position = section.lines.index(line)
    parts = []
    for c in line.components or []:
        product = session.get(Product, c["product_id"]) if c.get("product_id") else None
        part = QuoteLine(
            kind="product" if product else "manual",
            product_id=product.id if product else None,
            category_id=product.category_id if product else None,
            name=c["name"],
            description_lines=description_from_product(product, quote.language) if product
            else [],
            model_no=(product.model_no or product.attributes.get("model") or product.mpn)
            if product else None,
            material=product.material if product else None,
            image_ids=product_image_ids(session, product.id) if product else [],
            qty=c["qty"] * line.qty,
            cost_usd=None if c.get("cost_usd") is None else Decimal(c["cost_usd"]),
            price_source={"price_date": c.get("price_date"), "tier": "standard"},
        )  # fmt: skip
        parts.append(part)
    section.lines.remove(line)
    session.delete(line)
    section.lines[position:position] = parts
    _renumber(section)
    recalculate(session, quote)
    session.flush()
    return parts


def _renumber(section: QuoteSection) -> None:
    for index, line in enumerate(section.lines):
        line.sort_order = index


LINE_FIELDS = (
    "line_no", "name", "name_emphasis", "description_lines", "model_no", "material",
    "image_ids", "qty", "cost_usd", "margin_pct",
)  # fmt: skip


def update_line(session: Session, quote: Quote, line: QuoteLine, data: dict[str, Any]) -> None:
    if data.get("components") is not None:
        set_components(session, quote, line, data["components"])
    for key in LINE_FIELDS:
        if key in data:
            setattr(line, key, data[key])
    if data.get("describe") and line.kind == "config":
        line.description_lines = describe_components(line.components or [], quote.language)
    if "margin_pct" in data:
        line.unit_price_manual = False  # a margin decides the price again
    if data.get("unit_price") is not None:
        line.unit_price = Decimal(data["unit_price"])
        line.unit_price_manual = True
    elif "unit_price" in data:  # null: back to cost × margin
        line.unit_price_manual = False
    if "section_id" in data and data["section_id"] != line.section_id:
        target = get_section(quote, data["section_id"])
        line.section.lines.remove(line)
        line.sort_order = _next_sort(target)
        target.lines.append(line)
    if line.qty < 1:
        raise ProblemError(422, "quote.invalid_qty", "Quantity must be at least 1")
    recalculate(session, quote)
    session.flush()


def refresh_line_cost(session: Session, quote: Quote, line: QuoteLine) -> None:
    """Take the product's current price (after a 'price changed' warning)."""
    if line.kind == "config":
        refreshed = []
        for c in line.components or []:
            product = session.get(Product, c["product_id"]) if c.get("product_id") else None
            if product is not None and product.current_price_usd is not None:
                c = {**c, "cost_usd": str(product.current_price_usd),
                     "price_date": product.price_date.isoformat() if product.price_date
                     else None}  # fmt: skip
            refreshed.append(c)
        line.components = refreshed
        recalculate(session, quote)
        session.flush()
        return
    product = session.get(Product, line.product_id) if line.product_id else None
    if product is None:
        raise ProblemError(409, "quote.no_product", "This line is not linked to a product")
    line.cost_usd = product.current_price_usd
    line.price_source = {
        "price_date": product.price_date.isoformat() if product.price_date else None,
        "import_id": product.last_import_id,
        "tier": "standard",
    }
    recalculate(session, quote)
    session.flush()


def reorder_lines(session: Session, quote: Quote, section: QuoteSection, ids: list[int]) -> None:
    by_id = {line.id: line for line in section.lines}
    if sorted(ids) != sorted(by_id):
        raise ProblemError(422, "quote.bad_order", "The order must list every line once")
    for position, line_id in enumerate(ids):
        by_id[line_id].sort_order = position
    section.lines.sort(key=lambda line: line.sort_order)
    session.flush()


def get_line(quote: Quote, line_id: int) -> QuoteLine:
    for section in quote.sections:
        for line in section.lines:
            if line.id == line_id:
                return line
    raise ProblemError(404, "quote.line_not_found", "Line not found", id=line_id)


def printed_numbers(section: QuoteSection) -> list[str]:
    """The NO column: the seller's own number, else the position in the table."""
    return [line.line_no or str(index) for index, line in enumerate(section.lines, start=1)]


# ---------------------------------------------------------------- costing


@dataclass
class PartCost:
    component: dict[str, Any]
    cost_total: Decimal | None  # for all units of the line


@dataclass
class LineCost:
    number: str
    line: QuoteLine
    margin: Decimal | None  # what the unit price carries over cost
    cost_total: Decimal | None
    profit: Decimal | None
    parts: list[PartCost]


@dataclass
class SectionCost:
    section: QuoteSection
    lines: list[LineCost]
    cost: Decimal  # lines with a cost only
    revenue: Decimal
    profit: Decimal


@dataclass
class Costing:
    """The seller's own view of a quote: cost, margin and profit (never printed for the
    customer). Profit is counted on the lines that have a cost; the discount comes off it."""

    sections: list[SectionCost]
    cost: Decimal
    discount: Decimal
    profit: Decimal
    missing_cost: int  # lines and parts without a cost, left out of cost and profit

    @property
    def margin_on_cost(self) -> Decimal | None:
        return round_money(self.profit / self.cost * HUNDRED) if self.cost else None


def costing(session: Session, quote: Quote, settings: AppSettings | None = None) -> Costing:
    settings = settings or load_settings()
    categories = {c.id: c for c in session.scalars(select(Category))}
    sections: list[SectionCost] = []
    missing = 0
    for section in quote.sections:
        lines: list[LineCost] = []
        cost = revenue = profit = Decimal("0")
        for number, line in zip(printed_numbers(section), section.lines, strict=True):
            category = categories.get(line.category_id) if line.category_id else None
            margin = effective_margin(
                line, resolve_margin(line, quote.customer, category, settings)
            )
            revenue += line.total
            parts = [
                PartCost(
                    c,
                    None if c.get("cost_usd") is None
                    else round_money(line.qty * c["qty"] * Decimal(c["cost_usd"])),
                )
                for c in (line.components or [])
            ]  # fmt: skip
            missing += sum(1 for part in parts if part.cost_total is None)
            if line.cost_usd is None:
                missing += 0 if parts else 1
                lines.append(LineCost(number, line, None, None, None, parts))
                continue
            line_cost = round_money(Decimal(line.qty) * Decimal(line.cost_usd))
            lines.append(LineCost(number, line, margin, line_cost, line.total - line_cost, parts))
            cost += line_cost
            profit += line.total - line_cost
        sections.append(SectionCost(section, lines, cost, revenue, profit))
    discount = Decimal(quote.subtotal) - Decimal(quote.grand_total)
    total_cost = sum((s.cost for s in sections), Decimal("0"))
    total_profit = sum((s.profit for s in sections), Decimal("0")) - discount
    return Costing(sections, total_cost, discount, total_profit, missing)


# --------------------------------------------------------------- warnings


def component_warnings(
    line: QuoteLine, products: dict[int, Product], settings: AppSettings
) -> list[dict[str, Any]]:
    """The parts of a combined product, checked like lines; each warning names its part."""
    warnings: list[dict[str, Any]] = []
    for c in line.components or []:
        part = {"part": c["name"]}
        product = products.get(c["product_id"]) if c.get("product_id") else None
        if c.get("product_id") and product is None:
            warnings.append({"code": "product_deleted", **part})
        if c.get("cost_usd") is None:
            warnings.append({"code": "no_price", **part})
        if product is None:
            continue
        if product.status in ("discontinued", "stock_only", "no_supply", "inactive"):
            warnings.append({"code": "status", "status": product.status, **part})
        if product.price_date is not None:
            age = (today() - product.price_date).days
            if age > settings.price_age_warning_days:
                warnings.append({"code": "old_price", "days": age, **part})
        if (
            c.get("cost_usd") is not None
            and product.current_price_usd is not None
            and product.current_price_usd != Decimal(c["cost_usd"])
        ):
            warnings.append(
                {"code": "price_changed", "now": str(product.current_price_usd),
                 "was": c["cost_usd"], **part}
            )  # fmt: skip
    return warnings


def line_warnings(
    line: QuoteLine, product: Product | None, settings: AppSettings
) -> list[dict[str, Any]]:
    """Live checks against the product as it is now (plan §5.2 warnings icon)."""
    warnings: list[dict[str, Any]] = []
    if line.kind == "product" and line.product_id is not None and product is None:
        warnings.append({"code": "product_deleted"})
    if line.cost_usd is None and not line.unit_price_manual and not line.components:
        warnings.append({"code": "no_price"})
    if product is None:
        return warnings
    if product.status in ("discontinued", "stock_only", "no_supply", "inactive"):
        warnings.append({"code": "status", "status": product.status})
    for flag in ("confirm_before_order", "needs_validation", "quote_on_request"):
        if getattr(product, flag):
            warnings.append({"code": flag})
    if product.stock_qty == 0:
        warnings.append({"code": "no_stock"})
    if product.max_order_qty is not None and line.qty > product.max_order_qty:
        warnings.append({"code": "over_max_order", "max": product.max_order_qty})
    if product.price_date is not None:
        age = (today() - product.price_date).days
        if age > settings.price_age_warning_days:
            warnings.append({"code": "old_price", "days": age})
    if (
        line.kind == "product"
        and line.cost_usd is not None
        and product.current_price_usd is not None
        and product.current_price_usd != line.cost_usd
    ):
        warnings.append(
            {
                "code": "price_changed",
                "now": str(product.current_price_usd),
                "was": str(line.cost_usd),
            }
        )
    return warnings
