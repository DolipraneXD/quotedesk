"""Screenshot and PDF imports (plan M3), replayed offline with recorded model output."""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from PIL import Image

from app.services.importer import extract_media as media
from app.services.importer import pipeline
from tests.conftest import FIXTURES
from tests.importer_fakes import FakeExtractor

API = "/api/v1"
IMAGES = ["img_dram_chips.jpg", "img_ram_modules.jpg", "img_ssd.jpg", "img_cpu.jpg"]
PDF = "Sixunied_UPS_Quotation.pdf"


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeExtractor:
    extractor = FakeExtractor()
    monkeypatch.setattr(pipeline, "make_extractor", lambda session: extractor)
    monkeypatch.setattr(pipeline, "spawn", lambda target: target())
    return extractor


def upload(client, *names: str, status: int = 201) -> dict:
    files = [("files", (name, (FIXTURES / name).read_bytes())) for name in names]
    res = client.post(f"{API}/imports", files=files)
    assert res.status_code == status, res.json()
    return res.json()


def extract(client, imp: dict, sheets: list[str], hints: dict | None = None) -> dict:
    res = client.post(
        f"{API}/imports/{imp['id']}/extract", json={"sheets": sheets, "hints": hints or {}}
    )
    assert res.status_code == 202, res.json()
    return client.get(f"{API}/imports/{imp['id']}").json()


def staged_rows(client, imp: dict) -> dict[tuple[str, int], dict]:
    res = client.get(f"{API}/imports/{imp['id']}/rows", params={"page_size": 1000})
    return {(r["sheet"], r["row_index"]): r for r in res.json()["items"]}


def usd(row: dict, tier: str = "standard") -> str | None:
    found = [p for p in row["parsed"]["staged"]["prices"] if p["tier"] == tier]
    return found[0]["price_usd"] if found else None


# ------------------------------------------------------------------ upload


def test_several_screenshots_are_one_import(client, fake):
    imp = upload(client, *IMAGES)
    assert imp["filename"] == "img_dram_chips.jpg (+3)"
    assert imp["file_type"] == "image"
    assert [s["name"] for s in imp["sheets"]] == IMAGES
    cpu = imp["sheets"][3]
    assert cpu["kind"] == "image" and cpu["preselected"] is True
    assert (cpu["width"], cpu["height"]) == (1215, 1600)

    res = client.get(f"{API}/imports/{imp['id']}/sources/3/image")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert res.content == (FIXTURES / "img_cpu.jpg").read_bytes()
    assert client.get(f"{API}/imports/{imp['id']}/sources/9/image").status_code == 404


def test_pdf_upload_lists_pages_with_text_preview(client, fake):
    imp = upload(client, PDF)
    assert imp["file_type"] == "pdf"
    [page] = imp["sheets"]
    assert page["name"] == "Page 1" and page["kind"] == "pdf_page"
    assert page["scanned"] is False and page["rows"] == 36
    assert page["preview"][0] == ["Shenzhen Sixunited technology Co.,Ltd"]

    res = client.get(f"{API}/imports/{imp['id']}/sources/0/image")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(res.content)) as img:
        assert img.size == (1275, 1650)  # US letter at 150 dpi


def test_upload_rules_for_mixed_and_broken_files(client, fake):
    files = [
        ("files", ("prices.xlsx", (FIXTURES / "wifi_price_20260929.xlsx").read_bytes())),
        ("files", ("img_cpu.jpg", (FIXTURES / "img_cpu.jpg").read_bytes())),
    ]
    res = client.post(f"{API}/imports", files=files)
    assert res.status_code == 422 and res.json()["key"] == "import.one_spreadsheet"

    res = client.post(f"{API}/imports", files={"files": ("shot.png", b"not an image")})
    assert res.status_code == 422 and res.json()["key"] == "import.unreadable"
    res = client.post(f"{API}/imports", files={"files": ("quote.pdf", b"%PDF-1.4 broken")})
    assert res.status_code == 422 and res.json()["key"] == "import.unreadable"

    # an image and a PDF together: pages are named after their file
    files = [
        ("files", (PDF, (FIXTURES / PDF).read_bytes())),
        ("files", ("img_ssd.jpg", (FIXTURES / "img_ssd.jpg").read_bytes())),
    ]
    imp = client.post(f"{API}/imports", files=files).json()
    assert imp["file_type"] == "media"
    assert [s["name"] for s in imp["sheets"]] == [f"{PDF} p1", "img_ssd.jpg"]


def test_same_file_name_twice_gets_a_suffix(client, fake):
    data = (FIXTURES / "img_ssd.jpg").read_bytes()
    files = [("files", ("shot.jpg", data)), ("files", ("shot.jpg", data))]
    imp = client.post(f"{API}/imports", files=files).json()
    assert [s["name"] for s in imp["sheets"]] == ["shot.jpg", "shot.jpg (2)"]


# -------------------------------------------------------------- extraction


def test_screenshots_are_sent_as_images(client, fake):
    imp = upload(client, *IMAGES)
    imp = extract(client, imp, IMAGES, {"img_cpu.jpg": "cpu"})
    assert imp["status"] == "review"
    assert imp["progress"]["total_chunks"] == 4
    ctx = next(c for c in fake.calls if c.sheet == "img_cpu.jpg")
    assert ctx.kind == "image" and ctx.body == "" and ctx.category_hint == "cpu"
    assert ctx.max_tokens == 64000
    [image] = ctx.images
    assert image.media_type == "image/jpeg"
    assert image.data == (FIXTURES / "img_cpu.jpg").read_bytes()  # small enough to send as is


def test_screenshot_rows_golden(client, fake):
    """Plan §4.3 expectations for the four screenshots."""
    imp = extract(client, upload(client, *IMAGES), IMAGES)
    rows = staged_rows(client, imp)

    # DRAM chips: the merged LPDDR5/5X-315 group reaches all five rows
    chips = [rows[("img_dram_chips.jpg", n)]["parsed"]["staged"] for n in range(1, 7)]
    assert [c["attributes"]["type"] for c in chips[:5]] == ["LPDDR5/5X"] * 5
    assert chips[5]["attributes"]["package_balls"] == "496"
    assert chips[0]["fields"]["max_order_qty"] == 3700
    assert chips[1]["fields"]["from_stock_qty"] == 12000
    assert chips[2]["brand_name"] == "Yemas"  # "yemas" resolves to the same brand
    assert usd(rows[("img_dram_chips.jpg", 5)]) == "210.0000"
    assert (
        len({r["parsed"]["target_key"] for k, r in rows.items() if k[0] == "img_dram_chips.jpg"})
        == 6
    )

    # RAM modules: red payment notes, Chinese brand names resolved
    asint = rows[("img_ram_modules.jpg", 1)]["parsed"]["staged"]
    assert asint["brand_name"] == "Asint"
    assert asint["fields"]["max_order_qty"] == 13000
    assert asint["fields"]["payment_terms"] == "可接13K,预付30%，尾款到发货"
    kingfast = rows[("img_ram_modules.jpg", 2)]["parsed"]["staged"]
    assert kingfast["brand_name"] == "Kingfast"
    assert kingfast["fields"]["payment_terms"] == "预付30%，尾款开支票30天"
    assert (
        rows[("img_ram_modules.jpg", 9)]["parsed"]["staged"]["attributes"]["chip_vendor"] == "长鑫"
    )

    # SSD: "/" prices, from-stock quantities, the note above the table
    airdisk = rows[("img_ssd.jpg", 1)]
    assert airdisk["parsed"]["staged"]["prices"] == []
    assert airdisk["parsed"]["staged"]["no_price_reason"] == "/"
    assert airdisk["parsed"]["staged"]["fields"]["from_stock_qty"] == 1629
    assert {"code": "llm", "text": airdisk["parsed"]["source"]["issues"][0]} in airdisk["issues"]
    assert rows[("img_ssd.jpg", 14)]["parsed"]["staged"]["fields"]["needs_validation"] is True
    assert rows[("img_ssd.jpg", 9)]["parsed"]["staged"]["fields"]["max_order_qty"] == 50000
    assert rows[("img_ssd.jpg", 1)]["raw"] == {}  # the review shows the image instead

    # CPU: two price tiers, negative stock after orders, notes
    i5 = rows[("img_cpu.jpg", 1)]["parsed"]["staged"]
    assert i5["erp_code"] == "E.I.P.0000455"
    assert (usd(rows[("img_cpu.jpg", 1)]), usd(rows[("img_cpu.jpg", 1)], "forecast")) == (
        "154.0000",
        "154.0000",
    )
    ultra = rows[("img_cpu.jpg", 36)]
    assert (usd(ultra), usd(ultra, "forecast")) == ("130.0000", "156.5000")
    assert ultra["parsed"]["staged"]["fields"]["stock_after_qty"] == -20323
    only_standard = rows[("img_cpu.jpg", 35)]
    assert (usd(only_standard), usd(only_standard, "forecast")) == ("118.0000", None)
    no_price = rows[("img_cpu.jpg", 3)]["parsed"]["staged"]
    assert no_price["prices"] == [] and no_price["fields"]["lead_time_confirm"] is True
    assert rows[("img_cpu.jpg", 12)]["parsed"]["staged"]["fields"]["status"] == "discontinued"
    no_erp = rows[("img_cpu.jpg", 56)]
    assert no_erp["status"] == "new" and no_erp["parsed"]["staged"]["erp_code"] is None


def test_pdf_page_is_sent_as_numbered_text_and_image(client, fake):
    imp = extract(client, upload(client, PDF), ["Page 1"])
    ctx = fake.calls[0]
    assert ctx.kind == "pdf_page"
    assert "L11 |         1      SP10KS" in ctx.body
    assert ctx.body.splitlines()[0].startswith("L01 | ")
    [page] = ctx.images
    assert page.media_type == "image/png" and page.data[:4] == b"\x89PNG"
    assert imp["status"] == "review"


def test_pdf_golden_six_products(client, fake):
    """UPS quotation -> 6 products in ups / battery / cabinet with unit prices."""
    imp = extract(client, upload(client, PDF), ["Page 1"])
    rows = staged_rows(client, imp)
    got = {
        r["parsed"]["staged"]["attributes"]["model"]: (
            r["parsed"]["staged"]["category_code"],
            usd(r),
        )
        for r in rows.values()
    }
    assert got == {
        "SP10KS": ("ups", "490.0000"),
        "12V24AH": ("battery", "34.0000"),
        "C6": ("cabinet", "49.0000"),
        "SP20KS": ("ups", "943.0000"),
        "12V38AH": ("battery", "50.0000"),
        "C8": ("cabinet", "59.0000"),
    }
    assert rows[("Page 1", 11)]["raw"] == {
        "L11": "1      SP10KS                                   20 490         9,800"
    }
    assert rows[("Page 1", 11)]["parsed"]["staged"]["prices"][0]["price_date"] == "2026-08-11"

    res = client.post(f"{API}/imports/{imp['id']}/commit")
    assert res.status_code == 200, res.json()
    assert res.json()["stats"]["committed"]["new"] == 6
    ups = client.get(f"{API}/products", params={"q": "SP20KS"}).json()["items"][0]
    assert Decimal(ups["current_price_usd"]) == Decimal("943")
    history = client.get(f"{API}/products/{ups['id']}/prices").json()
    assert history[0]["source_ref"] == f"{PDF}!Page 1!E"


def test_scanned_pdf_page_goes_to_vision(client, fake, tmp_path):
    scan = tmp_path / "scan.pdf"
    Image.open(FIXTURES / "img_dram_chips.jpg").convert("RGB").save(scan, "PDF", resolution=150)
    files = {"files": ("scan.pdf", scan.read_bytes())}
    imp = client.post(f"{API}/imports", files=files).json()
    assert imp["sheets"][0]["scanned"] is True
    fake.recorded["Page 1"] = []
    extract(client, imp, ["Page 1"])
    ctx = fake.calls[0]
    assert ctx.kind == "image" and ctx.body == "" and len(ctx.images) == 1


def test_one_failed_screenshot_does_not_stop_the_others(client, fake):
    fake.fail_sheets = {"img_ssd.jpg"}
    imp = extract(client, upload(client, *IMAGES), IMAGES)
    assert imp["status"] == "review"
    assert imp["progress"]["errors"] == [
        {"sheet": "img_ssd.jpg", "rows": "", "message": "simulated failure"}
    ]


# ------------------------------------------------------------- image prep


def test_large_images_are_downscaled_before_sending():
    big = io.BytesIO()
    Image.new("RGBA", (5000, 1200), (255, 255, 255, 0)).save(big, "PNG")
    prepared = media.prepare_image(big.getvalue(), "image/png")
    assert prepared.media_type == "image/jpeg"
    with Image.open(io.BytesIO(prepared.data)) as img:
        assert max(img.size) == media.MAX_IMAGE_EDGE

    small = (FIXTURES / "img_ssd.jpg").read_bytes()
    assert media.prepare_image(small, "image/jpeg").data == small
