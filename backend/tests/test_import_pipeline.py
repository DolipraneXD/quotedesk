"""Import pipeline end to end through the API, with recorded model output (no network)."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from app.errors import ProblemError
from app.services.importer import extract_xlsx as xl
from app.services.importer import pipeline
from tests.conftest import FIXTURES
from tests.importer_fakes import RECORDED, FakeExtractor, price, row

API = "/api/v1"
WIFI = FIXTURES / "wifi_price_20260929.xlsx"
BOARDS = FIXTURES / "motherboard_cost.xlsx"
WIFI_SHEETS = ["Intel wifi", "domestic  WIFI", "内存条 参考价"]

_real_load_grids = xl.load_grids
_grid_cache: dict[tuple[str, tuple[str, ...] | None], list] = {}


def cached_load_grids(path: Path, sheets: list[str] | None = None):
    key = (hashlib.sha1(Path(path).read_bytes()).hexdigest(), tuple(sheets) if sheets else None)
    if key not in _grid_cache:
        _grid_cache[key] = _real_load_grids(path, sheets)
    return _grid_cache[key]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeExtractor:
    extractor = FakeExtractor()
    monkeypatch.setattr(xl, "load_grids", cached_load_grids)
    monkeypatch.setattr(pipeline, "make_extractor", lambda session: extractor)
    monkeypatch.setattr(pipeline, "spawn", lambda target: target())  # run inline
    return extractor


def upload(client, path: Path, name: str | None = None) -> dict:
    with open(path, "rb") as fh:
        res = client.post(f"{API}/imports", files={"files": (name or path.name, fh)})
    assert res.status_code == 201, res.json()
    return res.json()


def extract(client, imp: dict, sheets: list[str], hints: dict | None = None) -> dict:
    res = client.post(
        f"{API}/imports/{imp['id']}/extract", json={"sheets": sheets, "hints": hints or {}}
    )
    assert res.status_code == 202, res.json()
    return client.get(f"{API}/imports/{imp['id']}").json()


def rows_of(client, imp: dict, **params) -> list[dict]:
    res = client.get(f"{API}/imports/{imp['id']}/rows", params={"page_size": 1000, **params})
    return res.json()["items"]


def by_row(rows: list[dict], sheet: str, number: int) -> dict:
    return next(r for r in rows if r["sheet"] == sheet and r["row_index"] == number)


def run_wifi_import(client) -> dict:
    imp = upload(client, WIFI)
    return extract(client, imp, WIFI_SHEETS, {"Intel wifi": "wifi"})


# ------------------------------------------------------------------ upload


def test_upload_lists_sheets_with_preselection(client, fake):
    imp = upload(client, WIFI)
    sheets = {s["name"]: s for s in imp["sheets"]}
    assert imp["status"] == "uploaded"
    assert len(sheets) == 13
    assert sheets["Intel wifi"]["preselected"] is True
    assert sheets["Intel wifi"]["header_row"] == 3
    assert sheets["DDR颗粒参考价"]["hidden"] is True
    assert sheets["DDR颗粒参考价"]["preselected"] is False  # hidden sheets are opt-in
    assert len(sheets["domestic  WIFI"]["preview"]) == xl.PREVIEW_ROWS


def test_upload_motherboard_sheet7_not_preselected(client, fake):
    imp = upload(client, BOARDS)
    sheets = {s["name"]: s for s in imp["sheets"]}
    assert sheets["Sheet7"]["preselected"] is False
    assert sheets["DB小板汇总"]["preselected"] is True
    assert sheets["DB小板汇总"]["fx_rate"] == "6.71"
    assert sheets["DB小板汇总"]["currency"] == "USD"


def test_upload_rejects_xls_and_unknown_types(client, fake):
    res = client.post(f"{API}/imports", files={"files": ("old.xls", b"\xd0\xcf\x11\xe0")})
    assert res.status_code == 415 and res.json()["key"] == "import.xls_unsupported"
    res = client.post(f"{API}/imports", files={"files": ("notes.txt", b"hello")})
    assert res.status_code == 415 and res.json()["key"] == "import.unsupported_type"


def test_upload_unreadable_workbook(client, fake):
    res = client.post(f"{API}/imports", files={"files": ("broken.xlsx", b"not a zip")})
    assert res.status_code == 422 and res.json()["key"] == "import.unreadable"


def test_csv_upload(client, fake, tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("型号,品牌,参考价,备注\nAX210,Intel,6.5,供应良好\n", encoding="utf-8")
    imp = upload(client, path)
    assert imp["file_type"] == "csv"
    assert imp["sheets"][0]["preselected"] is True
    assert imp["sheets"][0]["header_row"] == 1


# --------------------------------------------------------------- extraction


def test_extract_without_api_key_is_refused(client, monkeypatch):
    monkeypatch.setattr(xl, "load_grids", cached_load_grids)
    imp = upload(client, WIFI)
    res = client.post(f"{API}/imports/{imp['id']}/extract", json={"sheets": ["Intel wifi"]})
    assert res.status_code == 409 and res.json()["key"] == "import.no_api_key"


def test_make_extractor_follows_the_provider(client, session, monkeypatch):
    from app.config import load_settings, save_settings
    from app.services.importer.llm_parser import ClaudeExtractor, GeminiExtractor

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert isinstance(pipeline.make_extractor(session), ClaudeExtractor)
    settings = load_settings()
    settings.llm_provider = "google"
    save_settings(settings)
    with pytest.raises(ProblemError) as exc:
        pipeline.make_extractor(session)
    assert exc.value.params == {"provider": "google"}
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    extractor = pipeline.make_extractor(session)
    assert isinstance(extractor, GeminiExtractor) and extractor.model == "gemini-3.8-flash"


def test_extract_rejects_unknown_sheet(client, fake):
    imp = upload(client, WIFI)
    res = client.post(f"{API}/imports/{imp['id']}/extract", json={"sheets": ["Nope"]})
    assert res.status_code == 422 and res.json()["key"] == "import.bad_sheets"


def test_extraction_sends_hints_and_grid(client, fake):
    run_wifi_import(client)
    intel_ctx = next(c for c in fake.calls if c.sheet == "Intel wifi")
    assert intel_ctx.category_hint == "wifi"
    assert intel_ctx.file_date == "2026-09-29"
    assert "| 4 | WIFI | CNVI | E.M.W.0000119 |" in intel_ctx.body
    assert "D: ERP料号" in intel_ctx.body


def test_extraction_reaches_review_with_counts_and_tokens(client, fake):
    imp = run_wifi_import(client)
    assert imp["status"] == "review"
    # domestic WIFI has 77 data rows: two chunks of at most 60
    assert imp["progress"]["total_chunks"] == 4
    assert imp["progress"]["done_chunks"] == 4
    assert imp["progress"]["sheets"]["domestic  WIFI"] == {"total": 2, "done": 2}
    assert imp["stats"]["total"] == len(RECORDED["Intel wifi"]) + 4 + 3
    assert imp["stats"]["new"] == imp["stats"]["total"]
    assert imp["llm_tokens_in"] == 4000
    assert imp["llm_model"] == "fake-model"


def test_staged_rows_golden(client, fake):
    """Plan §4.3 expectations on the normalized rows."""
    imp = run_wifi_import(client)
    rows = rows_of(client, imp)

    discontinued = by_row(rows, "Intel wifi", 4)["parsed"]["staged"]
    assert discontinued["erp_code"] == "E.M.W.0000119"
    assert discontinued["fields"]["status"] == "discontinued"
    assert discontinued["fields"]["confirm_before_order"] is True
    assert discontinued["fields"]["stock_after_qty"] == -49523
    assert discontinued["prices"][0]["price_usd"] == "3.1000"
    assert discontinued["brand_name"] == "Intel"
    assert by_row(rows, "Intel wifi", 4)["raw"]["C4"] == "CNVI"  # merged group filled

    no_price = by_row(rows, "Intel wifi", 6)["parsed"]["staged"]
    assert no_price["prices"] == []
    assert no_price["fields"]["status"] == "stock_only"

    # domestic WIFI: the sheet's own USD (VAT-free) column, original CNY + rate kept
    cdtech = by_row(rows, "domestic  WIFI", 2)["parsed"]["staged"]
    assert cdtech["prices"][0]["price_usd"] == "1.9563"
    assert cdtech["prices"][0]["amount_original"] == "14.85"
    assert cdtech["prices"][0]["currency_original"] == "CNY"
    assert cdtech["prices"][0]["fx_rate"] == "6.7175"
    assert cdtech["brand_name"] == "CDTech"  # 中龙通（cdtech） resolved through aliases
    assert cdtech["fields"]["market"] == "consumer"
    assert cdtech["prices"][0]["source_ref"].endswith("domestic  WIFI!M")

    ram = by_row(rows, "内存条 参考价", 4)["parsed"]["staged"]
    assert ram["erp_code"] == "E.M.R.0000036"
    assert ram["prices"][0]["price_date"] == "2026-09-29"  # from the file name
    assert ram["attributes"]["capacity_gb"] == "8GB"


def test_cny_price_without_usd_column_is_converted(client, fake):
    fake.recorded["Intel wifi"] = [
        row(4, "wifi", "国产网卡", attributes={"chipset": "X1", "module_model": "X1-M"},
            prices=[{"tier": "standard", "amount": Decimal("14.85"), "currency": "CNY",
                     "column": "F", "date": None, "original_amount": None,
                     "original_currency": None, "fx_rate": Decimal("6.7175")}]),
    ]  # fmt: skip
    imp = upload(client, WIFI)
    imp = extract(client, imp, ["Intel wifi"])
    staged = rows_of(client, imp)[0]["parsed"]["staged"]
    assert staged["prices"][0]["price_usd"] == "2.2106"  # 14.85 / 6.7175 = 2.21064…
    assert staged["prices"][0]["currency_original"] == "CNY"


def test_cny_without_any_rate_uses_settings_default(client, fake):
    fake.recorded["Intel wifi"] = [
        row(4, "wifi", "国产网卡", attributes={"chipset": "X1", "module_model": "X1-M"},
            prices=[{"tier": "standard", "amount": Decimal("71"), "currency": "CNY",
                     "column": "F", "date": None, "original_amount": None,
                     "original_currency": None, "fx_rate": None}]),
    ]  # fmt: skip
    imp = upload(client, WIFI)
    imp = extract(client, imp, ["Intel wifi"])
    found = rows_of(client, imp)[0]
    assert found["parsed"]["staged"]["prices"][0]["price_usd"] == "10.0000"  # 71 / 7.10
    assert {"code": "default_fx", "rate": "7.10"} in found["issues"]


def test_duplicates_within_import_last_row_wins(client, fake):
    imp = upload(client, BOARDS)
    imp = extract(client, imp, ["DB小板汇总"], {"DB小板汇总": "motherboard"})
    rows = rows_of(client, imp)
    xn35 = [r for r in rows if r["parsed"]["staged"]["attributes"]["model"] == "XN35"]
    assert [r["row_index"] for r in xn35] == [601, 602, 603]
    assert [r["decision"] for r in xn35] == ["skip", "skip", "create"]
    assert xn35[0]["issues"][-1]["code"] == "duplicate_in_import"
    assert imp["stats"]["to_apply"] == 4  # XN21S, DA1021C, XN21, last XN35


def xn35(n: int, erp: str | None, ttl: str) -> dict:
    # what a weaker model returns: the model name only, no SKU
    return row(n, "motherboard", "XN35 主板", erp_codes=[erp] if erp else [],
               attributes={"model": "XN35"}, prices=[price(ttl, "L")])  # fmt: skip


def test_rows_with_different_erp_codes_are_never_duplicates(client, fake):
    fake.recorded["DB小板汇总"] = [
        xn35(3, "A.F.D.2600382", "2.2884"),
        xn35(4, "A.F.D.2600398", "2.3884"),
        xn35(5, None, "2.5"),  # no code: same product as the first code
        xn35(601, "A.F.D.2600326", "2.6084"),
    ]
    imp = extract(client, upload(client, BOARDS), ["DB小板汇总"])
    rows = {r["row_index"]: r for r in rows_of(client, imp)}
    assert {n: r["decision"] for n, r in rows.items()} == {
        3: "skip",
        4: "create",
        5: "create",
        601: "create",
    }
    assert rows[3]["issues"][-1] == {"code": "duplicate_in_import", "row": "DB小板汇总!5"}
    assert {"code": "erp_variant", "product": "XN35 主板"} in rows[4]["issues"]

    res = client.post(f"{API}/imports/{imp['id']}/commit")
    assert res.status_code == 200, res.json()
    found = client.get(f"{API}/products", params={"q": "XN35", "page_size": 10}).json()["items"]
    assert sorted((p["erp_code"], p["current_price_usd"]) for p in found) == [
        ("A.F.D.2600326", "2.6084"),
        ("A.F.D.2600382", "2.5000"),
        ("A.F.D.2600398", "2.3884"),
    ]


def test_same_specs_with_another_erp_code_is_not_an_update(client, fake):
    fake.recorded["DB小板汇总"] = [xn35(3, "A.F.D.2600382", "2.2884")]
    first = extract(client, upload(client, BOARDS), ["DB小板汇总"])
    assert client.post(f"{API}/imports/{first['id']}/commit").status_code == 200

    fake.recorded["DB小板汇总"] = [xn35(3, "A.F.D.2600398", "9.99")]
    second = extract(client, upload(client, BOARDS), ["DB小板汇总"])
    [found] = rows_of(client, second)
    assert found["status"] == "new" and found["matched_product_id"] is None
    assert {"code": "erp_variant", "product": "XN35 主板"} in found["issues"]
    assert client.post(f"{API}/imports/{second['id']}/commit").status_code == 200
    old = client.get(f"{API}/products", params={"q": "A.F.D.2600382"}).json()["items"][0]
    assert old["current_price_usd"] == "2.2884"  # untouched


def test_two_codes_matching_one_uncoded_product(client, fake):
    fake.recorded["DB小板汇总"] = [xn35(3, None, "2")]
    first = extract(client, upload(client, BOARDS), ["DB小板汇总"])
    assert client.post(f"{API}/imports/{first['id']}/commit").status_code == 200

    fake.recorded["DB小板汇总"] = [xn35(3, "A.F.D.2600382", "3"), xn35(4, "A.F.D.2600398", "4")]
    second = extract(client, upload(client, BOARDS), ["DB小板汇总"])
    rows = {r["row_index"]: r for r in rows_of(client, second)}
    assert rows[3]["decision"] == "update"
    assert rows[4]["decision"] == "skip"
    assert {"code": "erp_conflict", "product": "XN35 主板"} in rows[4]["issues"]


def test_overlong_chunks_are_split(client, fake):
    fake.max_rows = 10  # the Intel sheet chunk has 21 data rows
    imp = upload(client, WIFI)
    imp = extract(client, imp, ["Intel wifi"])
    assert imp["status"] == "review"
    assert len(rows_of(client, imp)) == len(RECORDED["Intel wifi"])
    assert len(fake.calls) > 1


def test_failed_chunk_is_reported_but_others_continue(client, fake):
    fake.fail_sheets = {"内存条 参考价"}
    imp = run_wifi_import(client)
    assert imp["status"] == "review"
    assert imp["progress"]["failed_chunks"] == 1
    assert imp["progress"]["errors"][0]["sheet"] == "内存条 参考价"
    assert imp["progress"]["errors"][0]["message"] == "simulated failure"


def test_all_chunks_failing_marks_import_failed(client, fake):
    fake.fail_sheets = {"Intel wifi"}
    imp = upload(client, WIFI)
    imp = extract(client, imp, ["Intel wifi"])
    assert imp["status"] == "failed"
    assert imp["error"] == "simulated failure"


def test_unknown_category_is_a_problem_row(client, fake):
    fake.recorded["Intel wifi"] = [row(4, "smartwatch", "智能手表")]
    imp = upload(client, WIFI)
    imp = extract(client, imp, ["Intel wifi"])
    found = rows_of(client, imp)[0]
    assert found["status"] == "problem" and found["decision"] == "skip"
    assert found["issues"][-1] == {"code": "unknown_category", "category": "smartwatch"}


# ------------------------------------------------------------------- review


def test_row_filters_and_counts(client, fake):
    imp = run_wifi_import(client)
    res = client.get(f"{API}/imports/{imp['id']}/rows", params={"sheet": "Intel wifi"}).json()
    assert res["total"] == 8 and res["counts"] == {"new": 8}
    res = client.get(f"{API}/imports/{imp['id']}/rows", params={"q": "E.M.R.0000036"}).json()
    assert res["total"] == 1
    res = client.get(f"{API}/imports/{imp['id']}/rows", params={"category": "ram_module"}).json()
    assert res["total"] == 3


def test_edit_row_reanalyzes(client, fake):
    imp = run_wifi_import(client)
    target = by_row(rows_of(client, imp), "Intel wifi", 6)
    res = client.patch(
        f"{API}/imports/{imp['id']}/rows/{target['id']}",
        json={"edits": {"price_usd": "4.25", "name_zh": "Intel AX200 (edited)"}},
    )
    assert res.status_code == 200, res.json()
    staged = res.json()["parsed"]["staged"]
    assert staged["prices"][0]["price_usd"] == "4.25"
    assert staged["name_zh"] == "Intel AX200 (edited)"
    # removing an edit restores the extracted value
    res = client.patch(
        f"{API}/imports/{imp['id']}/rows/{target['id']}", json={"edits": {"price_usd": None}}
    )
    assert res.json()["parsed"]["staged"]["prices"] == []


def test_edit_rejects_unknown_fields_and_categories(client, fake):
    imp = run_wifi_import(client)
    row_id = rows_of(client, imp)[0]["id"]
    res = client.patch(f"{API}/imports/{imp['id']}/rows/{row_id}", json={"edits": {"x": 1}})
    assert res.status_code == 422 and res.json()["key"] == "import.bad_edit"
    res = client.patch(
        f"{API}/imports/{imp['id']}/rows/{row_id}", json={"edits": {"category_code": "nope"}}
    )
    assert res.status_code == 422


def test_bulk_set_category_and_skip(client, fake):
    imp = run_wifi_import(client)
    rows = rows_of(client, imp, sheet="内存条 参考价")
    ids = [r["id"] for r in rows]
    res = client.post(
        f"{API}/imports/{imp['id']}/bulk",
        json={"action": "set_category", "row_ids": ids, "category_code": "dram_chip"},
    )
    assert res.status_code == 200
    rows = rows_of(client, imp, sheet="内存条 参考价")
    assert {r["parsed"]["staged"]["category_code"] for r in rows} == {"dram_chip"}
    res = client.post(f"{API}/imports/{imp['id']}/bulk", json={"action": "skip", "row_ids": ids})
    assert res.json()["to_apply"] == 12  # 15 rows minus the 3 skipped
    assert {r["decision"] for r in rows_of(client, imp, sheet="内存条 参考价")} == {"skip"}


# ---------------------------------------------------------- commit / revert


def test_commit_creates_products_with_traceable_prices(client, fake):
    imp = run_wifi_import(client)
    res = client.post(f"{API}/imports/{imp['id']}/commit")
    assert res.status_code == 200, res.json()
    committed = res.json()
    assert committed["status"] == "committed"
    assert committed["stats"]["committed"]["new"] == 15

    products = client.get(f"{API}/products", params={"page_size": 100}).json()
    assert products["total"] == 15
    ax101 = client.get(f"{API}/products", params={"q": "E.M.W.0000119"}).json()["items"][0]
    assert ax101["status"] == "discontinued"
    assert ax101["confirm_before_order"] is True
    assert ax101["last_import_id"] == imp["id"]
    assert ax101["brand"]["canonical"] == "Intel"
    assert ax101["name_en_auto"] is True

    cdtech = client.get(f"{API}/products", params={"q": "E.M.W.0000167"}).json()["items"][0]
    history = client.get(f"{API}/products/{cdtech['id']}/prices").json()
    assert len(history) == 1
    assert history[0]["import_id"] == imp["id"]
    assert Decimal(history[0]["price_usd"]) == Decimal("1.9563")
    assert Decimal(history[0]["amount_original"]) == Decimal("14.85")
    assert history[0]["currency_original"] == "CNY"
    assert Decimal(history[0]["fx_rate"]) == Decimal("6.7175")
    assert history[0]["source_ref"] == "wifi_price_20260929.xlsx!domestic  WIFI!M"

    no_price = client.get(f"{API}/products", params={"q": "E.M.W.0000067"}).json()["items"][0]
    assert no_price["current_price_usd"] is None


def test_products_remember_the_import_that_added_them(client, fake, session):
    imp = run_wifi_import(client)
    assert client.post(f"{API}/imports/{imp['id']}/commit").status_code == 200
    ax101 = client.get(f"{API}/products", params={"q": "E.M.W.0000119"}).json()["items"][0]
    assert ax101["created_import_id"] == imp["id"]
    assert ax101["created_import"]["filename"] == "wifi_price_20260929.xlsx"
    assert ax101["created_import"]["committed_at"] is not None
    assert ax101["last_import"]["id"] == imp["id"]

    manual = client.post(
        f"{API}/products",
        json={"category_id": ax101["category_id"], "name_zh": "手工网卡", "attributes": {}},
    ).json()
    assert manual["created_import"] is None

    newest = client.get(f"{API}/products", params={"sort": "created", "order": "desc"}).json()
    assert newest["items"][0]["id"] == manual["id"]

    # the migration fills the column for products imported before it existed
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    from app.migrate import BACKEND_DIR

    session.execute(text("UPDATE products SET created_import_id = NULL"))
    session.commit()
    history = session.scalar(text("SELECT count(*) FROM price_history"))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logging"] = False
    command.downgrade(cfg, "0002")  # rebuilds the products table
    command.upgrade(cfg, "head")
    session.expire_all()
    assert session.scalar(text("SELECT count(*) FROM price_history")) == history
    assert (
        session.scalar(
            text("SELECT count(*) FROM products WHERE created_import_id = :id"), {"id": imp["id"]}
        )
        == 15
    )
    assert session.scalar(text("SELECT created_import_id FROM products WHERE id = :id"),
                          {"id": manual["id"]}) is None  # fmt: skip
    fks = session.execute(text("PRAGMA foreign_key_list(products)")).all()
    assert ("imports", "created_import_id", "SET NULL") in {(f[2], f[3], f[6]) for f in fks}


def test_unknown_brand_is_created_for_review_and_removed_on_revert(client, fake):
    fake.recorded = {"Intel wifi": [
        row(4, "wifi", "某网卡", brand="新品牌（NewCo）",
            attributes={"chipset": "Z1", "module_model": "Z1-M"}),
    ]}  # fmt: skip
    imp = upload(client, WIFI)
    imp = extract(client, imp, ["Intel wifi"])
    found = rows_of(client, imp)[0]
    assert {"code": "new_brand", "brand": "新品牌（NewCo）"} in found["issues"]
    client.post(f"{API}/imports/{imp['id']}/commit")
    brands = {b["canonical"]: b for b in client.get(f"{API}/brands").json()}
    assert brands["NewCo"]["name_zh"] == "新品牌"
    assert brands["NewCo"]["needs_review"] is True
    client.post(f"{API}/imports/{imp['id']}/revert")
    assert "NewCo" not in {b["canonical"] for b in client.get(f"{API}/brands").json()}


def test_second_import_matches_by_erp_and_last_upload_wins(client, fake):
    first = run_wifi_import(client)
    client.post(f"{API}/imports/{first['id']}/commit")

    for r in fake.recorded["内存条 参考价"]:
        if r["source_row"] == 4:
            r["prices"][0]["amount"] = Decimal("20")  # 14.5 -> 20: +37.9 %
    second = run_wifi_import(client)
    rows = rows_of(client, second)
    # rows without an ERP code fall back to the manufacturer part number
    assert {r["match_type"] for r in rows} == {"erp", "mpn"}
    changed = by_row(rows, "内存条 参考价", 4)
    assert changed["status"] == "updated" and changed["decision"] == "update"
    diff = changed["parsed"]["staged"]["diff"]["prices"]["standard"]
    assert diff == {"old": "14.5000", "new": "20.0000", "pct": "37.9"}
    assert {"code": "price_swing", "pct": "37.9"} in changed["issues"]
    assert by_row(rows, "Intel wifi", 4)["status"] == "unchanged"
    assert second["stats"]["unchanged"] == 14

    res = client.post(f"{API}/imports/{second['id']}/commit")
    assert res.json()["stats"]["committed"] == {
        "new": 0, "updated": 1, "unchanged": 14, "skipped": 0,
    }  # fmt: skip
    ram = client.get(f"{API}/products", params={"q": "E.M.R.0000036"}).json()["items"][0]
    assert Decimal(ram["current_price_usd"]) == Decimal("20")
    history = client.get(f"{API}/products/{ram['id']}/prices").json()
    assert [h["is_current"] for h in history] == [True, False]

    # the first import can't be reverted while the newer one is committed
    res = client.post(f"{API}/imports/{first['id']}/revert")
    assert res.status_code == 409 and res.json()["key"] == "import.not_latest"

    res = client.post(f"{API}/imports/{second['id']}/revert")
    assert res.json()["status"] == "reverted"
    ram = client.get(f"{API}/products/{ram['id']}").json()
    assert Decimal(ram["current_price_usd"]) == Decimal("14.5")
    assert len(client.get(f"{API}/products/{ram['id']}/prices").json()) == 1

    res = client.post(f"{API}/imports/{first['id']}/revert")
    assert res.json()["status"] == "reverted"
    assert client.get(f"{API}/products").json()["total"] == 0


def test_revert_keeps_products_with_manual_prices(client, fake):
    imp = run_wifi_import(client)
    client.post(f"{API}/imports/{imp['id']}/commit")
    ram = client.get(f"{API}/products", params={"q": "E.M.R.0000036"}).json()["items"][0]
    client.post(f"{API}/products/{ram['id']}/prices", json={"price_usd": "15"})
    client.post(f"{API}/imports/{imp['id']}/revert")
    kept = client.get(f"{API}/products/{ram['id']}")
    assert kept.status_code == 200
    assert Decimal(kept.json()["current_price_usd"]) == Decimal("15")


def test_update_keeps_manual_deactivation_and_restores_fields_on_revert(client, fake):
    first = run_wifi_import(client)
    client.post(f"{API}/imports/{first['id']}/commit")
    ram = client.get(f"{API}/products", params={"q": "E.M.R.0000036"}).json()["items"][0]
    client.patch(f"{API}/products/{ram['id']}", json={"status": "inactive", "name_en": "Mine"})

    for r in fake.recorded["内存条 参考价"]:
        if r["source_row"] == 4:
            r["stock_qty"] = 500
    second = run_wifi_import(client)
    client.post(f"{API}/imports/{second['id']}/commit")
    after = client.get(f"{API}/products/{ram['id']}").json()
    assert after["status"] == "inactive"  # imports never re-activate a manual deactivation
    assert after["stock_qty"] == 500

    client.post(f"{API}/imports/{second['id']}/revert")
    restored = client.get(f"{API}/products/{ram['id']}").json()
    assert restored["stock_qty"] is None
    assert restored["name_en"] == "Mine"


def test_possible_match_must_be_decided(client, fake):
    cat = {c["code"]: c for c in client.get(f"{API}/categories").json()}
    existing = client.post(
        f"{API}/products",
        json={
            "category_id": cat["ram_module"]["id"],
            "name_zh": "DDR4 8GB 2666MHZ 沃存 海力士颗粒",
            "attributes": {"type": "DDR4", "capacity_gb": "8GB"},
        },
    ).json()
    fake.recorded = {"Intel wifi": [
        row(4, "ram_module", "DDR4 8GB 2666MHZ 沃存 海力士颗粒 ",
            attributes={"type": "DDR4", "capacity_gb": "8GB", "speed_mhz": "2666"},
            prices=RECORDED["内存条 参考价"][1]["prices"]),
    ]}  # fmt: skip
    imp = upload(client, WIFI)
    imp = extract(client, imp, ["Intel wifi"])
    found = rows_of(client, imp)[0]
    assert found["status"] == "possible_match"
    assert found["candidates"][0]["product_id"] == existing["id"]
    assert found["decision"] is None

    res = client.post(f"{API}/imports/{imp['id']}/commit")
    assert res.status_code == 409 and res.json()["key"] == "import.undecided"

    res = client.patch(
        f"{API}/imports/{imp['id']}/rows/{found['id']}",
        json={"edits": {"match_product_id": existing["id"]}},
    )
    decided = res.json()
    assert decided["match_type"] == "manual"
    assert decided["status"] == "updated" and decided["decision"] == "update"

    assert client.post(f"{API}/imports/{imp['id']}/commit").status_code == 200
    updated = client.get(f"{API}/products/{existing['id']}").json()
    assert Decimal(updated["current_price_usd"]) == Decimal("14.5")
    assert updated["attributes"]["speed_mhz"] == "2666"


def test_possible_match_can_become_new(client, fake):
    cat = {c["code"]: c for c in client.get(f"{API}/categories").json()}
    client.post(
        f"{API}/products",
        json={"category_id": cat["wifi"]["id"], "name_zh": "Intel AX210 网卡 PCIE",
              "attributes": {"chipset": "AX210"}},
    )  # fmt: skip
    fake.recorded = {"Intel wifi": [
        row(4, "wifi", "Intel AX210 网卡 PCIE",
            attributes={"chipset": "AX210", "module_model": "B"}),
    ]}  # fmt: skip
    imp = upload(client, WIFI)
    imp = extract(client, imp, ["Intel wifi"])
    found = rows_of(client, imp)[0]
    assert found["status"] == "possible_match"
    res = client.patch(
        f"{API}/imports/{imp['id']}/rows/{found['id']}", json={"edits": {"force_new": True}}
    )
    assert res.json()["status"] == "new" and res.json()["decision"] == "create"
    client.post(f"{API}/imports/{imp['id']}/commit")
    assert client.get(f"{API}/products").json()["total"] == 2


def test_commit_and_delete_rules(client, fake):
    imp = run_wifi_import(client)
    client.post(f"{API}/imports/{imp['id']}/commit")
    assert client.post(f"{API}/imports/{imp['id']}/commit").status_code == 409
    assert client.delete(f"{API}/imports/{imp['id']}").status_code == 409
    client.post(f"{API}/imports/{imp['id']}/revert")
    assert client.delete(f"{API}/imports/{imp['id']}").status_code == 204
    assert client.get(f"{API}/imports/{imp['id']}").status_code == 404


def test_cancel_only_while_extracting(client, fake, session):
    imp = upload(client, WIFI)
    res = client.post(f"{API}/imports/{imp['id']}/cancel")
    assert res.status_code == 409
    from app.models import Import

    record = session.get(Import, imp["id"])
    record.status = "extracting"
    session.commit()
    res = client.post(f"{API}/imports/{imp['id']}/cancel")
    assert res.json()["status"] == "cancelled"


def test_list_imports(client, fake):
    run_wifi_import(client)
    listed = client.get(f"{API}/imports").json()
    assert len(listed) == 1 and listed[0]["status"] == "review"
