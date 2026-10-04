"""Saved configurations (plan §3.10, §6): CRUD, photos, where used, save from a quote."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import SessionDep
from app.api.quotes import get_quote
from app.models import Configuration, QuoteLine
from app.schemas.quotes import (
    ConfigurationCreate,
    ConfigurationItemOut,
    ConfigurationOut,
    ConfigurationPatch,
    ConfigurationSummary,
    ConfigurationUsage,
    DescriptionLine,
    SaveLineAsConfiguration,
)
from app.services import configurations as svc
from app.services import images
from app.services import quotes as quote_svc

router = APIRouter(prefix="/configurations", tags=["configurations"])


def _usage_counts(session: Session, ids: list[int] | None = None) -> dict[int, int]:
    query = select(QuoteLine.configuration_id, func.count()).where(
        QuoteLine.configuration_id.is_not(None)
    )
    if ids is not None:
        query = query.where(QuoteLine.configuration_id.in_(ids))
    rows = session.execute(query.group_by(QuoteLine.configuration_id))
    return {config_id: n for config_id, n in rows if config_id is not None}


def serialize(session: Session, config: Configuration) -> ConfigurationOut:
    parts = svc.components(config)
    return ConfigurationOut(
        id=config.id,
        name=config.name,
        name_zh=config.name_zh,
        notes=config.notes,
        platform=config.platform,
        model_no=config.model_no,
        material=config.material,
        base_margin_pct=config.base_margin_pct,
        image_ids=list(config.image_ids or []),
        items=[
            ConfigurationItemOut(
                id=item.id,
                product_id=item.product_id,
                name=item.name,
                qty=item.qty,
                condition=item.condition,
                emphasis=item.emphasis,
                cost_usd=item.cost_usd,
                unit_cost=svc.item_cost(item),
                product_name=item.product.name_zh if item.product else None,
                product_status=item.product.status if item.product else None,
                price_date=item.product.price_date if item.product else None,
            )
            for item in config.items
        ],
        description_lines=[
            DescriptionLine(**d) for d in quote_svc.describe_components(parts, "en")
        ],
        unit_cost=svc.unit_cost(config),
        saved_cost=config.saved_cost,
        cost_changed=svc.cost_changed(config),
        missing_cost=svc.missing_cost(config),
        used_in=_usage_counts(session, [config.id]).get(config.id, 0),
        updated_at=config.updated_at,
    )


def _done(session: Session, config: Configuration) -> ConfigurationOut:
    session.commit()
    session.expire_all()
    return serialize(session, svc.get(session, config.id))


@router.get("", response_model=list[ConfigurationSummary])
def list_configurations(session: SessionDep, q: str | None = None) -> list[ConfigurationSummary]:
    query = select(Configuration).order_by(Configuration.name)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Configuration.name.ilike(like),
                Configuration.name_zh.ilike(like),
                Configuration.model_no.ilike(like),
                Configuration.platform.ilike(like),
            )
        )
    configs = list(session.scalars(query))
    used = _usage_counts(session)
    return [
        ConfigurationSummary(
            id=c.id,
            name=c.name,
            name_zh=c.name_zh,
            platform=c.platform,
            model_no=c.model_no,
            parts=len(c.items),
            unit_cost=svc.unit_cost(c),
            saved_cost=c.saved_cost,
            cost_changed=svc.cost_changed(c),
            missing_cost=svc.missing_cost(c),
            used_in=used.get(c.id, 0),
            image_id=c.image_ids[0] if c.image_ids else None,
            updated_at=c.updated_at,
        )
        for c in configs
    ]


@router.post("", response_model=ConfigurationOut, status_code=201)
def create_configuration(session: SessionDep, body: ConfigurationCreate) -> ConfigurationOut:
    data = body.model_dump()
    data["items"] = [item.model_dump() for item in body.items or []]
    return _done(session, svc.create(session, data))


@router.post("/from-line", response_model=ConfigurationOut, status_code=201)
def save_line(session: SessionDep, body: SaveLineAsConfiguration) -> ConfigurationOut:
    """Keep a combined product built in a quote for later quotes."""
    quote = get_quote(session, body.quote_id)
    line = quote_svc.get_line(quote, body.line_id)
    return _done(session, svc.from_line(session, quote, line, body.name))


@router.get("/{config_id}", response_model=ConfigurationOut)
def get_configuration(session: SessionDep, config_id: int) -> ConfigurationOut:
    return serialize(session, svc.get(session, config_id))


@router.patch("/{config_id}", response_model=ConfigurationOut)
def update_configuration(
    session: SessionDep, config_id: int, body: ConfigurationPatch
) -> ConfigurationOut:
    data = body.model_dump(exclude_unset=True)
    if body.items is not None:
        data["items"] = [item.model_dump() for item in body.items]
    return _done(session, svc.update(session, svc.get(session, config_id), data))


@router.delete("/{config_id}", status_code=204)
def delete_configuration(session: SessionDep, config_id: int) -> Response:
    """Quotes keep their combined lines: they are snapshots."""
    session.delete(svc.get(session, config_id))
    session.commit()
    return Response(status_code=204)


@router.post("/{config_id}/duplicate", response_model=ConfigurationOut, status_code=201)
def duplicate_configuration(session: SessionDep, config_id: int) -> ConfigurationOut:
    return _done(session, svc.duplicate(session, svc.get(session, config_id), "(copy)"))


@router.get("/{config_id}/usage", response_model=list[ConfigurationUsage])
def configuration_usage(session: SessionDep, config_id: int) -> list[ConfigurationUsage]:
    svc.get(session, config_id)
    return [
        ConfigurationUsage(
            quote_id=quote.id,
            display_no=quote.display_no,
            status=quote.status,
            offer_date=quote.offer_date,
            customer_name=(quote.customer_snapshot or {}).get("name"),
            line_id=line.id,
            qty=line.qty,
            unit_price=line.unit_price,
        )
        for line, quote in svc.usage(session, config_id)
    ]


@router.post("/{config_id}/images", response_model=ConfigurationOut, status_code=201)
async def add_images(
    session: SessionDep, config_id: int, files: Annotated[list[UploadFile], File()]
) -> ConfigurationOut:
    config = svc.get(session, config_id)
    added = [images.save_image(session, f.filename, await f.read()).id for f in files]
    config.image_ids = [*(config.image_ids or []), *added]
    return _done(session, config)


@router.delete("/{config_id}/images/{image_id}", response_model=ConfigurationOut)
def remove_image(session: SessionDep, config_id: int, image_id: int) -> ConfigurationOut:
    """Unlinks the photo; the file stays for quotes that print it."""
    config = svc.get(session, config_id)
    config.image_ids = [i for i in config.image_ids or [] if i != image_id]
    return _done(session, config)
