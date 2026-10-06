"""Proforma invoice PDF, after docs/examples/proforma_invoice_ANZX20260914.pdf (plan §5.4).

Always issued by the company in Settings (Sixunited), whatever the sample's issuer.
"""

from __future__ import annotations

from decimal import Decimal

from app.config import AppSettings
from app.models import ProformaInvoice
from app.services.documents.common import (
    BLACK,
    FONT,
    YELLOW_PI,
    Cell,
    Column,
    Document,
    Run,
    Table,
    amount,
    image_size,
    quantity,
    text_cell,
    ymd_slash,
)
from app.services.documents.quote_pdf import ImageResolver, description_runs

SHARES = (0.16, 0.11, 0.31, 0.14, 0.07, 0.09, 0.12)
TERM_LINE = 3.4  # mm between lines of a term
TITLES = ("Model", "Name", "Description", "Photo", "Quantity", "Unit Price", "Net Amount")


def _pair(pdf: Document, label: str, value: str, right: float, y: float, size: float = 8) -> None:
    """``label`` bold and ``value`` regular, the pair right-aligned at ``right``."""
    pdf.set_font(FONT, "B", size)
    lw = pdf.get_string_width(label)
    pdf.set_font(FONT, "", size)
    vw = pdf.get_string_width(value)
    pdf.set_font(FONT, "B", size)
    pdf.set_xy(right - lw - vw, y)
    pdf.cell(lw, 4, label)
    pdf.set_font(FONT, "", size)
    pdf.cell(vw, 4, value)


def _header(pdf: Document, invoice: ProformaInvoice, settings: AppSettings) -> None:
    company = settings.company
    left, right = pdf.l_margin, pdf.w - pdf.r_margin
    pdf.set_font(FONT, "B", 13)
    pdf.set_xy(left, 18)
    pdf.cell(0, 6, company.name_en)
    pdf.set_font(FONT, "", 7.5)
    pdf.set_xy(left, 24)
    pdf.cell(0, 4, company.address_en)
    pdf.set_xy(right - 30, 24)
    pdf.cell(30, 4, f"Page {pdf.page_no()}", align="R")

    pdf.set_font(FONT, "B", 15)
    pdf.set_xy(left, 33)
    pdf.cell(pdf.content_width, 8, "Proforma   Invoice", align="C")

    # customer box with its label sitting on the top border
    box_x, box_y, box_w, box_h = left + 6, 49, 100, 28
    pdf.set_line_width(0.3)
    pdf.rect(box_x, box_y, box_w, box_h, round_corners=True, corner_radius=4)
    pdf.set_font(FONT, "B", 9)
    label_w = pdf.get_string_width("Customer") + 4
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(box_x + 1, box_y - 2.5, label_w + 2, 5, style="F")
    pdf.set_xy(box_x + 2, box_y - 2.5)
    pdf.cell(label_w, 5, "Customer")
    customer = invoice.customer_snapshot or {}
    pdf.set_font(FONT, "B", 10)
    pdf.set_xy(box_x + 14, box_y + 8)
    pdf.cell(box_w - 16, 5, str(customer.get("name") or ""))
    if invoice.attention:
        pdf.set_xy(box_x + 14, box_y + 17)
        pdf.cell(box_w - 16, 5, f"Atten: {invoice.attention}")

    seller = invoice.seller_contact or {}
    rows = [
        ("Inv No.: ", invoice.pi_no),
        ("Date: ", ymd_slash(invoice.issue_date)),
        ("P.O No.: ", invoice.po_no or ""),
        ("Customer ID: ", str(customer.get("code") or "")),
        ("Contact:", seller.get("name") or ""),
        ("Phone:", seller.get("phone") or ""),
    ]
    y = 56.0
    for label, value in rows:
        _pair(pdf, label, value, right, y)
        y += 4

    pdf.set_font(FONT, "", 8)
    text = "Currency: "
    pdf.set_font(FONT, "B", 8)
    value_w = pdf.get_string_width(invoice.currency)
    pdf.set_font(FONT, "", 8)
    label_w2 = pdf.get_string_width(text)
    pdf.set_xy(right - 30, 84)
    pdf.cell(label_w2, 4, text)
    pdf.set_font(FONT, "BU", 8)
    pdf.cell(value_w, 4, invoice.currency)
    pdf.set_font(FONT, "", 8)
    pdf.set_y(89)


def _table(pdf: Document, invoice: ProformaInvoice, image: ImageResolver) -> None:
    width = pdf.content_width
    columns = [Column(t, width * s) for t, s in zip(TITLES, SHARES, strict=True)]
    table = Table(
        pdf, columns, x=pdf.l_margin, size=7.2, header_size=7.5, header_fill=None, line_gap=1.2
    )
    table.border = False
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + width, pdf.get_y())
    table.header()
    foc = Decimal(invoice.foc_pct) if invoice.foc_pct else None
    for line in invoice.lines:
        runs = description_runs(line)
        if foc is not None:
            runs = [*runs, Run(f"{foc.normalize():f}% FOC")]
        photos = [p for p in (image(i) for i in (line.image_ids or [])[:2]) if p is not None]
        table.row(
            [
                text_cell(line.model_no, bold=True),
                text_cell(line.name, bold=True),
                Cell(lines=runs, align="L"),
                Cell(images=photos),
                text_cell(quantity(line.qty)),
                text_cell(amount(line.unit_price, decimals="always", dollar=True), bold=True),
                text_cell(amount(line.total, decimals="always", dollar=True), bold=True),
            ]
        )
    pdf.set_line_width(0.3)
    y = pdf.get_y() + 1
    pdf.line(pdf.l_margin, y, pdf.l_margin + width, y)
    pdf.set_y(y + 3)
    # Freight
    pdf.set_font(FONT, "B", 8)
    pdf.set_x(pdf.l_margin + columns[0].width)
    pdf.cell(columns[1].width, 5, "Freight", align="C")
    if invoice.freight is not None:
        pdf.set_x(pdf.l_margin + width - columns[-1].width)
        pdf.cell(
            columns[-1].width, 5, amount(invoice.freight, decimals="always", dollar=True), align="C"
        )
    pdf.ln(7)
    # Total
    total_w = columns[-1].width + columns[-2].width
    x = pdf.l_margin + width - total_w
    pdf.set_fill_color(*YELLOW_PI)
    pdf.rect(x, pdf.get_y(), total_w, 5.5, style="F")
    pdf.set_xy(x + 1, pdf.get_y())
    pdf.cell(columns[-2].width - 1, 5.5, "Total")
    pdf.cell(
        columns[-1].width, 5.5, amount(invoice.total, decimals="always", dollar=True), align="C"
    )
    pdf.ln(12)


def _terms(pdf: Document, invoice: ProformaInvoice) -> None:
    left = pdf.l_margin + 20
    pdf.set_font(FONT, "BU", 8)
    pdf.set_x(left)
    pdf.cell(0, 5, "TERMS & CONDITION:")
    pdf.ln(5)
    label_w = 23.0
    text_w = pdf.content_width - 20 - label_w
    for number, term in enumerate(invoice.terms or [], start=1):
        text = str(term.get("text") or "")
        lines = pdf.wrap(text, text_w, 7.5)
        if pdf.get_y() + len(lines) * TERM_LINE > pdf.bottom:
            pdf.add_page()
            pdf.set_y(pdf.t_margin)
        y = pdf.get_y()
        pdf.set_font(FONT, "", 7.5)
        pdf.set_xy(left - 5, y)
        pdf.cell(4, TERM_LINE, str(number), align="R")
        pdf.set_font(FONT, "B", 7.5)
        pdf.set_xy(left, y)
        pdf.cell(label_w, TERM_LINE, f"{term.get('title') or ''}:")
        pdf.set_font(FONT, "", 7.5)
        for i, piece in enumerate(lines):
            pdf.set_xy(left + label_w, y + i * TERM_LINE)
            pdf.cell(text_w, TERM_LINE, piece)
        pdf.set_y(y + max(len(lines), 1) * TERM_LINE + 0.6)
    pdf.ln(5)


def _bank(pdf: Document, settings: AppSettings) -> None:
    company = settings.company
    left = pdf.l_margin + 20
    if pdf.get_y() + 30 > pdf.bottom:
        pdf.add_page()
        pdf.set_y(pdf.t_margin)
    pdf.set_font(FONT, "B", 10)
    pdf.set_x(pdf.l_margin + 8)
    pdf.cell(5, 5, "•")
    pdf.set_font(FONT, "BU", 8)
    pdf.set_x(left)
    pdf.cell(0, 5, "Our Banking Info:")
    pdf.ln(5)
    for label, value in (
        ("Account Name:", company.bank_account_name),
        ("Account No:", company.bank_account_no),
        ("Bank Name:", company.bank_name),
        ("Swift Code :", company.bank_swift),
    ):
        pdf.set_font(FONT, "", 7.5)
        pdf.set_x(left)
        pdf.cell(20, 4.2, label)
        pdf.set_font(FONT, "B", 10)
        pdf.cell(0, 4.2, value)
        pdf.ln(4.2)
    pdf.ln(5)


def _signatures(
    pdf: Document, invoice: ProformaInvoice, settings: AppSettings, image: ImageResolver
) -> None:
    if pdf.get_y() + 26 > pdf.bottom:
        pdf.add_page()
        pdf.set_y(pdf.t_margin)
    left, mid = pdf.l_margin + 20, pdf.l_margin + 105
    y = pdf.get_y()
    pdf.set_font(FONT, "B", 8)
    pdf.set_xy(left, y)
    pdf.cell(80, 5, f"Seller:{settings.company.name_en}")
    pdf.set_xy(mid, y)
    pdf.cell(60, 5, "Buyer:")
    pdf.set_xy(left, y + 9)
    pdf.cell(16, 5, "Signed by:")
    pdf.set_xy(mid, y + 9)
    pdf.cell(16, 5, "Signed by:")
    signature = (
        image(settings.company.signature_image_id) if settings.company.signature_image_id else None
    )
    if signature is not None:
        w, h = image_size(signature)
        sig_h = 11.0
        sig_w = min(sig_h * w / h if h else 0, 50.0)
        pdf.image(str(signature), x=left + 17, y=y + 5, w=sig_w, h=sig_w * h / w if w else sig_h)
    pdf.set_xy(left, y + 20)
    pdf.cell(60, 5, f"Date: {ymd_slash(invoice.issue_date)}")
    pdf.set_xy(mid, y + 20)
    pdf.cell(60, 5, "Date:")
    pdf.set_text_color(*BLACK)


def render_proforma(invoice: ProformaInvoice, settings: AppSettings, image: ImageResolver) -> bytes:
    pdf = Document(number_pages=False)
    pdf.set_title(invoice.pi_no)
    pdf.set_author(settings.company.name_en)
    pdf.add_page()
    _header(pdf, invoice, settings)
    _table(pdf, invoice, image)
    _terms(pdf, invoice)
    _bank(pdf, settings)
    _signatures(pdf, invoice, settings, image)
    return bytes(pdf.output())
