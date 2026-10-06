"""Quote PDF: the company header, then one table per section in its layout (plan §5.3).

``offer`` follows docs/examples/offer_ups_WKZ20260811.pdf and ``list`` follows
docs/examples/quotation_list_2in1_laptop_WKZ20260817.pdf.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.config import AppSettings
from app.models import Quote, QuoteLine, QuoteSection
from app.services.documents.common import (
    BLACK,
    FONT,
    RED,
    YELLOW,
    Cell,
    Column,
    Document,
    Run,
    Table,
    amount,
    dmy,
    image_size,
    labels,
    quantity,
    text_cell,
)
from app.services.quotes import printed_numbers

ImageResolver = Callable[[int], Path | None]

# column shares of the content width, measured on the samples
OFFER_SHARES = (0.045, 0.21, 0.43, 0.055, 0.08, 0.18)
LIST_SHARES = (0.04, 0.31, 0.14, 0.07, 0.14, 0.08, 0.08, 0.14)


def description_runs(line: QuoteLine | object) -> list[Run]:
    lines = getattr(line, "description_lines", None) or []
    return [Run(d.get("text", ""), RED if d.get("emphasis") else BLACK) for d in lines] or [Run("")]


def list_description(line: QuoteLine) -> list[dict[str, Any]]:
    """The list layout has no Name column: a line without specs prints its name instead."""
    return line.description_lines or [{"text": line.name, "emphasis": line.name_emphasis}]


def company_header(
    pdf: Document, settings: AppSettings, language: str, image: ImageResolver
) -> float:
    """Logo on the left, company name and address centred beside it, in a box."""
    company = settings.company
    x, y, width = pdf.l_margin, pdf.get_y(), pdf.content_width
    logo = image(company.logo_image_id) if company.logo_image_id else None
    text_x, text_w = x, width
    if logo is not None:
        w, h = image_size(logo)
        logo_h = 13.0
        logo_w = min(logo_h * w / h if h else 0, 45.0)
        pdf.image(str(logo), x=x + 3, y=y + 3.5, w=logo_w, h=logo_w * h / w if w else logo_h)
        text_x, text_w = x + logo_w + 5, width - logo_w - 8
    names = [company.name_en]
    if language == "zh" and company.name_zh:
        names.insert(0, company.name_zh)
    text_y = y + 3
    for name in names:
        pdf.set_font(FONT, "B", 15)
        pdf.set_xy(text_x, text_y)
        pdf.cell(text_w, 7.5, name, align="C")
        text_y += 7.5
    address = company.address_zh if language == "zh" and company.address_zh else company.address_en
    size = 8.5
    while size > 6 and pdf.get_string_width(address) > text_w:
        size -= 0.25
        pdf.set_font(FONT, "", size)
    pdf.set_font(FONT, "", size)
    pdf.set_xy(text_x, text_y)
    pdf.cell(text_w, 5, address, align="C")
    height = max(20.0, text_y + 7 - y)
    pdf.set_line_width(0.6)
    pdf.rect(x, y, width, height)
    pdf.set_line_width(0.25)
    return y + height


def label_value(
    pdf: Document, x: float, y: float, w: float, h: float, label: str, value: str
) -> None:
    """``label`` in bold followed by ``value``, centred in the box, as in the samples.
    The font shrinks when a long value would overflow the box."""
    size = 8.5
    while True:
        pdf.set_font(FONT, "B", size)
        lw = pdf.get_string_width(label)
        pdf.set_font(FONT, "", size)
        vw = pdf.get_string_width(value)
        if lw + vw <= w - 2 or size <= 6:
            break
        size -= 0.25
    start = x + max((w - lw - vw) / 2, 1)
    pdf.set_font(FONT, "B", size)
    pdf.set_xy(start, y)
    pdf.cell(lw, h, label)
    pdf.set_font(FONT, "", size)
    pdf.set_xy(start + lw, y)
    pdf.cell(vw, h, value)
    pdf.rect(x, y, w, h)


def info_grid(pdf: Document, quote: Quote, y: float) -> float:
    lab = labels(quote.language)
    customer = quote.customer_snapshot or {}
    top = [
        (lab["offer_no"], quote.display_no),
        (lab["to"], " " + str(customer.get("name") or "")),
        (lab["contact"], quote.contact or ""),
    ]
    bottom = [
        (lab["offer_date"], dmy(quote.offer_date)),
        (lab["client_code"], str(customer.get("code") or "")),
        (lab["trade_term"], " " + (quote.trade_term or "")),
    ]
    if quote.contact_email or quote.validity_days:
        top.append((lab["email"], quote.contact_email or ""))
        valid = f" {quote.validity_days} {lab['days']}" if quote.validity_days else ""
        bottom.append((lab["valid"], valid))
        shares: tuple[float, ...] = (0.32, 0.2, 0.2, 0.28)
    else:
        shares = (0.26, 0.49, 0.25)
    width = pdf.content_width
    for row in (top, bottom):
        x = pdf.l_margin
        for (label, value), share in zip(row, shares, strict=True):
            label_value(pdf, x, y, width * share, 5.5, label, value)
            x += width * share
        y += 5.5
    return y


def _columns(shares: tuple[float, ...], titles: list[str], width: float) -> list[Column]:
    return [Column(t, width * s) for t, s in zip(titles, shares, strict=True)]


def offer_section(pdf: Document, quote: Quote, section: QuoteSection) -> None:
    lab = labels(quote.language)
    table = Table(
        pdf,
        _columns(
            OFFER_SHARES,
            [
                lab["no"],
                lab["name"],
                lab["description"],
                lab["qty"],
                lab["unit_price"],
                lab["total_price"],
            ],
            pdf.content_width,
        ),  # fmt: skip
        x=pdf.l_margin,
    )
    table.header()
    for number, line in zip(printed_numbers(section), section.lines, strict=True):
        table.row(
            [
                text_cell(number),
                text_cell(line.name, color=RED if line.name_emphasis else BLACK),
                Cell(lines=description_runs(line), align="L"),
                text_cell(quantity(line.qty)),
                text_cell(amount(line.unit_price)),
                text_cell(amount(line.total), "R"),
            ]
        )
    table.row(
        [
            Cell(lines=[Run(lab["total"], bold=True)], span=5, fill=YELLOW, size=10),
            Cell(lines=[Run(amount(section.subtotal), bold=True)], align="R", fill=YELLOW, size=10),
        ]
    )


def list_section(pdf: Document, quote: Quote, section: QuoteSection, image: ImageResolver) -> None:
    lab = labels(quote.language)
    width = pdf.content_width
    table = Table(
        pdf,
        _columns(
            LIST_SHARES,
            [
                lab["list_no"],
                lab["description"],
                lab["model_no"],
                lab["material"],
                lab["photo"],
                lab["list_unit"],
                lab["quantity"],
                lab["list_total"],
            ],
            width,
        ),  # fmt: skip
        x=pdf.l_margin,
        size=7.2,
        header_size=7.5,
        header_fill=None,
    )
    title = section.title or lab["quotation_list"]
    table.row([Cell(lines=[Run(title, bold=True)], span=8, size=13)], is_header=True)
    table.header()
    for number, line in zip(printed_numbers(section), section.lines, strict=True):
        photos = [p for p in (image(i) for i in (line.image_ids or [])[:2]) if p is not None]
        table.row(
            [
                text_cell(number, bold=True),
                Cell(
                    lines=[
                        Run(str(d["text"]), RED if d.get("emphasis") else BLACK)
                        for d in list_description(line)
                    ],
                    align="L",
                ),
                text_cell(line.model_no),
                text_cell(line.material),
                Cell(images=photos),
                text_cell(amount(line.unit_price, dollar=True), bold=True),
                text_cell(quantity(line.qty), "R"),
                text_cell(amount(line.total, decimals="always", dollar=True)),
            ]
        )
    table.row(
        [
            Cell(lines=[Run(lab["total"], bold=True)], span=7, fill=YELLOW, size=10),
            Cell(
                lines=[Run(amount(section.subtotal, decimals="always", dollar=True), bold=True)],
                fill=YELLOW,
                size=9,
            ),
        ]
    )


def closing(pdf: Document, quote: Quote) -> None:
    lab = labels(quote.language)
    discount = Decimal(quote.subtotal) - Decimal(quote.grand_total)
    pdf.set_text_color(*BLACK)
    if discount:
        width = pdf.content_width
        for label, value in (
            (lab["subtotal"], quote.subtotal),
            (lab["discount"], -discount),
            (lab["grand_total"], quote.grand_total),
        ):
            if pdf.get_y() + 6 > pdf.bottom:
                pdf.add_page()
            pdf.set_font(FONT, "B", 10)
            pdf.set_x(pdf.l_margin)
            pdf.cell(width * 0.8, 6, label, align="R")
            pdf.cell(
                width * 0.2, 6, amount(Decimal(value), decimals="always", dollar=True), align="R"
            )
            pdf.ln(6)
    paragraphs = []
    if quote.payment_terms:
        paragraphs.append(f"{lab['payment_terms']} {quote.payment_terms}")
    if quote.notes_footer:
        paragraphs.append(quote.notes_footer)
    for text in paragraphs:
        pdf.ln(3)
        pdf.set_font(FONT, "", 9)
        lines = pdf.wrap(text, pdf.content_width, 9)
        if pdf.get_y() + len(lines) * 4.5 > pdf.bottom:
            pdf.add_page()
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.content_width, 4.5, text, align="L")


def render_quote(quote: Quote, settings: AppSettings, image: ImageResolver) -> bytes:
    pdf = Document()
    pdf.set_title(f"{quote.display_no}")
    pdf.set_author(settings.company.name_en)
    pdf.add_page()
    y = company_header(pdf, settings, quote.language, image)
    y = info_grid(pdf, quote, y)
    pdf.set_y(y)
    if quote.notes_header:
        pdf.ln(2)
        pdf.set_font(FONT, "", 9)
        pdf.multi_cell(pdf.content_width, 4.5, quote.notes_header, align="L")
    for index, section in enumerate(quote.sections):
        if index:
            pdf.ln(6)
        if section.layout == "list":
            list_section(pdf, quote, section, image)
        else:
            offer_section(pdf, quote, section)
    closing(pdf, quote)
    return bytes(pdf.output())
