from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import SessionDep
from app.config import AppSettings, load_settings
from app.errors import ProblemError
from app.models import (
    Category,
    Image,
    Product,
    ProformaInvoice,
    Quote,
    QuoteLine,
    QuoteSection,
)
from app.schemas.quotes import (
    CombineIn,
    Component,
    DescriptionLine,
    LineCreate,
    LineOut,
    LinePatch,
    ProformaCreate,
    ProformaOut,
    QuoteCreate,
    QuoteList,
    QuoteOut,
    QuotePatch,
    QuoteSummary,
    ReorderIn,
    SectionIn,
    SectionOut,
)
from app.services import configurations, images, proformas
from app.services import quotes as svc
from app.services.documents.internal import costing_workbook, render_costing
from app.services.documents.quote_pdf import render_quote
from app.services.documents.xlsx import quote_workbook

router = APIRouter(prefix="/quotes", tags=["quotes"])

QUOTE_LOADS = [
    selectinload(Quote.sections).selectinload(QuoteSection.lines),
    selectinload(Quote.customer),
]


def get_quote(session: Session, quote_id: int) -> Quote:
    quote = session.get(Quote, quote_id, options=QUOTE_LOADS)
    if quote is None:
        raise ProblemError(404, "quote.not_found", "Quote not found", id=quote_id)
    return quote


def _editable(quote: Quote) -> None:
    if quote.status != "draft":
        raise ProblemError(
            409, "quote.locked", "Only a draft can change; make a new revision instead",
            status=quote.status,
        )  # fmt: skip


def image_resolver(session: Session) -> Any:
    def resolve(image_id: int) -> Path | None:
        image = session.get(Image, image_id)
        if image is None or not images.original_path(image).exists():
            return None
        return images.document_path(image)

    return resolve


# ---------------------------------------------------------- serialization


def serialize(session: Session, quote: Quote) -> QuoteOut:
    settings = load_settings()
    product_ids = {line.product_id for s in quote.sections for line in s.lines if line.product_id}
    product_ids |= {
        c["product_id"]
        for s in quote.sections
        for line in s.lines
        for c in line.components or []
        if c.get("product_id")
    }
    products = (
        {p.id: p for p in session.scalars(select(Product).where(Product.id.in_(product_ids)))}
        if product_ids
        else {}
    )
    categories = {c.id: c for c in session.scalars(select(Category))}
    sections = []
    for section in quote.sections:
        lines = []
        for number, line in zip(svc.printed_numbers(section), section.lines, strict=True):
            category = categories.get(line.category_id) if line.category_id else None
            margin = svc.resolve_margin(line, quote.customer, category, settings)
            lines.append(_line_out(line, number, margin, products, settings))
        sections.append(
            SectionOut(
                id=section.id,
                title=section.title,
                layout=section.layout,
                sort_order=section.sort_order,
                subtotal=section.subtotal,
                lines=lines,
            )
        )
    revisions = [
        {"id": q.id, "revision": q.revision, "status": q.status, "display_no": q.display_no}
        for q in session.scalars(
            select(Quote).where(Quote.offer_no == quote.offer_no).order_by(Quote.revision)
        )
    ]
    pis = [
        {"id": pi.id, "pi_no": pi.pi_no, "status": pi.status, "total": str(pi.total)}
        for pi in session.scalars(
            select(ProformaInvoice).where(ProformaInvoice.quote_id == quote.id)
            .order_by(ProformaInvoice.id)
        )
    ]  # fmt: skip
    return QuoteOut(
        id=quote.id,
        offer_no=quote.offer_no,
        revision=quote.revision,
        display_no=quote.display_no,
        parent_quote_id=quote.parent_quote_id,
        status=quote.status,
        offer_date=quote.offer_date,
        validity_days=quote.validity_days,
        valid_until=svc.valid_until(quote),
        customer_id=quote.customer_id,
        customer_snapshot=quote.customer_snapshot or {},
        contact=quote.contact,
        contact_email=quote.contact_email,
        trade_term=quote.trade_term,
        payment_terms=quote.payment_terms,
        currency=quote.currency,
        language=quote.language,
        notes_header=quote.notes_header,
        notes_footer=quote.notes_footer,
        discount_pct=quote.discount_pct,
        discount_amount=quote.discount_amount,
        subtotal=quote.subtotal,
        grand_total=quote.grand_total,
        sections=sections,
        revisions=revisions,
        proformas=pis,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


def _line_out(
    line: QuoteLine,
    number: str,
    margin: Decimal,
    products: dict[int, Product],
    settings: AppSettings,
) -> LineOut:
    product = products.get(line.product_id) if line.product_id else None
    return LineOut(
        id=line.id,
        section_id=line.section_id,
        sort_order=line.sort_order,
        line_no=line.line_no,
        printed_no=number,
        kind=line.kind,
        product_id=line.product_id,
        category_id=line.category_id,
        configuration_id=line.configuration_id,
        name=line.name,
        name_emphasis=line.name_emphasis,
        description_lines=[DescriptionLine(**d) for d in line.description_lines or []],
        model_no=line.model_no,
        material=line.material,
        image_ids=line.image_ids or [],
        qty=line.qty,
        cost_usd=line.cost_usd,
        margin_pct=line.margin_pct,
        effective_margin_pct=svc.effective_margin(line, margin),
        unit_price=line.unit_price,
        unit_price_manual=line.unit_price_manual,
        total=line.total,
        price_source=line.price_source or {},
        components=[Component(**c) for c in line.components or []],
        warnings=svc.line_warnings(line, product, settings)
        + svc.component_warnings(line, products, settings),
    )


def _done(session: Session, quote: Quote) -> QuoteOut:
    session.commit()
    session.expire_all()  # money as stored (4 places), not as computed in memory
    return serialize(session, get_quote(session, quote.id))


# ------------------------------------------------------------------ quotes


@router.get("", response_model=QuoteList)
def list_quotes(
    session: SessionDep,
    q: str | None = None,
    status: str | None = None,
    customer: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> QuoteList:
    stmt = select(Quote)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Quote.offer_no.ilike(like),
                func.json_extract(Quote.customer_snapshot, "$.name").ilike(like),
                func.json_extract(Quote.customer_snapshot, "$.code").ilike(like),
            )
        )
    if status:
        stmt = stmt.where(Quote.status == status)
    if customer is not None:
        stmt = stmt.where(Quote.customer_id == customer)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.options(*QUOTE_LOADS)
        .order_by(Quote.offer_date.desc(), Quote.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    settings = load_settings()
    product_ids = {line.product_id for qt in rows for s in qt.sections for line in s.lines
                   if line.product_id}  # fmt: skip
    products = (
        {p.id: p for p in session.scalars(select(Product).where(Product.id.in_(product_ids)))}
        if product_ids
        else {}
    )
    items = []
    for quote in rows:
        lines = [line for s in quote.sections for line in s.lines]
        warnings = sum(
            1
            for line in lines
            if svc.line_warnings(line, products.get(line.product_id or 0), settings)
        )
        snapshot = quote.customer_snapshot or {}
        items.append(
            QuoteSummary(
                id=quote.id,
                display_no=quote.display_no,
                status=quote.status,
                offer_date=quote.offer_date,
                customer_name=snapshot.get("name"),
                customer_code=snapshot.get("code"),
                grand_total=quote.grand_total,
                lines=len(lines),
                warnings=warnings,
                updated_at=quote.updated_at,
            )
        )
    return QuoteList(items=items, total=total)


@router.post("", response_model=QuoteOut, status_code=201)
def create_quote(session: SessionDep, body: QuoteCreate) -> QuoteOut:
    quote = svc.create_quote(session, body.model_dump(exclude_none=True))
    return _done(session, quote)


@router.get("/{quote_id}", response_model=QuoteOut)
def read_quote(session: SessionDep, quote_id: int) -> QuoteOut:
    return serialize(session, get_quote(session, quote_id))


@router.patch("/{quote_id}", response_model=QuoteOut)
def update_quote(session: SessionDep, quote_id: int, body: QuotePatch) -> QuoteOut:
    quote = get_quote(session, quote_id)
    data = body.model_dump(exclude_unset=True)
    if set(data) - {"status"}:
        _editable(quote)
    svc.update_quote(session, quote, data)
    return _done(session, quote)


@router.delete("/{quote_id}", status_code=204)
def delete_quote(session: SessionDep, quote_id: int) -> Response:
    quote = get_quote(session, quote_id)
    if session.scalar(select(func.count()).where(ProformaInvoice.quote_id == quote.id)):
        raise ProblemError(409, "quote.has_proformas", "Delete its proforma invoices first")
    session.delete(quote)
    session.commit()
    return Response(status_code=204)


@router.post("/{quote_id}/duplicate", response_model=QuoteOut, status_code=201)
def duplicate_quote(session: SessionDep, quote_id: int) -> QuoteOut:
    copy = svc.copy_quote(session, get_quote(session, quote_id), revision=False)
    return _done(session, copy)


@router.post("/{quote_id}/revision", response_model=QuoteOut, status_code=201)
def new_revision(session: SessionDep, quote_id: int) -> QuoteOut:
    copy = svc.copy_quote(session, get_quote(session, quote_id), revision=True)
    return _done(session, copy)


# ---------------------------------------------------------------- sections


@router.post("/{quote_id}/sections", response_model=QuoteOut, status_code=201)
def add_section(session: SessionDep, quote_id: int, body: SectionIn) -> QuoteOut:
    quote = get_quote(session, quote_id)
    _editable(quote)
    svc.add_section(session, quote, body.model_dump(exclude_none=True))
    return _done(session, quote)


@router.patch("/{quote_id}/sections/{section_id}", response_model=QuoteOut)
def update_section(
    session: SessionDep, quote_id: int, section_id: int, body: SectionIn
) -> QuoteOut:
    quote = get_quote(session, quote_id)
    _editable(quote)
    svc.update_section(svc.get_section(quote, section_id), body.model_dump(exclude_unset=True))
    quote.sections.sort(key=lambda s: s.sort_order)
    return _done(session, quote)


@router.delete("/{quote_id}/sections/{section_id}", response_model=QuoteOut)
def delete_section(session: SessionDep, quote_id: int, section_id: int) -> QuoteOut:
    quote = get_quote(session, quote_id)
    _editable(quote)
    if len(quote.sections) == 1:
        raise ProblemError(422, "quote.last_section", "A quote needs at least one table")
    quote.sections.remove(svc.get_section(quote, section_id))
    svc.recalculate(session, quote)
    return _done(session, quote)


# ------------------------------------------------------------------- lines


@router.post("/{quote_id}/lines", response_model=QuoteOut, status_code=201)
def add_line(session: SessionDep, quote_id: int, body: LineCreate) -> QuoteOut:
    quote = get_quote(session, quote_id)
    _editable(quote)
    section = svc.get_section(quote, body.section_id)
    if body.configuration_id is not None:
        config = configurations.get(session, body.configuration_id)
        configurations.insert_into_quote(session, quote, section, config, body.qty)
    elif body.kind == "config":
        if not (body.name or "").strip():
            raise ProblemError(422, "quote.name_required", "A combined product needs a name")
        data = body.model_dump(include={"name", "qty", "model_no", "material"})
        data["components"] = [c.model_dump() for c in body.components or []]
        svc.add_config_line(session, quote, section, data)
    elif body.product_id is not None:
        product = session.get(Product, body.product_id)
        if product is None:
            raise ProblemError(404, "product.not_found", "Product not found", id=body.product_id)
        svc.add_product_line(session, quote, section, product, body.qty)
    else:
        if not (body.name or "").strip():
            raise ProblemError(422, "quote.name_required", "A manual item needs a name")
        data = body.model_dump(exclude={"section_id", "product_id"})
        data["description_lines"] = [d.model_dump() for d in body.description_lines or []]
        svc.add_manual_line(session, quote, section, data)
    return _done(session, quote)


@router.patch("/{quote_id}/lines/{line_id}", response_model=QuoteOut)
def update_line(session: SessionDep, quote_id: int, line_id: int, body: LinePatch) -> QuoteOut:
    quote = get_quote(session, quote_id)
    _editable(quote)
    data = body.model_dump(exclude_unset=True)
    if "description_lines" in data and data["description_lines"] is not None:
        data["description_lines"] = [dict(d) for d in data["description_lines"]]
    svc.update_line(session, quote, svc.get_line(quote, line_id), data)
    return _done(session, quote)


@router.post("/{quote_id}/lines/combine", response_model=QuoteOut)
def combine_lines(session: SessionDep, quote_id: int, body: CombineIn) -> QuoteOut:
    """Several lines become one product; the customer sees one row, the parts stay inside."""
    quote = get_quote(session, quote_id)
    _editable(quote)
    svc.combine_lines(session, quote, body.line_ids, body.name.strip())
    return _done(session, quote)


@router.post("/{quote_id}/lines/{line_id}/split", response_model=QuoteOut)
def split_line(session: SessionDep, quote_id: int, line_id: int) -> QuoteOut:
    quote = get_quote(session, quote_id)
    _editable(quote)
    svc.split_line(session, quote, svc.get_line(quote, line_id))
    return _done(session, quote)


@router.delete("/{quote_id}/lines/{line_id}", response_model=QuoteOut)
def delete_line(session: SessionDep, quote_id: int, line_id: int) -> QuoteOut:
    quote = get_quote(session, quote_id)
    _editable(quote)
    line = svc.get_line(quote, line_id)
    line.section.lines.remove(line)
    svc.recalculate(session, quote)
    return _done(session, quote)


@router.post("/{quote_id}/lines/reorder", response_model=QuoteOut)
def reorder_lines(session: SessionDep, quote_id: int, body: ReorderIn) -> QuoteOut:
    quote = get_quote(session, quote_id)
    _editable(quote)
    svc.reorder_lines(session, quote, svc.get_section(quote, body.section_id), body.line_ids)
    return _done(session, quote)


@router.post("/{quote_id}/lines/{line_id}/refresh-cost", response_model=QuoteOut)
def refresh_cost(session: SessionDep, quote_id: int, line_id: int) -> QuoteOut:
    quote = get_quote(session, quote_id)
    _editable(quote)
    svc.refresh_line_cost(session, quote, svc.get_line(quote, line_id))
    return _done(session, quote)


# ----------------------------------------------------------------- exports


def _filename(quote: Quote, suffix: str, internal: bool = False) -> str:
    tag = "_INTERNAL" if internal else ""
    return f"{quote.display_no.replace(' ', '_')}{tag}.{suffix}"


def _disposition(name: str, download: bool) -> dict[str, str]:
    kind = "attachment" if download else "inline"
    return {"Content-Disposition": f'{kind}; filename="{name}"'}


@router.get("/{quote_id}/export.pdf")
def export_pdf(
    session: SessionDep, quote_id: int, download: bool = False, internal: bool = False
) -> Response:
    """``internal`` gives the seller's version with cost, margin and profit."""
    quote = get_quote(session, quote_id)
    settings = load_settings()
    if internal:
        pdf = render_costing(quote, svc.costing(session, quote, settings), settings)
    else:
        pdf = render_quote(quote, settings, image_resolver(session))
    name = _filename(quote, "pdf", internal)
    return Response(pdf, media_type="application/pdf", headers=_disposition(name, download))


@router.get("/{quote_id}/export.xlsx")
def export_xlsx(session: SessionDep, quote_id: int, internal: bool = False) -> Response:
    quote = get_quote(session, quote_id)
    settings = load_settings()
    if internal:
        data = costing_workbook(quote, svc.costing(session, quote, settings))
    else:
        data = quote_workbook(quote, settings, image_resolver(session))
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=_disposition(_filename(quote, "xlsx", internal), True),
    )


# --------------------------------------------------------------- proformas


@router.post("/{quote_id}/proforma", response_model=ProformaOut, status_code=201)
def create_proforma(session: SessionDep, quote_id: int, body: ProformaCreate) -> ProformaInvoice:
    invoice = proformas.create_from_quote(
        session, get_quote(session, quote_id), body.line_ids, body.po_no
    )
    session.commit()
    session.refresh(invoice)
    return invoice
