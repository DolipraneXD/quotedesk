"""Manual column mapping: importing a spreadsheet without the AI (plan §4, M6)."""

from __future__ import annotations

from tests.test_import_pipeline import API, WIFI, upload

WIFI_MAPPING = {
    "sheet": "Intel wifi",
    "header_row": 3,
    "category_code": "wifi",
    "name_columns": ["B", "E"],
    "fields": {"erp_code": "D", "mpn": "E", "price": "F", "stock_qty": "G", "demand_qty": "H",
               "stock_after_qty": "I", "notes_raw": "J"},
    "attributes": {"interface": "C", "module_model": "E"},
}  # fmt: skip


def rows(client, imp: dict) -> list[dict]:
    return client.get(f"{API}/imports/{imp['id']}/rows", params={"page_size": 200}).json()["items"]


def test_columns_show_header_and_samples(client):
    imp = upload(client, WIFI)
    cols = client.get(
        f"{API}/imports/{imp['id']}/columns", params={"sheet": "Intel wifi", "header_row": 3}
    ).json()
    by_letter = {c["letter"]: c for c in cols}
    assert by_letter["D"]["header"] == "ERP料号"
    assert by_letter["F"]["samples"] == ["3.1", "3.1", "-"]


def test_map_columns_then_commit_without_any_api_key(client):
    imp = upload(client, WIFI)
    # no key is configured in tests: the AI path refuses, the mapping works
    refused = client.post(
        f"{API}/imports/{imp['id']}/extract", json={"sheets": ["Intel wifi"], "hints": {}}
    )
    assert refused.status_code == 409

    res = client.post(f"{API}/imports/{imp['id']}/map", json=WIFI_MAPPING)
    assert res.status_code == 200, res.json()
    imp = res.json()
    assert imp["status"] == "review" and imp["llm_model"] == "manual"

    items = rows(client, imp)
    ax101 = next(r for r in items if "E.M.W.0000119" in (r["parsed"]["source"]["erp_codes"]))
    source = ax101["parsed"]["source"]
    assert source["name_zh"] == "WIFI AX101.NGWG.NV,999CV1"
    assert source["prices"][0]["amount"] == "3.1" and source["stock_qty"] == 1734
    assert source["stock_after_qty"] == -49523 and source["notes_raw"] == "已停产，接单前确认"
    assert "E.M.W.0000119" in ax101["raw"].values()
    no_price = next(r for r in items if r["parsed"]["source"]["prices"] == [])
    assert no_price["parsed"]["source"]["no_price_reason"] == "-"

    # mapping the sheet again replaces its rows instead of adding to them
    again = client.post(f"{API}/imports/{imp['id']}/map", json=WIFI_MAPPING).json()
    assert len(rows(client, again)) == len(items)

    committed = client.post(f"{API}/imports/{imp['id']}/commit")
    assert committed.status_code == 200, committed.json()
    product = client.get(f"{API}/products", params={"q": "E.M.W.0000119"}).json()["items"][0]
    assert product["current_price_usd"] == "3.1000" and product["stock_qty"] == 1734


def test_mapping_needs_name_price_and_category(client):
    imp = upload(client, WIFI)
    bad = {**WIFI_MAPPING, "fields": {"erp_code": "D"}}
    res = client.post(f"{API}/imports/{imp['id']}/map", json=bad)
    assert res.status_code == 422 and res.json()["key"] == "import.mapping_price"
    res = client.post(f"{API}/imports/{imp['id']}/map", json={**WIFI_MAPPING, "category_code": "x"})
    assert res.json()["key"] == "import.mapping_category"
