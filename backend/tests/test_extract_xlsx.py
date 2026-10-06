"""Deterministic pre-extraction on the real sample workbooks (no AI involved)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.importer import extract_xlsx as xl
from tests.conftest import FIXTURES


@pytest.fixture(scope="module")
def wifi() -> dict[str, tuple[xl.SheetGrid, bool]]:
    return {g.name: (g, h) for g, h in xl.load_grids(FIXTURES / "wifi_price_20260929.xlsx")}


@pytest.fixture(scope="module")
def boards() -> dict[str, tuple[xl.SheetGrid, bool]]:
    return {g.name: (g, h) for g, h in xl.load_grids(FIXTURES / "motherboard_cost.xlsx")}


def cell(grid: xl.SheetGrid, ref: str) -> str:
    for row in grid.rows:
        for c in row.cells:
            if c.ref == ref:
                return c.value
    raise KeyError(ref)


def test_used_range_ignores_formatted_empty_rows(wifi, boards):
    # these sheets claim 1,048,576 rows because of formatting
    assert len(wifi["DDR颗粒参考价"][0].rows) == 30
    assert len(wifi["SSD"][0].rows) == 9
    assert len(boards["E BOM大核 (2)"][0].rows) < 2000


def test_merged_cells_are_filled_down(wifi):
    intel = wifi["Intel wifi"][0]
    assert cell(intel, "C5") == "CNVI"  # C4:C5
    assert cell(intel, "C14") == "PCIE"  # C6:C14
    assert cell(intel, "B24") == "WIFI"  # B3:B24
    ddr = wifi["DDR颗粒参考价"][0]
    assert cell(ddr, "B10") == "LPDDR4X-200"  # B6:B10


def test_header_detection(wifi, boards):
    assert wifi["Intel wifi"][0].header.number == 3
    assert wifi["domestic  WIFI"][0].header.number == 1
    assert wifi["DDR颗粒参考价"][0].header.number == 2
    assert wifi["内存条 参考价"][0].header.number == 2
    assert boards["DB小板汇总"][0].header.number == 2
    assert boards["高通"][0].header.number == 3


def test_title_metadata(boards):
    db = boards["DB小板汇总"][0]
    assert db.meta.currency == "USD" and db.meta.fx_rate == Decimal("6.71")
    assert boards["E BOM大核"][0].meta.fx_rate == Decimal("6.71")  # "9月汇率：6.71" by the header
    assert boards["高通"][0].meta.fx_rate == Decimal("6.71")
    assert boards["AMD"][0].meta.fx_rate == Decimal("6.75")


def test_values_are_rendered_stably(wifi, boards):
    assert cell(wifi["Intel wifi"][0], "F4") == "3.1"
    assert cell(wifi["Intel wifi"][0], "I4") == "-49523"
    assert cell(wifi["domestic  WIFI"][0], "L2") == "6.7175"
    assert cell(wifi["domestic  WIFI"][0], "A2") == "WIFI5 / 1T1R"  # newline inside a cell
    assert cell(boards["DB小板汇总"][0], "B3") == "2026-02-28"  # datetime -> ISO date


def test_preselection(wifi, boards):
    def pre(sheets, name):
        grid, hidden = sheets[name]
        return xl.summarize(grid, hidden).preselected

    assert pre(wifi, "Intel wifi") and pre(wifi, "domestic  WIFI")
    assert pre(boards, "DB小板汇总")
    assert not pre(boards, "Sheet7")  # personal notes
    assert not pre(boards, "Sheet8")  # empty
    assert not pre(wifi, "DDR颗粒参考价")  # hidden: listed, but opt-in


def test_chunks_repeat_header_and_cap_rows(boards):
    db = boards["DB小板汇总"][0]
    chunks = xl.chunk_grid(db)
    assert len(chunks) == 12  # 672 data rows / 60
    assert all(len(c.rows) <= xl.CHUNK_ROWS for c in chunks)
    assert sum(len(c.rows) for c in chunks) == len(db.data_rows)
    text = xl.render_chunk(chunks[5])
    assert "Header is row 2." in text
    assert "| row | A: 机型 | B: 日期 |" in text
    assert "Title rows above the header:" in text and "E1=币种:USD" in text


def test_render_escapes_pipes():
    grid = xl.SheetGrid(
        "s",
        ["A", "B"],
        [
            xl.Row(1, [xl.Cell("A1", "型号"), xl.Cell("B1", "价格")]),
            xl.Row(2, [xl.Cell("A2", "a|b"), xl.Cell("B2", "1")]),
        ],
        0,
    )
    assert "| 2 | a\\|b | 1 |" in xl.render_chunk(xl.chunk_grid(grid)[0])


def test_date_from_filename():
    assert xl.date_from_filename("wifi_price_20260929.xlsx") == date(2026, 9, 29)
    assert xl.date_from_filename("prices 2026-09-28.xlsx") == date(2026, 9, 28)
    assert xl.date_from_filename("motherboard_cost.xlsx") is None
    assert xl.date_from_filename("x_20261399.xlsx") is None
