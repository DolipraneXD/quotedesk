"""Golden tests against the live model APIs (plan §4.3). Opt-in: they cost money.

    QUOTEDESK_LIVE=1 ANTHROPIC_API_KEY=sk-ant-... pytest -m live
    QUOTEDESK_LIVE=1 GEMINI_API_KEY=AIza... pytest -m live

Each test runs once per provider whose key is set; text-only providers skip the screenshots.

They run the real pipeline (prompt, structured output, normalization) on the sample
workbooks and check the rules the plan cares about, not every byte of model output.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from app.config import API_KEY_VARS
from app.services.importer import pipeline
from tests.conftest import FIXTURES

API = "/api/v1"
KEYS = {provider: os.environ.get(var) for provider, var in API_KEY_VARS.items()}
PROVIDERS = [provider for provider, key in KEYS.items() if key]
TEXT_ONLY = {"inception"}

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (os.environ.get("QUOTEDESK_LIVE") == "1" and PROVIDERS),
        reason="set QUOTEDESK_LIVE=1 and ANTHROPIC_API_KEY or GEMINI_API_KEY to run",
    ),
]


@pytest.fixture(params=PROVIDERS or ["anthropic"])
def live(request, client, monkeypatch):
    provider = request.param
    if provider in TEXT_ONLY and request.node.name.startswith("test_screenshots"):
        pytest.skip(f"{provider} reads text only")
    monkeypatch.setenv(API_KEY_VARS[provider], KEYS[provider] or "")
    monkeypatch.setattr(pipeline, "spawn", lambda target: target())
    settings = client.get(f"{API}/settings").json()
    settings["llm_provider"] = provider
    assert client.put(f"{API}/settings", json=settings).status_code == 200
    return client


def run(client, filename: str | list[str], sheets: list[str], hints: dict[str, str]) -> dict:
    names = [filename] if isinstance(filename, str) else filename
    files = [("files", (name, (FIXTURES / name).read_bytes())) for name in names]
    imp = client.post(f"{API}/imports", files=files).json()
    res = client.post(f"{API}/imports/{imp['id']}/extract", json={"sheets": sheets, "hints": hints})
    assert res.status_code == 202, res.json()
    imp = client.get(f"{API}/imports/{imp['id']}").json()
    assert imp["status"] == "review", imp
    assert imp["progress"]["failed_chunks"] == 0, imp["progress"]["errors"]
    return imp


def rows(client, imp: dict) -> dict[tuple[str, int], dict]:
    items = client.get(f"{API}/imports/{imp['id']}/rows", params={"page_size": 1000}).json()
    return {(r["sheet"], r["row_index"]): r["parsed"]["staged"] for r in items["items"]}


def usd(staged: dict, tier: str = "standard") -> Decimal | None:
    found = [p for p in staged["prices"] if p["tier"] == tier]
    return Decimal(found[0]["price_usd"]) if found else None


def test_wifi_workbook(live):
    sheets = ["Intel wifi", "domestic  WIFI", "DDR颗粒参考价", "内存条 参考价", "SSD", "EMMC"]
    hints = {
        "Intel wifi": "wifi", "domestic  WIFI": "wifi", "DDR颗粒参考价": "dram_chip",
        "内存条 参考价": "ram_module", "SSD": "ssd", "EMMC": "emmc",
    }  # fmt: skip
    imp = run(live, "wifi_price_20260929.xlsx", sheets, hints)
    got = rows(live, imp)

    ax101 = got[("Intel wifi", 4)]
    assert ax101["erp_code"] == "E.M.W.0000119"
    assert usd(ax101) == Decimal("3.1")
    assert ax101["fields"]["status"] == "discontinued"
    assert ax101["fields"]["stock_after_qty"] == -49523
    assert got[("Intel wifi", 6)]["prices"] == []  # "-" in the only price column

    # USD column of domestic WIFI excludes VAT: 14.85 CNY / 1.13 / 6.7175
    cdtech = got[("domestic  WIFI", 2)]
    assert cdtech["erp_code"] == "E.M.W.0000167"
    assert usd(cdtech) == Decimal("1.9563")
    assert Decimal(cdtech["prices"][0]["amount_original"]) == Decimal("14.85")
    assert Decimal(cdtech["prices"][0]["fx_rate"]) == Decimal("6.7175")

    # merged LPDDR4X-200 group label reaches rows below the first
    lp = got[("DDR颗粒参考价", 7)]
    assert lp["category_code"] == "dram_chip"
    assert "LPDDR4X" in str(lp["attributes"].get("type", "")).upper()
    assert lp["erp_code"] == "E.I.M.0000536"
    assert usd(lp) == Decimal("16")  # right-most column N (参考价9/19)
    assert got[("DDR颗粒参考价", 3)]["prices"] == []  # right-most is "/"

    ram = got[("内存条 参考价", 4)]
    assert ram["erp_code"] == "E.M.R.0000036"
    assert usd(ram) == Decimal("14.5")
    assert ram["category_code"] == "ram_module"

    ssd = got[("SSD", 3)]
    assert ssd["erp_code"] == "E.M.P.0000389" and usd(ssd) == Decimal("9.2")

    assert got[("EMMC", 3)]["prices"] == []
    assert got[("EMMC", 3)]["fields"]["status"] == "no_supply"
    assert usd(got[("EMMC", 4)]) == Decimal("4.5")  # right-most of two 参考价 columns


def test_motherboard_summary_sheet(live):
    imp = run(live, "motherboard_cost.xlsx", ["DB小板汇总"], {"DB小板汇总": "motherboard"})
    got = rows(live, imp)
    xn21s = got[("DB小板汇总", 3)]
    assert xn21s["category_code"] == "motherboard"
    assert xn21s["attributes"]["model"] == "XN21S"
    assert abs(usd(xn21s) - Decimal("5.0121")) <= Decimal("0.0001")  # TTL
    assert imp["stats"]["total"] > 600


def find(got: dict, sheet: str, **expect) -> dict:
    """The one staged row of ``sheet`` whose attributes / fields contain ``expect``."""

    def matches(staged: dict) -> bool:
        values = {**staged["attributes"], **staged.get("fields", {}), **staged}
        return all(str(values.get(k, "")).upper() == str(v).upper() for k, v in expect.items())

    found = [st for (sh, _), st in got.items() if sh == sheet and matches(st)]
    assert len(found) == 1, (expect, found)
    return found[0]


def test_screenshots(live):
    images = ["img_dram_chips.jpg", "img_ram_modules.jpg", "img_ssd.jpg", "img_cpu.jpg"]
    hints = dict(zip(images, ["dram_chip", "ram_module", "ssd", "cpu"], strict=True))
    imp = run(live, images, images, hints)
    got = rows(live, imp)
    count = {name: sum(1 for sh, _ in got if sh == name) for name in images}
    assert count["img_dram_chips.jpg"] == 6
    assert count["img_ram_modules.jpg"] == 9
    assert count["img_ssd.jpg"] == 17
    assert count["img_cpu.jpg"] >= 85

    # merged LPDDR5/5X-315 group: five rows, and the 16GB one at $210
    chips = [st for (sh, _), st in got.items() if sh == "img_dram_chips.jpg"]
    assert sum("315" in str(c["attributes"].get("package_balls", "")) for c in chips) == 5
    big = find(got, "img_dram_chips.jpg", capacity_gb="16GB")
    assert usd(big) == Decimal("210") and big["brand_name"] == "Yemas"
    assert find(got, "img_dram_chips.jpg", max_order_qty=3700)
    assert find(got, "img_dram_chips.jpg", from_stock_qty=12000)

    # red payment notes on the RAM modules
    asint = find(got, "img_ram_modules.jpg", max_order_qty=13000)
    assert asint["brand_name"] == "Asint" and usd(asint) == Decimal("42")
    assert "预付30%" in asint["fields"]["payment_terms"]

    # SSD: "/" prices and from-stock quantities
    assert sum(1 for (sh, _), st in got.items() if sh == "img_ssd.jpg" and not st["prices"]) == 2
    assert find(got, "img_ssd.jpg", from_stock_qty=1629)["prices"] == []

    # CPU: ERP codes, two tiers, negative stock after orders
    i5 = next(st for (sh, _), st in got.items() if sh == "img_cpu.jpg"
              and st.get("erp_code") == "E.I.P.0000455")  # fmt: skip
    assert usd(i5) == Decimal("154") and usd(i5, "forecast") == Decimal("154")
    ultra = next(st for (sh, _), st in got.items() if sh == "img_cpu.jpg"
                 and st.get("erp_code") == "E.I.P.0000560")  # fmt: skip
    assert usd(ultra) == Decimal("130") and usd(ultra, "forecast") == Decimal("156.5")
    assert ultra["fields"]["stock_after_qty"] == -20323


def test_ups_quotation_pdf(live):
    imp = run(live, "Sixunied_UPS_Quotation.pdf", ["Page 1"], {})
    got = rows(live, imp)
    prices = sorted((st["category_code"], usd(st)) for st in got.values())
    assert prices == [
        ("battery", Decimal("34")), ("battery", Decimal("50")),
        ("cabinet", Decimal("49")), ("cabinet", Decimal("59")),
        ("ups", Decimal("490")), ("ups", Decimal("943")),
    ]  # fmt: skip
    assert imp["stats"]["new"] == 6  # the two cabinets are two products
