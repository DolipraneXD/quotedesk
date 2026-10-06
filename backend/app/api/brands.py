from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import SessionDep
from app.errors import ProblemError
from app.models import Brand, BrandAlias, Product
from app.schemas.catalog import AliasCreate, BrandCreate, BrandOut, BrandUpdate
from app.services.brands import add_alias
from app.services.importer.normalize import brand_key

router = APIRouter(prefix="/brands", tags=["brands"])


def _out(session: SessionDep, brand: Brand) -> BrandOut:
    out = BrandOut.model_validate(brand)
    out.product_count = (
        session.scalar(select(func.count()).where(Product.brand_id == brand.id)) or 0
    )
    return out


def _get(session: SessionDep, brand_id: int) -> Brand:
    brand = session.get(Brand, brand_id)
    if brand is None:
        raise ProblemError(404, "brand.not_found", "Brand not found", id=brand_id)
    return brand


def _check_alias_free(session: SessionDep, alias: str, brand_id: int | None = None) -> None:
    existing = session.scalar(select(BrandAlias).where(BrandAlias.alias_key == brand_key(alias)))
    if existing is not None and existing.brand_id != brand_id:
        raise ProblemError(
            409,
            "brand.alias_taken",
            "Alias already belongs to another brand",
            alias=alias,
            brand=existing.brand.canonical,
        )


@router.get("", response_model=list[BrandOut])
def list_brands(session: SessionDep) -> list[BrandOut]:
    rows = session.execute(
        select(Product.brand_id, func.count())
        .where(Product.brand_id.is_not(None))
        .group_by(Product.brand_id)
    )
    counts = {bid: n for bid, n in rows}
    brands = session.scalars(
        select(Brand).options(selectinload(Brand.aliases)).order_by(func.lower(Brand.canonical))
    )
    result = []
    for brand in brands:
        out = BrandOut.model_validate(brand)
        out.product_count = counts.get(brand.id, 0)
        result.append(out)
    return result


@router.post("", response_model=BrandOut, status_code=201)
def create_brand(session: SessionDep, body: BrandCreate) -> BrandOut:
    canonical = body.canonical.strip()
    if session.scalar(select(Brand).where(func.lower(Brand.canonical) == canonical.lower())):
        raise ProblemError(409, "brand.duplicate", "Brand exists", canonical=canonical)
    for name in {canonical, body.name_zh or "", body.name_en or ""} - {""}:
        _check_alias_free(session, name)
    brand = Brand(canonical=canonical, name_en=body.name_en or canonical, name_zh=body.name_zh)
    session.add(brand)
    add_alias(session, brand, canonical, "en")
    if body.name_zh and brand_key(body.name_zh) != brand_key(canonical):
        add_alias(session, brand, body.name_zh, "zh")
    session.commit()
    return _out(session, brand)


@router.patch("/{brand_id}", response_model=BrandOut)
def update_brand(session: SessionDep, brand_id: int, body: BrandUpdate) -> BrandOut:
    brand = _get(session, brand_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(brand, key, value)
    session.commit()
    return _out(session, brand)


@router.delete("/{brand_id}", status_code=204)
def delete_brand(session: SessionDep, brand_id: int) -> Response:
    brand = _get(session, brand_id)
    if session.scalar(select(func.count()).where(Product.brand_id == brand.id)):
        raise ProblemError(409, "brand.in_use", "Brand is used by products")
    session.delete(brand)
    session.commit()
    return Response(status_code=204)


@router.post("/{brand_id}/aliases", response_model=BrandOut, status_code=201)
def create_alias(session: SessionDep, brand_id: int, body: AliasCreate) -> BrandOut:
    brand = _get(session, brand_id)
    _check_alias_free(session, body.alias, brand.id)
    if not any(a.alias_key == brand_key(body.alias) for a in brand.aliases):
        add_alias(session, brand, body.alias, body.lang)
    session.commit()
    session.refresh(brand)
    return _out(session, brand)


@router.delete("/{brand_id}/aliases/{alias_id}", response_model=BrandOut)
def delete_alias(session: SessionDep, brand_id: int, alias_id: int) -> BrandOut:
    brand = _get(session, brand_id)
    alias = session.get(BrandAlias, alias_id)
    if alias is None or alias.brand_id != brand.id:
        raise ProblemError(404, "brand.alias_not_found", "Alias not found", id=alias_id)
    session.delete(alias)
    session.commit()
    session.refresh(brand)
    return _out(session, brand)
