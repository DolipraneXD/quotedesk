"""Saved builds (plan §3.10): a list of parts that quotes insert as one combined product.

A catalog part always takes the product's current price, so the cost of a configuration
moves with the catalog; ``saved_cost`` remembers it at the last save to show the change.
A part typed by hand keeps its own cost. Each part is also one printed description line.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ProblemError
from app.models import (
    Configuration,
    ConfigurationItem,
    Product,
    Quote,
    QuoteLine,
    QuoteSection,
)
from app.services import quotes

FIELDS = ("name", "name_zh", "notes", "platform", "model_no", "material", "base_margin_pct",
          "image_ids")  # fmt: skip


def get(session: Session, config_id: int) -> Configuration:
    config = session.get(Configuration, config_id)
    if config is None:
        raise ProblemError(404, "configuration.not_found", "Configuration not found", id=config_id)
    return config


# ------------------------------------------------------------------- cost


def item_cost(item: ConfigurationItem) -> Decimal | None:
    if item.product_id is not None:
        return item.product.current_price_usd if item.product else None
    return item.cost_usd


def unit_cost(config: Configuration) -> Decimal | None:
    """Σ qty × cost over the parts that have a cost; None when none has."""
    costs = [(item.qty, item_cost(item)) for item in config.items]
    known = [qty * Decimal(cost) for qty, cost in costs if cost is not None]
    return sum(known, Decimal("0")) if known else None


def missing_cost(config: Configuration) -> int:
    return sum(1 for item in config.items if item_cost(item) is None)


def cost_changed(config: Configuration) -> bool:
    current = unit_cost(config)
    saved = config.saved_cost
    if current is None or saved is None:
        return current != saved
    return Decimal(current) != Decimal(saved)


def components(config: Configuration) -> list[dict[str, Any]]:
    """The parts as a quote line stores them: a snapshot at today's prices."""
    result = []
    for item in config.items:
        product = item.product if item.product_id is not None else None
        cost = item_cost(item)
        result.append(
            {
                "product_id": item.product_id,
                "name": item.name,
                "qty": item.qty,
                "cost_usd": None if cost is None else str(cost),
                "condition": item.condition,
                "emphasis": item.emphasis,
                "price_date": product.price_date.isoformat()
                if product is not None and product.price_date
                else None,
            }
        )
    return result


# ----------------------------------------------------------------- writes


def _items(session: Session, data: list[dict[str, Any]]) -> list[ConfigurationItem]:
    items = []
    for position, entry in enumerate(data):
        product_id = entry.get("product_id")
        name = (entry.get("name") or "").strip()
        if product_id is not None:
            product = session.get(Product, product_id)
            if product is None:
                raise ProblemError(404, "product.not_found", "Product not found", id=product_id)
            name = name or product.name_en or product.name_zh
        if not name:
            raise ProblemError(422, "configuration.part_name_required", "A part needs a name")
        if entry.get("condition") not in (None, "new", "used"):
            raise ProblemError(422, "configuration.bad_condition", "Condition is new or used")
        items.append(
            ConfigurationItem(
                product_id=product_id,
                name=name,
                # a catalog part is priced from the catalog, never from a stored cost
                cost_usd=None if product_id is not None else entry.get("cost_usd"),
                qty=int(entry.get("qty") or 1),
                condition=entry.get("condition"),
                emphasis=bool(entry.get("emphasis")),
                sort_order=position,
            )
        )
    return items


def _save(session: Session, config: Configuration) -> Configuration:
    session.flush()
    session.expire(config, ["items"])  # products of new parts load with them
    config.saved_cost = unit_cost(config)
    session.flush()
    return config


def create(session: Session, data: dict[str, Any]) -> Configuration:
    config = Configuration(**{key: data.get(key) for key in FIELDS if key != "image_ids"})
    config.image_ids = list(data.get("image_ids") or [])
    config.items = _items(session, data.get("items") or [])
    session.add(config)
    return _save(session, config)


def update(session: Session, config: Configuration, data: dict[str, Any]) -> Configuration:
    """Every save also accepts the current cost as the new ``saved_cost``."""
    for key in FIELDS:
        if key in data:
            setattr(config, key, data[key])
    if not (config.name or "").strip():
        raise ProblemError(422, "configuration.name_required", "A configuration needs a name")
    if data.get("items") is not None:
        config.items = _items(session, data["items"])
    return _save(session, config)


def duplicate(session: Session, source: Configuration, suffix: str) -> Configuration:
    copy = Configuration(**{key: getattr(source, key) for key in FIELDS})
    copy.name = f"{source.name} {suffix}"
    copy.image_ids = list(source.image_ids or [])
    copy.items = [
        ConfigurationItem(
            product_id=item.product_id, name=item.name, cost_usd=item.cost_usd, qty=item.qty,
            condition=item.condition, emphasis=item.emphasis, sort_order=item.sort_order,
        )
        for item in source.items
    ]  # fmt: skip
    session.add(copy)
    return _save(session, copy)


def from_line(session: Session, quote: Quote, line: QuoteLine, name: str | None) -> Configuration:
    """Save a combined product of a quote for reuse. The parts keep their links to the
    catalog, so the saved build prices from the catalog from now on."""
    if line.kind != "config":
        raise ProblemError(409, "quote.not_combined", "This line is not a combined product")
    zh = quote.language == "zh"
    config = create(
        session,
        {
            "name": name or line.name,
            "name_zh": line.name if zh else None,
            "model_no": line.model_no,
            "material": line.material,
            "base_margin_pct": line.margin_pct,
            "image_ids": list(line.image_ids or []),
            "items": [
                {**c, "product_id": c.get("product_id") if _exists(session, c) else None}
                for c in line.components or []
            ],
        },
    )
    line.configuration_id = config.id
    return config


def _exists(session: Session, component: dict[str, Any]) -> bool:
    product_id = component.get("product_id")
    return product_id is not None and session.get(Product, product_id) is not None


# ------------------------------------------------------------------ quotes


def insert_into_quote(
    session: Session, quote: Quote, section: QuoteSection, config: Configuration, qty: int
) -> QuoteLine:
    """One combined line at today's prices; the margin is the build's own if it has one."""
    name = config.name_zh if quote.language == "zh" and config.name_zh else config.name
    parts = components(config)
    line = QuoteLine(
        kind="config",
        configuration_id=config.id,
        name=name,
        model_no=config.model_no,
        material=config.material,
        qty=qty,
        components=parts,
        description_lines=quotes.describe_components(parts, quote.language),
        image_ids=list(config.image_ids or []),
        margin_pct=config.base_margin_pct,
        sort_order=max((line.sort_order for line in section.lines), default=-1) + 1,
    )
    section.lines.append(line)
    quotes.recalculate(session, quote)
    session.flush()
    return line


def usage(session: Session, config_id: int) -> list[tuple[QuoteLine, Quote]]:
    rows = session.execute(
        select(QuoteLine, Quote)
        .join(QuoteSection, QuoteLine.section_id == QuoteSection.id)
        .join(Quote, QuoteSection.quote_id == Quote.id)
        .where(QuoteLine.configuration_id == config_id)
        .order_by(Quote.offer_date.desc(), Quote.id.desc())
    )
    return [(line, quote) for line, quote in rows]
