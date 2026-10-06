"""Proforma invoices from accepted quotes (plan §5.4).

A PI is a snapshot of chosen quote lines. It can be edited while it is a draft; once
issued it never changes, and a correction is a new PI numbered ``<no>-R2``.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import AppSettings, load_settings
from app.errors import ProblemError
from app.models import ProformaInvoice, ProformaLine, Quote
from app.services.quotes import get_line, round_money, today

TERM_TITLES = ("Payment Term", "Lead time", "Delivery Place", "Warranty time")


def default_terms(settings: AppSettings, trade_term: str | None) -> list[dict[str, str]]:
    payment = settings.pi_payment_term.replace("{trade_term}", trade_term or "FOB Shenzhen")
    texts = (payment, settings.pi_lead_time, settings.pi_delivery_place, settings.pi_warranty)
    return [{"title": title, "text": text} for title, text in zip(TERM_TITLES, texts, strict=True)]


def seller_contact(settings: AppSettings) -> dict[str, str]:
    company = settings.company
    return {
        "name": company.seller_name,
        "phone": company.seller_phone,
        "email": company.seller_email,
    }


def next_pi_no(session: Session, prefix: str) -> str:
    """PREFIX + YYYYMMDD, with -02, -03 … when several are issued the same day."""
    base = f"{prefix}{today():%Y%m%d}"
    taken = set(session.scalars(select(ProformaInvoice.pi_no).where(
        ProformaInvoice.pi_no.like(f"{base}%")
    )))  # fmt: skip
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n:02d}" in taken:
        n += 1
    return f"{base}-{n:02d}"


def recalculate(invoice: ProformaInvoice) -> None:
    for line in invoice.lines:
        line.total = round_money(Decimal(line.qty) * Decimal(line.unit_price))
    invoice.subtotal = sum((line.total for line in invoice.lines), Decimal("0"))
    invoice.total = invoice.subtotal + Decimal(invoice.freight or 0)


def create_from_quote(
    session: Session, quote: Quote, line_ids: list[int], po_no: str | None
) -> ProformaInvoice:
    if quote.status != "accepted":
        raise ProblemError(409, "proforma.quote_not_accepted", "Mark the quote accepted first")
    if not line_ids:
        raise ProblemError(422, "proforma.no_lines", "Pick at least one line")
    settings = load_settings()
    invoice = ProformaInvoice(
        pi_no=next_pi_no(session, settings.pi_prefix),
        quote_id=quote.id,
        status="draft",
        po_no=po_no,
        issue_date=today(),
        customer_snapshot=dict(quote.customer_snapshot or {}),
        attention=quote.contact,
        seller_contact=seller_contact(settings),
        currency=quote.currency,
        terms=default_terms(settings, quote.trade_term),
    )
    for position, line_id in enumerate(line_ids):
        line = get_line(quote, line_id)
        invoice.lines.append(
            ProformaLine(
                source_line_id=line.id,
                sort_order=position,
                model_no=line.model_no,
                name=line.name,
                description_lines=[dict(d) for d in line.description_lines or []],
                image_ids=list(line.image_ids or []),
                qty=line.qty,
                unit_price=line.unit_price,
            )
        )
    recalculate(invoice)
    session.add(invoice)
    session.flush()
    return invoice


HEADER_FIELDS = ("po_no", "issue_date", "attention", "foc_pct", "freight", "terms")
LINE_FIELDS = ("model_no", "name", "description_lines", "image_ids", "qty", "unit_price")


def _require_draft(invoice: ProformaInvoice) -> None:
    if invoice.status != "draft":
        raise ProblemError(409, "proforma.issued", "An issued proforma invoice cannot change")


def update(session: Session, invoice: ProformaInvoice, data: dict[str, Any]) -> None:
    _require_draft(invoice)
    if "pi_no" in data and data["pi_no"] != invoice.pi_no:
        pi_no = (data["pi_no"] or "").strip()
        if not pi_no:
            raise ProblemError(422, "proforma.no_number", "The invoice number is required")
        clash = session.scalar(select(ProformaInvoice).where(ProformaInvoice.pi_no == pi_no))
        if clash is not None:
            raise ProblemError(409, "proforma.number_taken", "Number already used", pi_no=pi_no)
        invoice.pi_no = pi_no
    for key in HEADER_FIELDS:
        if key in data:
            setattr(invoice, key, data[key])
    if "seller_contact" in data:
        invoice.seller_contact = {**invoice.seller_contact, **(data["seller_contact"] or {})}
    if "customer_snapshot" in data:
        invoice.customer_snapshot = {
            **invoice.customer_snapshot,
            **(data["customer_snapshot"] or {}),
        }
    recalculate(invoice)
    session.flush()


def get_pi_line(invoice: ProformaInvoice, line_id: int) -> ProformaLine:
    for line in invoice.lines:
        if line.id == line_id:
            return line
    raise ProblemError(404, "proforma.line_not_found", "Line not found", id=line_id)


def update_line(
    session: Session, invoice: ProformaInvoice, line: ProformaLine, data: dict[str, Any]
) -> None:
    _require_draft(invoice)
    for key in LINE_FIELDS:
        if key in data and data[key] is not None:
            setattr(line, key, data[key])
    if line.qty < 1:
        raise ProblemError(422, "quote.invalid_qty", "Quantity must be at least 1")
    recalculate(invoice)
    session.flush()


def remove_line(session: Session, invoice: ProformaInvoice, line: ProformaLine) -> None:
    _require_draft(invoice)
    if len(invoice.lines) == 1:
        raise ProblemError(422, "proforma.no_lines", "A proforma invoice needs at least one line")
    invoice.lines.remove(line)
    recalculate(invoice)
    session.flush()


def issue(session: Session, invoice: ProformaInvoice) -> None:
    _require_draft(invoice)
    invoice.status = "issued"
    invoice.issued_at = today()
    session.flush()


def cancel(session: Session, invoice: ProformaInvoice) -> None:
    if invoice.status == "cancelled":
        return
    invoice.status = "cancelled"
    session.flush()


def revise(session: Session, invoice: ProformaInvoice) -> ProformaInvoice:
    """A draft copy of an issued PI: ANZX20260914 -> ANZX20260914-R2 -> -R3 …"""
    if invoice.status == "draft":
        raise ProblemError(409, "proforma.still_draft", "Edit the draft instead")
    base = re.sub(r"-R\d+$", "", invoice.pi_no)
    taken = set(session.scalars(select(ProformaInvoice.pi_no).where(
        ProformaInvoice.pi_no.like(f"{base}-R%")
    )))  # fmt: skip
    n = 2
    while f"{base}-R{n}" in taken:
        n += 1
    copy = ProformaInvoice(
        pi_no=f"{base}-R{n}",
        quote_id=invoice.quote_id,
        status="draft",
        po_no=invoice.po_no,
        issue_date=today(),
        customer_snapshot=dict(invoice.customer_snapshot),
        attention=invoice.attention,
        seller_contact=dict(invoice.seller_contact),
        currency=invoice.currency,
        foc_pct=invoice.foc_pct,
        freight=invoice.freight,
        terms=[dict(t) for t in invoice.terms],
        revised_from_id=invoice.id,
    )
    for line in invoice.lines:
        copy.lines.append(
            ProformaLine(
                source_line_id=line.source_line_id,
                sort_order=line.sort_order,
                model_no=line.model_no,
                name=line.name,
                description_lines=[dict(d) for d in line.description_lines],
                image_ids=list(line.image_ids),
                qty=line.qty,
                unit_price=line.unit_price,
            )
        )
    recalculate(copy)
    session.add(copy)
    session.flush()
    return copy
