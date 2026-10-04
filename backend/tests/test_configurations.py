"""Saved configurations and the dashboard widgets (plan M5)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.models import Import, PriceHistory
from tests.test_quotes import API, add_product, first_line, new_quote, png_bytes, texts


def make_config(client, ups: dict, **extra) -> dict:
    res = client.post(
        f"{API}/configurations",
        json={
            "name": "UPS kit",
            "name_zh": "UPS 套装",
            "model_no": "KIT-10",
            "base_margin_pct": "10",
            "items": [
                {"product_id": ups["id"], "condition": "new"},
                {"name": "Battery 12V24AH", "cost_usd": "21.5", "qty": 2, "emphasis": True},
                {"name": "CE/ROHS"},
            ],
            **extra,
        },
    )
    assert res.status_code == 201, res.json()
    return res.json()


def test_configuration_prices_its_parts_from_the_catalog(client, ups):
    config = make_config(client, ups)
    assert [(i["name"], i["unit_cost"]) for i in config["items"]] == [
        ("SP10KS", "400.0000"), ("Battery 12V24AH", "21.5000"), ("CE/ROHS", None),
    ]  # fmt: skip
    assert config["unit_cost"] == "443.0000" and config["saved_cost"] == "443.0000"
    assert config["missing_cost"] == 1 and not config["cost_changed"]
    assert config["description_lines"] == [
        {"text": "SP10KS (New)", "emphasis": False},
        {"text": "2*Battery 12V24AH", "emphasis": True},
        {"text": "CE/ROHS", "emphasis": False},
    ]

    # a catalog price change moves the cost; saving accepts it
    client.post(f"{API}/products/{ups['id']}/prices", json={"price_usd": "420"})
    config = client.get(f"{API}/configurations/{config['id']}").json()
    assert config["unit_cost"] == "463.0000" and config["cost_changed"]
    [summary] = client.get(f"{API}/configurations", params={"q": "kit-10"}).json()
    assert summary["cost_changed"] and summary["parts"] == 3
    config = client.patch(f"{API}/configurations/{config['id']}", json={}).json()
    assert config["saved_cost"] == "463.0000" and not config["cost_changed"]

    copy = client.post(f"{API}/configurations/{config['id']}/duplicate").json()
    assert copy["name"] == "UPS kit (copy)" and len(copy["items"]) == 3

    photo = client.post(
        f"{API}/configurations/{config['id']}/images", files={"files": ("a.png", png_bytes())}
    ).json()
    assert len(photo["image_ids"]) == 1
    empty = client.patch(f"{API}/configurations/{config['id']}", json={"name": " "})
    assert empty.status_code == 422


def test_insert_configuration_into_quote_and_where_used(client, customer, ups):
    config = make_config(client, ups)
    quote = new_quote(client, customer_id=customer["id"])
    quote = client.patch(f"{API}/quotes/{quote['id']}", json={"language": "zh"}).json()
    res = client.post(
        f"{API}/quotes/{quote['id']}/lines",
        json={"section_id": quote["sections"][0]["id"], "configuration_id": config["id"],
              "qty": 10},
    )  # fmt: skip
    assert res.status_code == 201, res.json()
    line = first_line(res.json())
    assert line["kind"] == "config" and line["name"] == "UPS 套装" and line["model_no"] == "KIT-10"
    assert line["cost_usd"] == "443.0000" and line["margin_pct"] == "10.0000"
    assert line["unit_price"] == "487.3000"
    assert texts(line) == ["SP10KS (全新)", "2*Battery 12V24AH", "CE/ROHS"]
    assert line["description_lines"][1]["emphasis"] is True

    usage = client.get(f"{API}/configurations/{config['id']}/usage").json()
    assert [(u["display_no"], u["qty"]) for u in usage] == [(quote["display_no"], 10)]
    assert client.get(f"{API}/configurations/{config['id']}").json()["used_in"] == 1

    # deleting the configuration leaves the quote as it was
    assert client.delete(f"{API}/configurations/{config['id']}").status_code == 204
    line = first_line(client.get(f"{API}/quotes/{quote['id']}").json())
    assert line["kind"] == "config" and len(line["components"]) == 3


def test_save_combined_line_as_configuration(client, ups):
    quote = add_product(client, new_quote(client), ups, qty=4)
    quote = client.post(
        f"{API}/quotes/{quote['id']}/lines",
        json={"section_id": quote["sections"][0]["id"], "name": "Bag", "cost_usd": "3", "qty": 4},
    ).json()
    ids = [line["id"] for line in quote["sections"][0]["lines"]]
    quote = client.post(
        f"{API}/quotes/{quote['id']}/lines/combine", json={"line_ids": ids, "name": "Kit"}
    ).json()
    line = first_line(quote)
    res = client.post(
        f"{API}/configurations/from-line", json={"quote_id": quote["id"], "line_id": line["id"]}
    )
    assert res.status_code == 201, res.json()
    config = res.json()
    assert config["name"] == "Kit" and config["unit_cost"] == "403.0000" and config["used_in"] == 1
    assert [(i["product_id"], i["name"]) for i in config["items"]] == [
        (ups["id"], "SP10KS"), (None, "Bag"),
    ]  # fmt: skip


# --------------------------------------------------------------- dashboard


def test_dashboard_widgets(client, session, customer, ups, categories):
    dash = client.get(f"{API}/dashboard").json()
    assert dash["last_import"] is None and dash["price_moves"] == []
    assert dash["open_quotes"]["count"] == 0

    quote = add_product(client, new_quote(client, customer_id=customer["id"]), ups, qty=2)
    client.post(f"{API}/products/{ups['id']}/prices", json={"price_usd": "520"})
    old = client.post(
        f"{API}/products",
        json={"category_id": categories["ups"]["id"], "name_zh": "旧UPS", "attributes": {},
              "price_usd": "100", "price_date": str(date.today() - timedelta(days=90))},
    ).json()  # fmt: skip

    # an import that moved the UPS price from 520 to 300 (-42 %)
    imp = Import(filename="ups.xlsx", stored_path="x", file_type="xlsx",
                 committed_at=datetime.now(UTC), stats={"new": 0, "updated": 1})  # fmt: skip
    session.add(imp)
    session.flush()
    session.add(PriceHistory(product_id=ups["id"], import_id=imp.id, price_usd=Decimal("300")))
    session.commit()

    dash = client.get(f"{API}/dashboard").json()
    assert dash["last_import"]["filename"] == "ups.xlsx" and dash["last_import"]["updated"] == 1
    [move] = dash["price_moves"]
    assert move["product_id"] == ups["id"] and move["pct"] == "-42.3"
    assert dash["open_quotes"]["count"] == 1
    assert dash["open_quotes"]["value"] == quote["grand_total"]
    [alert] = dash["quote_alerts"]
    assert alert["code"] == "price_changed" and alert["quote_id"] == quote["id"]
    assert dash["old_prices"]["count"] == 1
    assert dash["old_prices"]["oldest"][0]["product_id"] == old["id"]
