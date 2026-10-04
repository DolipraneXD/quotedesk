"""Small read-only endpoints: health and the dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from app import __version__
from app.api.deps import SessionDep
from app.config import load_settings
from app.models import Brand, Category, Product
from app.services.dashboard import widgets as dashboard_widgets

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/dashboard")
def dashboard(session: SessionDep) -> dict[str, Any]:
    rows = session.execute(select(Product.status, func.count()).group_by(Product.status))
    by_status = {status: n for status, n in rows}
    by_category = [
        {"category_id": cid, "count": n}
        for cid, n in session.execute(
            select(Product.category_id, func.count()).group_by(Product.category_id)
        )
    ]
    return {
        "products": sum(by_status.values()),
        "products_by_status": by_status,
        "products_by_category": by_category,
        "products_without_price": session.scalar(
            select(func.count()).where(Product.current_price_usd.is_(None))
        ),
        "categories": session.scalar(select(func.count()).select_from(Category)),
        "brands": session.scalar(select(func.count()).select_from(Brand)),
        **dashboard_widgets(session, load_settings()),
    }
