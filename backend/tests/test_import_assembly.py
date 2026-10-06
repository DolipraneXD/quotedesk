"""A complete unit imported with its parts (整机成本 BOM): products + one configuration."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.importer import assembly, pipeline
from tests.conftest import FIXTURES
from tests.importer_fakes import TABLET, FakeExtractor

API = "/api/v1"
BOM = "img_tablet_bom.png"


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeExtractor:
    extractor = FakeExtractor()
    monkeypatch.setattr(pipeline, "make_extractor", lambda session: extractor)
    monkeypatch.setattr(pipeline, "spawn", lambda target: target())
    return extractor


def imported(client) -> dict:
    files = [("files", (BOM, (FIXTURES / BOM).read_bytes()))]
    imp = client.post(f"{API}/imports", files=files).json()
    res = client.post(f"{API}/imports/{imp['id']}/extract", json={"sheets": [BOM], "hints": {}})
    assert res.status_code == 202, res.json()
    return client.get(f"{API}/imports/{imp['id']}").json()


def staged(client, imp: dict) -> list[dict]:
    items = client.get(f"{API}/imports/{imp['id']}/rows", params={"page_size": 100}).json()
    return [r["parsed"]["staged"] | {"issues": r["issues"]} for r in items["items"]]


def test_parts_expand_with_the_units_own_rmb_per_usd():
    unit = {
        "source_row": 1, "name_zh": "X1 整机", "confidence": 0.9,
        "attributes": [{"key": "model", "value": "X1"}],
        "prices": [  # RMB cost and USD price returned as two prices of one tier
            {"tier": "standard", "currency": "CNY", "amount": Decimal("1141.53"),
             "fx_rate": Decimal("6.7175"), "date": "2026-09-28"},
            {"tier": "standard", "currency": "USD", "amount": Decimal("150.38")},
        ],
        "parts": [
            {"label": "电池", "spec": "8000mAh", "category_code": "battery",
             "amount": Decimal("62.22"), "generic": False},
            {"label": "TP", "spec": "/", "category_code": "other", "amount": None,
             "generic": False},
            {"label": "其他", "spec": "组装费", "category_code": "service",
             "amount": Decimal("31"), "generic": True},
        ],
    }  # fmt: skip
    out = assembly.expand_parts(unit)
    assert [r["assembly_role"] for r in out] == ["unit", "part", "part"]
    assert unit["prices"] == [
        {"tier": "standard", "currency": "USD", "amount": Decimal("150.38"),
         "original_amount": Decimal("1141.53"), "original_currency": "CNY",
         "fx_rate": Decimal("6.7175"), "date": "2026-09-28"},
    ]  # fmt: skip
    battery, service = out[1], out[2]
    assert battery["name_zh"] == "电池 8000mAh" and battery["source_row"] == 1
    assert battery["prices"][0]["fx_rate"] == Decimal("7.590970")  # 1141.53 / 150.38, VAT incl.
    assert battery["prices"][0]["date"] == "2026-09-28"
    assert service["name_zh"] == "其他 组装费 (X1)"  # generic: kept apart per unit
    assert unit["parts_total"] == {"parts": "93.22", "unit": "1141.53"}  # a misread part
    plain = {"name_zh": "DDR4 8GB", "parts": [], "prices": []}
    assert assembly.expand_parts(plain) == [plain]


def test_unit_and_parts_become_products_and_a_configuration(client, fake):
    imp = imported(client)
    rows = staged(client, imp)
    assert imp["stats"]["new"] == 13
    unit = next(r for r in rows if r["assembly_role"] == "unit")
    assert unit["category_code"] == "tablet" and unit["prices"][0]["price_usd"] == "150.3800"
    assert {"code": "assembly_unit", "unit": TABLET} in unit["issues"]
    assert not any(i["code"] == "parts_total" for i in unit["issues"])  # they add up
    parts = [r for r in rows if r["assembly_role"] == "part"]
    assert len(parts) == 12
    battery = next(p for p in parts if p["category_code"] == "battery")
    assert battery["name_zh"] == "电池 3.8V/8000mAh 不带电量计,带BIS认证"
    assert any(p["name_zh"] == f"其他 组装费+材料运费分摊 ({TABLET})" for p in parts)
    assert battery["prices"][0]["fx_rate"] == "7.590970"
    assert {"code": "unit_fx", "unit": TABLET, "rate": "7.590970"} in battery["issues"]
    total = sum(Decimal(p["prices"][0]["price_usd"]) for p in parts)
    assert abs(total - Decimal("150.38")) < Decimal("0.001")  # the parts add up to the unit

    assert client.post(f"{API}/imports/{imp['id']}/commit").status_code == 200
    configs = client.get(f"{API}/configurations").json()
    assert len(configs) == 1
    config = client.get(f"{API}/configurations/{configs[0]['id']}").json()
    assert config["model_no"] == TABLET and config["name_zh"] == f"{TABLET} 整机"
    assert len(config["items"]) == 12 and all(i["product_id"] for i in config["items"])
    assert abs(Decimal(config["unit_cost"]) - Decimal("150.38")) < Decimal("0.001")

    # importing the same BOM again refreshes that configuration instead of adding one
    again = imported(client)
    assert client.post(f"{API}/imports/{again['id']}/commit").status_code == 200
    assert len(client.get(f"{API}/configurations").json()) == 1
    assert client.post(f"{API}/imports/{again['id']}/revert").status_code == 200
    assert len(client.get(f"{API}/configurations/{config['id']}").json()["items"]) == 12

    assert client.post(f"{API}/imports/{imp['id']}/revert").status_code == 200
    assert client.get(f"{API}/configurations").json() == []
    assert client.get(f"{API}/products").json()["total"] == 0
