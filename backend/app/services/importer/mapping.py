"""Manual column mapping (plan §4 fallback): import a spreadsheet without the AI.

The seller picks the header row, which column holds the name, price, ERP code …, and the
sheet's category. Each data row becomes the same dict the AI returns, so normalization,
matching, review and commit are shared with the AI path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.errors import ProblemError
from app.models import Category, Import, ImportRow
from app.services.importer import extract_xlsx as xl
from app.services.importer.matcher import jsonable
from app.services.importer.normalize import parse_number, split_erp_codes, to_halfwidth

MODEL = "manual"  # imports.llm_model of a mapped import
TEXT_FIELDS = ("name_en", "brand", "mpn", "notes_raw", "platform")
INT_FIELDS = ("stock_qty", "demand_qty", "stock_after_qty")
FIELDS = (*TEXT_FIELDS, *INT_FIELDS, "erp_code", "price")
SAMPLES = 3
_MONEY_RE = re.compile(r"[$¥￥,\s]|USD|RMB|CNY|元", re.IGNORECASE)


@dataclass
class ColumnMapping:
    sheet: str
    header_row: int  # sheet row number of the header
    category_code: str
    name_columns: list[str]  # joined with spaces into name_zh
    fields: dict[str, str] = field(default_factory=dict)  # field -> column letter
    attributes: dict[str, str] = field(default_factory=dict)  # attribute key -> column
    currency: str = "USD"
    fx_rate: Decimal | None = None


_grids: dict[tuple[str, float, str], xl.SheetGrid] = {}  # openpyxl takes seconds per load


def grid_for(imp: Import, sheet: str) -> xl.SheetGrid:
    """The sheet's grid, cached per file: the dialog asks again for every header row."""
    if imp.file_type not in ("xlsx", "csv"):
        raise ProblemError(409, "import.mapping_spreadsheet", "Only spreadsheets can be mapped")
    path = Path(imp.stored_path)
    key = (str(path), path.stat().st_mtime, sheet)
    if key not in _grids:
        grids = xl.load_grids(path, None if imp.file_type == "csv" else [sheet])
        grid = next((g for g, _ in grids if imp.file_type == "csv" or g.name == sheet), None)
        if grid is None:
            raise ProblemError(422, "import.bad_sheets", "Unknown sheet", sheets=[sheet])
        if len(_grids) >= 8:
            _grids.pop(next(iter(_grids)))
        _grids[key] = grid
    return _grids[key]


def _cells(row: xl.Row) -> dict[str, str]:
    """Column letter -> text."""
    return {re.sub(r"\d+$", "", c.ref): c.value for c in row.cells}


def columns(grid: xl.SheetGrid, header_row: int) -> list[dict[str, Any]]:
    """Each column with its header text and a few sample values under it."""
    header = next((r for r in grid.rows if r.number == header_row), None)
    titles = _cells(header) if header else {}
    below = [_cells(r) for r in grid.rows if r.number > header_row][:20]
    result = []
    for letter in grid.columns:
        samples = [row[letter] for row in below if row.get(letter)][:SAMPLES]
        if titles.get(letter) or samples:
            result.append({"letter": letter, "header": titles.get(letter, ""), "samples": samples})
    return result


def _price(text: str) -> Decimal | None:
    cleaned = _MONEY_RE.sub("", to_halfwidth(text))
    number = parse_number(cleaned) if cleaned else None
    return number if number is not None and number > 0 else None


def _int(text: str) -> int | None:
    number = parse_number(text.replace(",", "")) if text else None
    return int(number) if number is not None and number == number.to_integral_value() else None


def mapped_rows(grid: xl.SheetGrid, mapping: ColumnMapping) -> list[dict[str, Any]]:
    """The data rows below the header, shaped like the AI's output rows."""
    header = next((r for r in grid.rows if r.number == mapping.header_row), None)
    header_cells = _cells(header) if header else {}
    out = []
    for row in grid.rows:
        if row.number <= mapping.header_row:
            continue
        cells = _cells(row)
        if header_cells and all(cells.get(k) == v for k, v in header_cells.items() if v):
            continue  # a repeated header row
        name = " ".join(cells[c] for c in mapping.name_columns if cells.get(c)).strip()
        if not name:
            continue
        get = {key: cells.get(column, "").strip() for key, column in mapping.fields.items()}
        price_text = get.get("price", "")
        amount = _price(price_text)
        prices = []
        if amount is not None:
            prices.append({
                "tier": "standard", "amount": amount, "currency": mapping.currency,
                "column": mapping.fields["price"], "date": None, "original_amount": None,
                "original_currency": None,
                "fx_rate": mapping.fx_rate if mapping.currency == "CNY" else None,
            })  # fmt: skip
        out.append({
            "source_row": row.number,
            "category_code": mapping.category_code,
            "name_zh": name,
            **{key: get.get(key) or None for key in TEXT_FIELDS},
            "erp_codes": split_erp_codes(get.get("erp_code")),
            "attributes": [
                {"key": key, "value": cells[column]}
                for key, column in mapping.attributes.items()
                if cells.get(column)
            ],
            "prices": prices,
            "no_price_reason": (price_text or None) if amount is None else None,
            **{key: _int(get.get(key, "")) for key in INT_FIELDS},
            "confidence": 1.0,
            "issues": [],
        })  # fmt: skip
    return out


def apply(session: Session, imp: Import, mapping: ColumnMapping) -> int:
    """Replace the sheet's rows with the mapped ones and analyze the import again.
    Sheets can be mapped one after the other; each keeps its own rows."""
    if imp.status not in ("uploaded", "review", "failed", "cancelled"):
        raise ProblemError(409, "import.busy", "This import cannot be extracted now")
    if session.scalar(select(Category).where(Category.code == mapping.category_code)) is None:
        raise ProblemError(422, "import.mapping_category", "Pick the sheet's category")
    if not mapping.name_columns:
        raise ProblemError(422, "import.mapping_name", "Pick the column with the product name")
    if "price" not in mapping.fields:
        raise ProblemError(422, "import.mapping_price", "Pick the price column")
    from app.services.importer.pipeline import analyze_import  # circular at import time

    grid = grid_for(imp, mapping.sheet)
    rows = mapped_rows(grid, mapping)
    session.execute(
        delete(ImportRow).where(ImportRow.import_id == imp.id, ImportRow.sheet == grid.name)
    )
    for row in rows:
        number = row["source_row"]
        source = next(r for r in grid.rows if r.number == number)
        session.add(
            ImportRow(
                import_id=imp.id,
                row_index=number,
                sheet=grid.name,
                source_ref=f"{imp.filename}!{grid.name}!{number}",
                raw={c.ref: c.value for c in source.cells if c.value},
                parsed={"source": jsonable(row)},
                confidence=1.0,
            )
        )
    imp.sheets_selected = list(dict.fromkeys([*(imp.sheets_selected or []), grid.name]))
    imp.hints = {**(imp.hints or {}), grid.name: mapping.category_code}
    meta = dict((imp.progress or {}).get("sheet_meta") or {})
    meta[grid.name] = jsonable({"currency": mapping.currency, "fx_rate": mapping.fx_rate,
                                "price_date": None})  # fmt: skip
    empty = {"total_chunks": 0, "done_chunks": 0, "failed_chunks": 0, "errors": []}
    imp.progress = {**empty, **(imp.progress or {}), "sheet_meta": meta}
    imp.llm_model = MODEL
    imp.error = None
    imp.started_at = imp.started_at or datetime.now(UTC)
    analyze_import(session, imp)
    imp.status = "review"
    session.flush()
    return len(rows)
