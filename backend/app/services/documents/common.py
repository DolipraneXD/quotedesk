"""Shared document pieces: number formats, labels per language, and a small PDF table
engine (rows never split across pages, per-line colours inside a cell, photo cells)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import MethodReturnValue
from PIL import Image as PILImage

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
FONT = "Noto"

BLACK = (0, 0, 0)
RED = (230, 0, 0)
GREY_HEAD = (191, 191, 191)  # table header fill in the offer sample
YELLOW = (255, 242, 204)  # total row
YELLOW_PI = (255, 230, 153)

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "offer_no": "Offer No.", "to": "To:", "contact": "Contact:", "email": "Email:",
        "offer_date": "Offer date:", "client_code": "Client Code:", "trade_term": "Trade Term:",
        "valid": "Valid:", "days": "Days", "no": "NO", "name": "Name",
        "description": "Description", "qty": "Q'ty", "unit_price": "Units Price($)",
        "total_price": "Total price($)", "total": "Total price", "list_no": "NO.",
        "model_no": "ST Products No.", "material": "Material", "photo": "Photo",
        "list_unit": "Unit Price($)", "quantity": "Quantity", "list_total": "Total Price($)",
        "quotation_list": "Quotation List", "subtotal": "Subtotal", "discount": "Discount",
        "grand_total": "Grand total", "payment_terms": "Payment terms:", "page": "Page",
        "internal": "INTERNAL — cost and margin, do not send to the customer",
        "customer": "Customer:", "status": "Status:", "table": "Table", "product": "Product",
        "unit_cost": "Unit cost($)", "margin": "Margin %", "cost_total": "Total cost($)",
        "profit": "Profit($)", "total_cost": "Total cost", "revenue": "Quote total",
        "margin_on_cost": "Margin on cost",
        "missing_cost": "{n} item(s) without a cost are left out of cost and profit.",
    },
    "zh": {
        "offer_no": "报价单号：", "to": "客户：", "contact": "联系人：", "email": "邮箱：",
        "offer_date": "报价日期：", "client_code": "客户代码：", "trade_term": "贸易条款：",
        "valid": "有效期：", "days": "天", "no": "序号", "name": "品名",
        "description": "描述", "qty": "数量", "unit_price": "单价($)",
        "total_price": "总价($)", "total": "合计", "list_no": "序号",
        "model_no": "产品型号", "material": "材质", "photo": "图片",
        "list_unit": "单价($)", "quantity": "数量", "list_total": "总价($)",
        "quotation_list": "报价清单", "subtotal": "小计", "discount": "折扣",
        "grand_total": "总计", "payment_terms": "付款条件：", "page": "第",
        "internal": "内部文件 — 含成本与利润，请勿发送给客户",
        "customer": "客户：", "status": "状态：", "table": "表", "product": "产品",
        "unit_cost": "成本单价($)", "margin": "利润率 %", "cost_total": "成本合计($)",
        "profit": "利润($)", "total_cost": "成本合计", "revenue": "报价合计",
        "margin_on_cost": "成本利润率", "missing_cost": "{n} 项没有成本，未计入成本和利润。",
    },
}  # fmt: skip


def labels(language: str) -> dict[str, str]:
    return LABELS["zh" if language == "zh" else "en"]


# ---------------------------------------------------------------- numbers


def group(value: Decimal, places: int) -> str:
    q = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return f"{q:,.{places}f}"


def amount(value: Decimal | None, *, decimals: str = "auto", dollar: bool = False) -> str:
    """``decimals``: "auto" drops ".00" on whole amounts (490, 9,800), "always" keeps them."""
    if value is None:
        return ""
    value = Decimal(value)
    whole = value == value.to_integral_value()
    text = group(value, 0 if decimals == "auto" and whole else 2)
    if dollar:
        return f"-${text[1:]}" if text.startswith("-") else f"${text}"
    return text


def quantity(value: int | Decimal) -> str:
    return f"{int(value):,}"


def dmy(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def ymd_slash(value: date) -> str:
    """The proforma sample prints 2026/9/14."""
    return f"{value.year}/{value.month}/{value.day}"


# ----------------------------------------------------------------- table


@dataclass
class Run:
    """One printed line inside a cell."""

    text: str
    color: tuple[int, int, int] = BLACK
    bold: bool = False


@dataclass
class Cell:
    lines: list[Run] = field(default_factory=list)
    align: str = "C"  # L / C / R
    images: list[Path] = field(default_factory=list)
    size: float | None = None  # font size override
    fill: tuple[int, int, int] | None = None
    span: int = 1


def text_cell(text: str | None, align: str = "C", **kw: object) -> Cell:
    color = kw.pop("color", BLACK)
    bold = bool(kw.pop("bold", False))
    lines = [Run(t, color, bold) for t in (text or "").splitlines()] or [Run("")]  # type: ignore[arg-type]
    return Cell(lines=lines, align=align, **kw)  # type: ignore[arg-type]


MAX_PHOTO_H = 40.0  # mm
MIN_FONT = 5.5  # pt, smallest size a cell shrinks to


def image_size(path: Path) -> tuple[int, int]:
    with PILImage.open(path) as img:
        return img.size


@dataclass
class Column:
    title: str
    width: float  # mm
    align: str = "C"


class Document(FPDF):
    """Letter-size pages like the samples, the CJK font registered, page numbers."""

    def __init__(self, page_label: str = "", number_pages: bool = True) -> None:
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.add_font(FONT, "", str(FONTS_DIR / "NotoSansSC-Regular.ttf"))
        self.add_font(FONT, "B", str(FONTS_DIR / "NotoSansSC-Bold.ttf"))
        self.set_margins(15, 15, 15)
        self.c_margin = 0  # tables pad their own cells; wrap and measure on the same width
        self.set_auto_page_break(False)
        self.page_label = page_label
        self.number_pages = number_pages
        self.set_font(FONT, size=9)

    @property
    def bottom(self) -> float:
        return self.h - (18 if self.number_pages else 10)

    @property
    def content_width(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def footer(self) -> None:
        if not self.number_pages:
            return
        self.set_y(-12)
        self.set_font(FONT, size=8)
        self.set_text_color(*BLACK)
        self.cell(0, 5, str(self.page_no()), align="C")

    def wrap(self, text: str, width: float, size: float, bold: bool = False) -> list[str]:
        self.set_font(FONT, "B" if bold else "", size)
        if not text:
            return [""]
        lines = self.multi_cell(
            width, text=text, dry_run=True, output=MethodReturnValue.LINES, align="L"
        )
        return list(lines) if isinstance(lines, list) else [text]


@dataclass
class Table:
    pdf: Document
    columns: Sequence[Column]
    x: float
    size: float = 9
    header_size: float = 9
    header_fill: tuple[int, int, int] | None = GREY_HEAD
    pad: float = 1.2
    line_gap: float = 1.35  # line height = size(pt) * 0.3528 * line_gap mm
    border: bool = True
    min_row: float = 6

    @property
    def line_h(self) -> float:
        return self.size * 0.3528 * self.line_gap

    def _width(self, index: int, span: int) -> float:
        return sum(c.width for c in self.columns[index : index + span])

    def _fit(self, cell: Cell, width: float) -> float:
        """Shrink the cell's font until its longest word fits (like Excel's shrink to fit),
        so headers, part numbers and big amounts never break in the middle of a word."""
        size = cell.size or self.size
        words = [(w, r.bold) for r in cell.lines for w in r.text.split()]
        while size > MIN_FONT:
            too_wide = False
            for word, bold in words:
                self.pdf.set_font(FONT, "B" if bold else "", size)
                if self.pdf.get_string_width(word) > width:
                    too_wide = True
                    break
            if not too_wide:
                break
            size -= 0.25
        return size

    def _layout(self, cells: Sequence[Cell]) -> tuple[list[list[Run]], list[float], float]:
        wrapped: list[list[Run]] = []
        sizes: list[float] = []
        height = self.min_row
        index = 0
        for cell in cells:
            width = self._width(index, cell.span) - 2 * self.pad
            size = self._fit(cell, width)
            sizes.append(size)
            runs: list[Run] = []
            for run in cell.lines:
                for piece in self.pdf.wrap(run.text, width, size, run.bold):
                    runs.append(Run(piece, run.color, run.bold))
            wrapped.append(runs)
            lh = size * 0.3528 * self.line_gap
            text_h = len(runs) * lh if any(r.text for r in runs) else 0
            image_h = self._image_height(cell, width) if cell.images else 0
            height = max(height, text_h + 2 * self.pad, image_h + 2 * self.pad)
            index += cell.span
        return wrapped, sizes, height

    def _image_boxes(self, cell: Cell, inner: float) -> list[tuple[Path, float, float, float]]:
        """(path, slot width, image width, image height) for photos side by side."""
        gap = 2.0
        slot = (inner - gap * (len(cell.images) - 1)) / len(cell.images)
        boxes = []
        for path in cell.images:
            w, h = image_size(path)
            img_h = min(slot * h / w, MAX_PHOTO_H) if w and h else 0
            img_w = img_h * w / h if h else 0
            boxes.append((path, slot, img_w, img_h))
        return boxes

    def _image_height(self, cell: Cell, width: float) -> float:
        return max((box[3] for box in self._image_boxes(cell, width)), default=0)

    def header(self) -> None:
        cells = [text_cell(c.title, "C", bold=True, size=self.header_size) for c in self.columns]
        self.row(cells, fill=self.header_fill, is_header=True)

    def fits(self, cells: Sequence[Cell]) -> bool:
        _, _, height = self._layout(cells)
        return self.pdf.get_y() + height <= self.pdf.bottom

    def row(
        self,
        cells: Sequence[Cell],
        fill: tuple[int, int, int] | None = None,
        is_header: bool = False,
        on_new_page: object = None,
    ) -> None:
        wrapped, sizes, height = self._layout(cells)
        pdf = self.pdf
        if not is_header and pdf.get_y() + height > pdf.bottom:
            pdf.add_page()
            pdf.set_y(pdf.t_margin)
            if callable(on_new_page):
                on_new_page()
            self.header()
        y = pdf.get_y()
        x = self.x
        index = 0
        for cell, runs, size in zip(cells, wrapped, sizes, strict=True):
            width = self._width(index, cell.span)
            colour = cell.fill or fill
            if colour:
                pdf.set_fill_color(*colour)
                pdf.rect(x, y, width, height, style="F")
            if self.border:
                pdf.set_draw_color(0, 0, 0)
                pdf.set_line_width(0.25)
                pdf.rect(x, y, width, height)
            lh = size * 0.3528 * self.line_gap
            if cell.images:
                self._draw_images(cell, x, y, width, height)
            if any(r.text for r in runs):
                top = y + (height - len(runs) * lh) / 2
                for i, run in enumerate(runs):
                    pdf.set_font(FONT, "B" if run.bold else "", size)
                    pdf.set_text_color(*run.color)
                    pdf.set_xy(x + self.pad, top + i * lh)
                    pdf.cell(width - 2 * self.pad, lh, run.text, align=cell.align)
            x += width
            index += cell.span
        pdf.set_text_color(*BLACK)
        pdf.set_xy(self.x, y + height)

    def _draw_images(self, cell: Cell, x: float, y: float, width: float, height: float) -> None:
        cx = x + self.pad
        for path, slot, img_w, img_h in self._image_boxes(cell, width - 2 * self.pad):
            if img_h:
                self.pdf.image(
                    str(path), x=cx + (slot - img_w) / 2, y=y + (height - img_h) / 2,
                    w=img_w, h=img_h,
                )  # fmt: skip
            cx += slot + 2.0
