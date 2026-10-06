"""Complete units imported with their parts (整机成本 BOM sheets, DECISIONS D80).

The model returns the unit (a tablet) as one row whose ``parts`` list holds every part
column. Two things happen here:

* ``expand_parts`` (pure, before analysis): each priced part becomes its own row, in RMB,
  sharing ``assembly`` = the unit's model. The parts take the unit's own RMB / USD ratio as
  their rate (the unit's USD price usually excludes VAT), so they add up to its USD price.
  A generic part (整套, 组装费) gets the unit's model in its name so it never merges with
  another unit's.
* ``link_configurations`` (at commit): one configuration per unit, named after it, holding
  the part products, so the unit can be quoted as a combined product. ``unlink`` undoes it.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Configuration, ImportRow, Product
from app.models.catalog import DEVICE_TYPES
from app.services import configurations

RATE_QUANT = Decimal("0.000001")


def _decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except ArithmeticError:
        return None
    return number if number.is_finite() and number > 0 else None


def _merge_unit_prices(unit: dict[str, Any]) -> None:
    """A unit's RMB cost and USD price sometimes come back as two prices of one tier:
    keep the USD one, with the RMB amount as its original."""
    prices = unit.get("prices") or []
    for usd in prices:
        if usd.get("currency") != "USD" or usd.get("original_currency") == "CNY":
            continue
        rmb = next(
            (p for p in prices if p.get("currency") == "CNY" and p.get("tier") == usd.get("tier")),
            None,
        )
        if rmb is not None:
            usd["original_amount"], usd["original_currency"] = rmb.get("amount"), "CNY"
            usd["fx_rate"] = usd.get("fx_rate") or rmb.get("fx_rate")
            usd["date"] = usd.get("date") or rmb.get("date")
            prices.remove(rmb)


def _unit_rate(unit: dict[str, Any]) -> Decimal | None:
    """RMB per USD implied by the unit's own prices (its USD column next to its RMB cost)."""
    for price in unit.get("prices") or []:
        if price.get("currency") != "USD" or price.get("original_currency") != "CNY":
            continue
        usd, rmb = _decimal(price.get("amount")), _decimal(price.get("original_amount"))
        if usd and rmb:
            return (rmb / usd).quantize(RATE_QUANT)
    return None


def _unit_rmb(unit: dict[str, Any]) -> Decimal | None:
    for price in unit.get("prices") or []:
        if price.get("currency") == "CNY":
            return _decimal(price.get("amount"))
        if price.get("original_currency") == "CNY":
            return _decimal(price.get("original_amount"))
    return None


def _check_total(unit: dict[str, Any], parts: list[dict[str, Any]]) -> None:
    """The parts of a BOM add up to the unit's cost; a gap means a misread amount."""
    cost = _unit_rmb(unit)
    total = sum((a for p in parts if (a := _decimal(p.get("amount")))), Decimal("0"))
    if cost is not None and abs(total - cost) > Decimal("0.01"):
        unit["parts_total"] = {"parts": str(total), "unit": str(cost)}


def _model(unit: dict[str, Any]) -> str:
    attrs = {a.get("key"): a.get("value") for a in unit.get("attributes") or []}
    return str(attrs.get("model") or unit.get("name_zh") or "").strip()


def expand_parts(row: dict[str, Any]) -> list[dict[str, Any]]:
    """The row itself, plus one row per priced part when it is a complete unit."""
    parts = row.get("parts") or []
    key = _model(row)
    if not parts or not key:
        return [row]
    _merge_unit_prices(row)
    row["assembly"], row["assembly_role"] = key, "unit"
    # a tablet's parts are tablet parts: the picker of a PC build hides them
    device = row.get("category_code") if row.get("category_code") in DEVICE_TYPES else None
    if device:
        row["device_type"] = device
    rate = _unit_rate(row)
    fallback = next((p.get("fx_rate") for p in row.get("prices") or [] if p.get("fx_rate")), None)
    date = next((p.get("date") for p in row.get("prices") or [] if p.get("date")), None)
    out = [row]
    _check_total(row, parts)
    for part in parts:
        amount = _decimal(part.get("amount"))
        if amount is None:
            continue  # "/" or 0: the unit has no such part
        label, spec = (part.get("label") or "").strip(), (part.get("spec") or "").strip()
        name = " ".join(t for t in (label, spec) if t and t not in ("/", "-"))
        if part.get("generic"):
            name = f"{name} ({key})"
        price = {
            "tier": "standard", "amount": amount, "currency": "CNY", "column": "",
            "date": date, "original_amount": None, "original_currency": None,
            "fx_rate": rate or fallback,
        }  # fmt: skip
        out.append(
            {
                **{
                    k: copy.deepcopy(v) for k, v in row.items() if k in ("source_row", "confidence")
                },
                "category_code": part.get("category_code") or "other",
                "name_zh": name,
                "name_en": None,
                "brand": None,
                "erp_codes": [],
                "mpn": None,
                "attributes": [{"key": "spec_text", "value": spec}] if spec else [],
                "prices": [price],
                "no_price_reason": None,
                "stock_qty": None,
                "demand_qty": None,
                "stock_after_qty": None,
                "notes_raw": None,
                "platform": row.get("platform"),
                "parts": [],
                "issues": [],
                "assembly": key,
                "assembly_role": "part",
                **({"device_type": device} if device else {}),
                **({"unit_fx_rate": str(rate)} if rate else {}),
            }
        )
    return out


# ------------------------------------------------------------------ commit


def _product_id(row: ImportRow) -> int | None:
    if row.commit_info:
        return row.commit_info.get("product_id")
    if row.status == "unchanged":  # already in the catalog at this price
        return row.matched_product_id
    return None


def link_configurations(session: Session, rows: list[ImportRow]) -> list[dict[str, Any]]:
    """Create or refresh one configuration per committed unit; returns what revert needs."""
    units: dict[str, ImportRow] = {}
    parts: dict[str, list[ImportRow]] = {}
    for row in rows:
        staged = row.parsed.get("staged") or {}
        key, role = staged.get("assembly"), staged.get("assembly_role")
        if not key or _product_id(row) is None:
            continue
        if role == "unit":
            units.setdefault(key, row)
        elif role == "part":
            parts.setdefault(key, []).append(row)

    changes: list[dict[str, Any]] = []
    for key, unit_row in units.items():
        part_ids = list(dict.fromkeys(pid for r in parts.get(key, []) if (pid := _product_id(r))))
        if not part_ids:
            continue
        unit = session.get(Product, _product_id(unit_row))
        if unit is None:
            continue
        items = [{"product_id": pid, "qty": 1} for pid in part_ids]
        existing = session.scalar(
            select(Configuration).where(Configuration.model_no == key).order_by(Configuration.id)
        )
        if existing is not None:
            before = [
                {"product_id": i.product_id, "name": i.name, "cost_usd": i.cost_usd, "qty": i.qty,
                 "condition": i.condition, "emphasis": i.emphasis}
                for i in existing.items
            ]  # fmt: skip
            configurations.update(session, existing, {"items": items})
            changes.append({"id": existing.id, "created": False, "before_items": before})
        else:
            config = configurations.create(
                session,
                {
                    "name": unit.name_en or unit.name_zh,
                    "name_zh": unit.name_zh,
                    "model_no": key,
                    "platform": unit.platform,
                    "device_type": unit.device_type,
                    "items": items,
                },
            )
            changes.append({"id": config.id, "created": True})
    return [_jsonable(c) for c in changes]


def unlink_configurations(session: Session, changes: list[dict[str, Any]]) -> None:
    for change in reversed(changes):
        config = session.get(Configuration, change.get("id"))
        if config is None:
            continue
        if change.get("created"):
            session.delete(config)
        else:
            items = [
                {**item, "product_id": item["product_id"]
                 if item.get("product_id") and session.get(Product, item["product_id"])
                 else None}
                for item in change.get("before_items") or []
            ]  # fmt: skip
            configurations.update(session, config, {"items": items})
    session.flush()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value
