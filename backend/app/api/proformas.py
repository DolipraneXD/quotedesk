from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import SessionDep
from app.api.quotes import _disposition, image_resolver
from app.config import load_settings
from app.errors import ProblemError
from app.models import ProformaInvoice
from app.schemas.quotes import ProformaLinePatch, ProformaOut, ProformaPatch, ProformaSummary
from app.services import proformas as svc
from app.services.documents.proforma_pdf import render_proforma
from app.services.documents.xlsx import proforma_workbook

router = APIRouter(prefix="/proformas", tags=["proformas"])


def _get(session: Session, invoice_id: int) -> ProformaInvoice:
    invoice = session.get(
        ProformaInvoice, invoice_id, options=[selectinload(ProformaInvoice.lines)]
    )
    if invoice is None:
        raise ProblemError(404, "proforma.not_found", "Proforma invoice not found", id=invoice_id)
    return invoice


def _done(session: Session, invoice: ProformaInvoice) -> ProformaInvoice:
    session.commit()
    session.refresh(invoice)
    return invoice


@router.get("", response_model=list[ProformaSummary])
def list_proformas(session: SessionDep, quote: int | None = None) -> list[ProformaInvoice]:
    stmt = select(ProformaInvoice).order_by(
        ProformaInvoice.issue_date.desc(), ProformaInvoice.id.desc()
    )
    if quote is not None:
        stmt = stmt.where(ProformaInvoice.quote_id == quote)
    return list(session.scalars(stmt))


@router.get("/{invoice_id}", response_model=ProformaOut)
def read_proforma(session: SessionDep, invoice_id: int) -> ProformaInvoice:
    return _get(session, invoice_id)


@router.patch("/{invoice_id}", response_model=ProformaOut)
def update_proforma(session: SessionDep, invoice_id: int, body: ProformaPatch) -> ProformaInvoice:
    invoice = _get(session, invoice_id)
    data = body.model_dump(exclude_unset=True)
    if "terms" in data and data["terms"] is not None:
        data["terms"] = [dict(t) for t in data["terms"]]
    svc.update(session, invoice, data)
    return _done(session, invoice)


@router.patch("/{invoice_id}/lines/{line_id}", response_model=ProformaOut)
def update_proforma_line(
    session: SessionDep, invoice_id: int, line_id: int, body: ProformaLinePatch
) -> ProformaInvoice:
    invoice = _get(session, invoice_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("description_lines") is not None:
        data["description_lines"] = [dict(d) for d in data["description_lines"]]
    svc.update_line(session, invoice, svc.get_pi_line(invoice, line_id), data)
    return _done(session, invoice)


@router.delete("/{invoice_id}/lines/{line_id}", response_model=ProformaOut)
def delete_proforma_line(session: SessionDep, invoice_id: int, line_id: int) -> ProformaInvoice:
    invoice = _get(session, invoice_id)
    svc.remove_line(session, invoice, svc.get_pi_line(invoice, line_id))
    return _done(session, invoice)


@router.post("/{invoice_id}/issue", response_model=ProformaOut)
def issue_proforma(session: SessionDep, invoice_id: int) -> ProformaInvoice:
    invoice = _get(session, invoice_id)
    svc.issue(session, invoice)
    return _done(session, invoice)


@router.post("/{invoice_id}/cancel", response_model=ProformaOut)
def cancel_proforma(session: SessionDep, invoice_id: int) -> ProformaInvoice:
    invoice = _get(session, invoice_id)
    svc.cancel(session, invoice)
    return _done(session, invoice)


@router.post("/{invoice_id}/revise", response_model=ProformaOut, status_code=201)
def revise_proforma(session: SessionDep, invoice_id: int) -> ProformaInvoice:
    copy = svc.revise(session, _get(session, invoice_id))
    return _done(session, copy)


@router.delete("/{invoice_id}", status_code=204)
def delete_proforma(session: SessionDep, invoice_id: int) -> Response:
    invoice = _get(session, invoice_id)
    if invoice.status != "draft":
        raise ProblemError(409, "proforma.issued", "Only a draft can be deleted; cancel it instead")
    session.delete(invoice)
    session.commit()
    return Response(status_code=204)


@router.get("/{invoice_id}/export.pdf")
def export_pdf(session: SessionDep, invoice_id: int, download: bool = False) -> Response:
    invoice = _get(session, invoice_id)
    pdf = render_proforma(invoice, load_settings(), image_resolver(session))
    return Response(
        pdf, media_type="application/pdf", headers=_disposition(f"{invoice.pi_no}.pdf", download)
    )


@router.get("/{invoice_id}/export.xlsx")
def export_xlsx(session: SessionDep, invoice_id: int) -> Response:
    invoice = _get(session, invoice_id)
    data = proforma_workbook(invoice, load_settings(), image_resolver(session))
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=_disposition(f"{invoice.pi_no}.xlsx", True),
    )
