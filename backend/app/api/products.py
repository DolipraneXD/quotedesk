from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query, Response
from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import joinedload

from app.api.deps import SessionDep
from app.errors import ProblemError
from app.models import PriceHistory, Product, ProductAlias
from app.schemas.catalog import (
    MergeRequest,
    PriceCreate,
    PriceOut,
    ProductAliasOut,
    ProductCreate,
    ProductList,
    ProductOut,
    ProductUpdate,
)
from app.services import catalog, search

router = APIRouter(prefix="/products", tags=["products"])

SORT_KEYS: dict[str, Any] = {
    "name": Product.name_zh,
    "updated": Product.updated_at,
    "created": Product.created_at,
    "price_date": Product.price_date,
    # Prices are stored as text; the cast is for ordering only, never for arithmetic.
    "price": cast(Product.current_price_usd, Float),
}


PRODUCT_LOADS = [
    joinedload(Product.brand),
    joinedload(Product.created_import),
    joinedload(Product.last_import),
]


def _get(session: SessionDep, product_id: int) -> Product:
    product = session.get(Product, product_id, options=PRODUCT_LOADS)
    if product is None:
        raise ProblemError(404, "product.not_found", "Product not found", id=product_id)
    return product


@router.get("", response_model=ProductList)
def list_products(
    session: SessionDep,
    q: str | None = None,
    category: int | None = None,
    brand: int | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    sort: Literal["name", "price", "updated", "created", "price_date"] = "name",
    order: Literal["asc", "desc"] = "asc",
) -> ProductList:
    stmt = select(Product)
    if q and q.strip():
        hits = search.matching_ids_query(q.strip())
        if hits is not None:
            stmt = stmt.where(Product.id.in_(hits))
    if category is not None:
        stmt = stmt.where(Product.category_id == category)
    if brand is not None:
        stmt = stmt.where(Product.brand_id == brand)
    if status:
        stmt = stmt.where(Product.status == status)

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    key = SORT_KEYS[sort]
    ordering = key.desc() if order == "desc" else key.asc()
    items = session.scalars(
        stmt.options(*PRODUCT_LOADS)
        .order_by(ordering.nulls_last(), Product.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ProductList(
        items=[ProductOut.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ProductOut, status_code=201)
def create_product(session: SessionDep, body: ProductCreate) -> Product:
    product = catalog.create_product(session, body.model_dump())
    session.commit()
    return product


@router.get("/{product_id}", response_model=ProductOut)
def get_product(session: SessionDep, product_id: int) -> Product:
    return _get(session, product_id)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(session: SessionDep, product_id: int, body: ProductUpdate) -> Product:
    product = catalog.update_product(
        session, _get(session, product_id), body.model_dump(exclude_unset=True)
    )
    session.commit()
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product(session: SessionDep, product_id: int) -> Response:
    catalog.delete_product(session, _get(session, product_id))
    session.commit()
    return Response(status_code=204)


@router.get("/{product_id}/prices", response_model=list[PriceOut])
def list_prices(session: SessionDep, product_id: int) -> list[PriceHistory]:
    _get(session, product_id)
    return list(
        session.scalars(
            select(PriceHistory)
            .where(PriceHistory.product_id == product_id)
            .order_by(PriceHistory.created_at.desc(), PriceHistory.id.desc())
        )
    )


@router.post("/{product_id}/prices", response_model=ProductOut, status_code=201)
def add_price(session: SessionDep, product_id: int, body: PriceCreate) -> Product:
    """Manual price edit: recorded in price history with no import attached."""
    product = _get(session, product_id)
    catalog.set_price(
        session,
        product,
        body.price_usd,
        tier=body.tier,
        price_date=body.price_date,
        note=body.note,
        source_ref="manual",
    )
    session.commit()
    return product


@router.get("/{product_id}/aliases", response_model=list[ProductAliasOut])
def list_aliases(session: SessionDep, product_id: int) -> list[ProductAlias]:
    _get(session, product_id)
    return list(session.scalars(select(ProductAlias).where(ProductAlias.product_id == product_id)))


@router.post("/{product_id}/merge", response_model=ProductOut)
def merge_product(session: SessionDep, product_id: int, body: MergeRequest) -> Product:
    """Merge this product into ``into_id``; this one is deleted."""
    drop = _get(session, product_id)
    keep = _get(session, body.into_id)
    product = catalog.merge_products(session, keep, drop)
    session.commit()
    return product
