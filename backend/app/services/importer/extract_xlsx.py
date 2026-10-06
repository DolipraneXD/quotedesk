"""Deterministic spreadsheet pre-extraction (plan §4.1 steps 2 and 4, no AI).

Turns a worksheet into a clean grid: real used range only (sheets often claim a
million formatted rows), merged cells forward-filled, empty rows/columns dropped,
header row detected, title-row metadata (exchange rate, currency) read, and data
rows sliced into chunks for the LLM.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.services.importer.normalize import to_halfwidth

CHUNK_ROWS = 60
PREVIEW_ROWS = 15
HEADER_SCAN_ROWS = 8

PRICE_HEADER_RE = re.compile(r"价|price|参考|报价|WK\s*\d+|\d+\s*月|TTL|币种", re.IGNORECASE)
FX_RE = re.compile(r"汇率\s*[:：]?\s*(\d+(?:\.\d+)?)")
CURRENCY_RE = re.compile(r"币种\s*[:：]?\s*(USD|USA|RMB|CNY|人民币|美金|美元)", re.IGNORECASE)
FILE_DATE_RE = re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})")

CURRENCY_MAP = {"usd": "USD", "usa": "USD", "美金": "USD", "美元": "USD"}


@dataclass
class Cell:
    ref: str  # "B5"
    value: str  # rendered text, merged values filled in


@dataclass
class Row:
    number: int  # 1-based sheet row
    cells: list[Cell]

    def text(self) -> str:
        return " ".join(c.value for c in self.cells if c.value)


@dataclass
class SheetMeta:
    currency: str | None = None
    fx_rate: Decimal | None = None
    title_text: str = ""


@dataclass
class SheetGrid:
    name: str
    columns: list[str]  # column letters kept, in order
    rows: list[Row]  # non-empty rows of the used range
    header_index: int | None  # index into rows
    meta: SheetMeta = field(default_factory=SheetMeta)

    @property
    def header(self) -> Row | None:
        return self.rows[self.header_index] if self.header_index is not None else None

    @property
    def data_rows(self) -> list[Row]:
        start = (self.header_index + 1) if self.header_index is not None else 0
        return self.rows[start:]

    @property
    def title_rows(self) -> list[Row]:
        return self.rows[: self.header_index] if self.header_index else []


@dataclass
class SheetSummary:
    name: str
    hidden: bool
    rows: int
    columns: int
    looks_like_price_table: bool
    preselected: bool
    header_row: int | None
    currency: str | None
    fx_rate: str | None
    preview: list[list[str]]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "sheet", **self.__dict__}


def render_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0) else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        # repr keeps every digit Excel stored; trim float noise beyond 10 places
        text = f"{value:.10f}".rstrip("0").rstrip(".")
        return text if text not in ("-0", "") else "0"
    text = str(value).replace("\r", "")
    return re.sub(r"[ \t]*\n[ \t]*", " / ", text.strip())


def _used_cells(ws: Worksheet) -> dict[tuple[int, int], Any]:
    """Only cells that hold a value. ``ws._cells`` avoids iterating a sheet whose
    formatting extends to row 1,048,576, which ``iter_rows`` would materialize."""
    return {
        key: cell.value
        for key, cell in ws._cells.items()  # noqa: SLF001
        if cell.value is not None and str(cell.value).strip() != ""
    }


def sheet_grid(ws: Worksheet) -> SheetGrid:
    values = _used_cells(ws)
    # Forward-fill merged ranges from their top-left cell.
    for merged in ws.merged_cells.ranges:
        anchor = values.get((merged.min_row, merged.min_col))
        if anchor is None:
            continue
        for r in range(merged.min_row, merged.max_row + 1):
            for c in range(merged.min_col, merged.max_col + 1):
                values.setdefault((r, c), anchor)
    if not values:
        return SheetGrid(ws.title, [], [], None)

    col_numbers = sorted({c for _, c in values})
    row_numbers = sorted({r for r, _ in values})
    rows = []
    for r in row_numbers:
        cells = [
            Cell(f"{get_column_letter(c)}{r}", render_value(values.get((r, c))))
            for c in col_numbers
        ]
        rows.append(Row(r, cells))
    grid = SheetGrid(ws.title, [get_column_letter(c) for c in col_numbers], rows, None)
    grid.header_index = detect_header(grid.rows)
    grid.meta = read_meta(_meta_rows(grid))
    return grid


def _meta_rows(grid: SheetGrid) -> list[Row]:
    # title rows plus the header row itself: "9月汇率：6.71" often sits beside the labels
    end = (grid.header_index or 0) + 1 if grid.header_index is not None else 0
    return grid.rows[:end]


def _is_number(text: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", text))


def detect_header(rows: list[Row]) -> int | None:
    """The first row (among the first few) that is mostly short text labels.

    A row mentioning a price keyword wins over an earlier plain-text row, since
    title rows ("9月汇率：6.71") also tend to be text.
    """
    best: int | None = None
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        filled = [c.value for c in row.cells if c.value]
        if len(filled) < 3:
            continue
        texts = [v for v in filled if not _is_number(v) and len(v) <= 40]
        if len(texts) / len(filled) < 0.6:
            continue
        if any(PRICE_HEADER_RE.search(v) for v in texts):
            return i
        if best is None:
            best = i
    return best


def read_meta(title_rows: list[Row]) -> SheetMeta:
    text = " ".join(r.text() for r in title_rows)
    meta = SheetMeta(title_text=text[:500])
    fx = FX_RE.search(to_halfwidth(text))
    if fx:
        meta.fx_rate = Decimal(fx.group(1))
    currency = CURRENCY_RE.search(text)
    if currency:
        meta.currency = CURRENCY_MAP.get(currency.group(1).lower(), "CNY")
    if meta.fx_rate is None:
        # "6.71" alone in a title row next to "币种:USD" is the sheet's exchange rate
        for row in title_rows:
            numbers = [c.value for c in row.cells if _is_number(c.value)]
            if len(numbers) == 1 and 5 < Decimal(numbers[0]) < 9:
                meta.fx_rate = Decimal(numbers[0])
                break
    return meta


def looks_like_price_table(grid: SheetGrid) -> bool:
    if grid.header is None or len(grid.data_rows) < 1:
        return False
    head = [c.value for r in grid.rows[: (grid.header_index or 0) + 1] for c in r.cells]
    return any(PRICE_HEADER_RE.search(v) for v in head if v)


def summarize(grid: SheetGrid, hidden: bool) -> SheetSummary:
    price_like = looks_like_price_table(grid)
    return SheetSummary(
        name=grid.name,
        hidden=hidden,
        rows=len(grid.rows),
        columns=len(grid.columns),
        looks_like_price_table=price_like,
        preselected=price_like and not hidden,
        header_row=grid.header.number if grid.header else None,
        currency=grid.meta.currency,
        fx_rate=str(grid.meta.fx_rate) if grid.meta.fx_rate is not None else None,
        preview=[[c.value for c in row.cells] for row in grid.rows[:PREVIEW_ROWS]],
    )


def load_grids(path: Path, sheets: list[str] | None = None) -> list[tuple[SheetGrid, bool]]:
    """(grid, hidden) for every sheet, or only the named ones, in workbook order."""
    if path.suffix.lower() == ".csv":
        return [(csv_grid(path), False)]
    wb = load_workbook(path, data_only=True)
    try:
        out = []
        for ws in wb.worksheets:
            if sheets is not None and ws.title not in sheets:
                continue
            out.append((sheet_grid(ws), ws.sheet_state != "visible"))
        return out
    finally:
        wb.close()


def csv_grid(path: Path) -> SheetGrid:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    records = list(csv.reader(text.splitlines()))
    width = max((len(r) for r in records), default=0)
    columns = [get_column_letter(i + 1) for i in range(width)]
    rows = [
        Row(n, [Cell(f"{columns[i]}{n}", render_value(v)) for i, v in enumerate(rec)])
        for n, rec in enumerate(records, start=1)
        if any(v.strip() for v in rec)
    ]
    grid = SheetGrid(path.stem, columns, rows, None)
    grid.header_index = detect_header(rows)
    grid.meta = read_meta(_meta_rows(grid))
    return grid


def date_from_filename(name: str) -> date | None:
    match = FILE_DATE_RE.search(name)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


@dataclass
class Chunk:
    sheet: str
    index: int
    rows: list[Row]
    header: Row | None
    title_rows: list[Row]
    meta: SheetMeta

    @property
    def row_numbers(self) -> list[int]:
        return [r.number for r in self.rows]


def chunk_grid(grid: SheetGrid, size: int = CHUNK_ROWS) -> list[Chunk]:
    data = grid.data_rows
    return [
        Chunk(grid.name, i // size, data[i : i + size], grid.header, grid.title_rows, grid.meta)
        for i in range(0, len(data), size)
    ]


def _cell_text(value: str) -> str:
    return value.replace("|", "\\|")


def render_chunk(chunk: Chunk) -> str:
    """Markdown grid with cell references, header repeated on every chunk."""
    lines = []
    if chunk.title_rows:
        lines.append("Title rows above the header:")
        for row in chunk.title_rows:
            filled = [f"{c.ref}={_cell_text(c.value)}" for c in row.cells if c.value]
            lines.append("  " + "; ".join(filled))
        lines.append("")
    columns = [re.sub(r"\d+$", "", c.ref) for c in (chunk.rows[0].cells if chunk.rows else [])]
    header_cells = chunk.header.cells if chunk.header else []
    labels = [
        f"{col}: {_cell_text(header_cells[i].value)}" if i < len(header_cells) else col
        for i, col in enumerate(columns)
    ]
    if chunk.header:
        lines.append(f"Header is row {chunk.header.number}.")
    lines.append("| row | " + " | ".join(labels) + " |")
    lines.append("|" + "---|" * (len(labels) + 1))
    for row in chunk.rows:
        lines.append(
            f"| {row.number} | " + " | ".join(_cell_text(c.value) for c in row.cells) + " |"
        )
    return "\n".join(lines)
