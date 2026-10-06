"""Dashboard widgets (plan §6): last import, open quotes, big price moves, quote alerts,
old prices. Read-only; every number is computed on request."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import AppSettings
from app.models import Import, PriceHistory, Product, Quote
from app.services import quotes

OPEN = ("draft", "sent")
BIG_MOVE = Decimal("20")  # percent
ALERTS = ("price_changed", "status", "product_deleted")
LIMIT = 50


def last_import(session: Session) -> dict[str, Any] | None:
    imp = session.scalars(
        select(Import)
        .where(Import.committed_at.is_not(None))
        .order_by(Import.committed_at.desc(), Import.id.desc())
        .limit(1)
    ).first()
    if imp is None:
        return None
    stats = imp.stats or {}
    return {
        "id": imp.id,
        "filename": imp.filename,
        "committed_at": imp.committed_at,
        "new": stats.get("new", 0),
        "updated": stats.get("updated", 0),
        "unchanged": stats.get("unchanged", 0),
    }


def price_moves(session: Session, import_id: int) -> list[dict[str, Any]]:
    """Prices the import changed by more than 20 %, against each product's price before."""
    rows = session.scalars(select(PriceHistory).where(PriceHistory.import_id == import_id)).all()
    moves: list[dict[str, Any]] = []
    for row in rows:
        before = session.scalars(
            select(PriceHistory)
            .where(
                PriceHistory.product_id == row.product_id,
                PriceHistory.tier == row.tier,
                PriceHistory.id < row.id,
            )
            .order_by(PriceHistory.id.desc())
            .limit(1)
        ).first()
        if before is None or not before.price_usd:
            continue
        old, new = Decimal(before.price_usd), Decimal(row.price_usd)
        pct = (new - old) / old * 100
        if abs(pct) > BIG_MOVE:
            moves.append({"product_id": row.product_id, "old": old, "new": new,
                          "pct": quotes.round_money(pct, 1)})  # fmt: skip
    names = _names(session, [m["product_id"] for m in moves])
    for move in moves:
        move["name"] = names.get(move["product_id"])
    moves.sort(key=lambda m: -abs(m["pct"]))
    return moves[:LIMIT]


def _names(session: Session, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = session.execute(select(Product.id, Product.name_zh).where(Product.id.in_(ids)))
    return {pid: name for pid, name in rows}


def open_quotes(session: Session) -> list[Quote]:
    return list(
        session.scalars(
            select(Quote).where(Quote.status.in_(OPEN)).order_by(Quote.updated_at.desc())
        )
    )


def quote_alerts(
    session: Session, quotes_open: list[Quote], settings: AppSettings
) -> list[dict[str, Any]]:
    """Lines of open quotes whose product changed price or stopped being sold since."""
    ids = {
        pid
        for q in quotes_open
        for s in q.sections
        for line in s.lines
        for pid in [line.product_id, *(c.get("product_id") for c in line.components or [])]
        if pid
    }
    products = (
        {p.id: p for p in session.scalars(select(Product).where(Product.id.in_(ids)))}
        if ids
        else {}
    )
    alerts = []
    for quote in quotes_open:
        for section in quote.sections:
            for line in section.lines:
                product = products.get(line.product_id) if line.product_id else None
                warnings = quotes.line_warnings(line, product, settings)
                warnings += quotes.component_warnings(line, products, settings)
                for warning in warnings:
                    if warning["code"] in ALERTS:
                        alerts.append({
                            "quote_id": quote.id,
                            "display_no": quote.display_no,
                            "customer_name": (quote.customer_snapshot or {}).get("name"),
                            "line": line.name,
                            **warning,
                        })  # fmt: skip
    return alerts[:LIMIT]


def old_prices(session: Session, settings: AppSettings) -> dict[str, Any]:
    cutoff = quotes.today() - timedelta(days=settings.price_age_warning_days)
    old = (
        select(Product)
        .where(Product.price_date.is_not(None), Product.price_date < cutoff)
        .where(Product.status == "active")
    )
    count = session.scalar(select(func.count()).select_from(old.subquery())) or 0
    oldest = session.scalars(old.order_by(Product.price_date).limit(10))
    return {
        "days": settings.price_age_warning_days,
        "count": count,
        "oldest": [
            {"product_id": p.id, "name": p.name_zh, "price_date": p.price_date} for p in oldest
        ],
    }


def widgets(session: Session, settings: AppSettings) -> dict[str, Any]:
    imp = last_import(session)
    quotes_open = open_quotes(session)
    return {
        "last_import": imp,
        "price_moves": price_moves(session, imp["id"]) if imp else [],
        "open_quotes": {
            "count": len(quotes_open),
            "value": sum((Decimal(q.grand_total) for q in quotes_open), Decimal("0")),
            "recent": [
                {
                    "id": q.id,
                    "display_no": q.display_no,
                    "status": q.status,
                    "customer_name": (q.customer_snapshot or {}).get("name"),
                    "grand_total": q.grand_total,
                    "updated_at": q.updated_at,
                }
                for q in quotes_open[:8]
            ],
        },
        "quote_alerts": quote_alerts(session, quotes_open, settings),
        "old_prices": old_prices(session, settings),
    }
