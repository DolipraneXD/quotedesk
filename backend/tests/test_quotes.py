"""Customers, quotes, documents and proforma invoices (plan M4)."""

from __future__ import annotations

import io
from datetime import date, timedelta
from decimal import Decimal

import pdfplumber
from openpyxl import load_workbook
from PIL import Image

from app.services.quotes import today
from tests.conftest import FIXTURES

API = "/api/v1"
TODAY = f"{today():%Y%m%d}"


def new_quote(client, **body) -> dict:
    res = client.post(f"{API}/quotes", json=body)
    assert res.status_code == 201, res.json()
    return res.json()


def add_product(client, quote: dict, product: dict, qty: int = 1) -> dict:
    res = client.post(
        f"{API}/quotes/{quote['id']}/lines",
        json={"section_id": quote["sections"][0]["id"], "product_id": product["id"], "qty": qty},
    )
    assert res.status_code == 201, res.json()
    return res.json()


def first_line(quote: dict) -> dict:
    return quote["sections"][0]["lines"][0]


def patch_line(client, quote: dict, line: dict, **body) -> dict:
    res = client.patch(f"{API}/quotes/{quote['id']}/lines/{line['id']}", json=body)
    assert res.status_code == 200, res.json()
    return res.json()


# --------------------------------------------------------------- customers


def test_customers_crud_and_unique_code(client, customer):
    assert customer["code"] == "SP002" and customer["language"] == "en"
    clash = client.post(f"{API}/customers", json={"code": "SP002", "name": "Other"})
    assert clash.status_code == 409 and clash.json()["key"] == "customer.code_taken"
    res = client.patch(f"{API}/customers/{customer['id']}", json={"default_margin_pct": "12.5"})
    assert res.json()["default_margin_pct"] == "12.5000"
    assert [c["code"] for c in client.get(f"{API}/customers", params={"q": "linux"}).json()] == [
        "SP002"
    ]
    assert client.delete(f"{API}/customers/{customer['id']}").status_code == 204


# ------------------------------------------------------------------ quotes


def test_offer_numbers_follow_the_day_sequence(client, customer):
    first = new_quote(client, customer_id=customer["id"])
    second = new_quote(client)
    assert first["offer_no"] == f"WKZ{TODAY}-01"
    assert second["offer_no"] == f"WKZ{TODAY}-02"
    # the customer's defaults fill the header
    assert first["contact"] == "David" and first["trade_term"] == "FOB Shenzhen"
    assert first["contact_email"] == "david@example.com"
    assert first["customer_snapshot"]["code"] == "SP002"
    assert first["validity_days"] == 30
    assert first["valid_until"] == (today() + timedelta(days=30)).isoformat()
    assert len(first["sections"]) == 1 and first["sections"][0]["layout"] == "offer"


def test_product_line_is_a_snapshot(client, ups):
    quote = add_product(client, new_quote(client), ups, qty=20)
    line = first_line(quote)
    assert line["name"] == "SP10KS"  # English document: English name
    assert [d["text"] for d in line["description_lines"]] == [
        "High-frequency on-line UPS, power 10KVA/5400W", "weight:14KG",
    ]  # fmt: skip
    assert line["model_no"] == "SP10KS"
    assert line["cost_usd"] == "400.0000" and line["unit_price"] == "400.0000"
    assert line["total"] == "8000.0000" and quote["grand_total"] == "8000.0000"
    assert line["printed_no"] == "1"

    # a later catalog price change does not alter the quote, but is flagged
    client.post(f"{API}/products/{ups['id']}/prices", json={"price_usd": "420"})
    line = first_line(client.get(f"{API}/quotes/{quote['id']}").json())
    assert line["unit_price"] == "400.0000"
    assert {"code": "price_changed", "now": "420.0000", "was": "400.0000"} in line["warnings"]
    refreshed = client.post(f"{API}/quotes/{quote['id']}/lines/{line['id']}/refresh-cost").json()
    assert first_line(refreshed)["cost_usd"] == "420.0000"
    assert not [w for w in first_line(refreshed)["warnings"] if w["code"] == "price_changed"]


def test_margin_resolution_line_customer_category_settings(client, ups, customer, categories):
    settings = client.get(f"{API}/settings").json()
    settings["default_margin_pct"] = "5"
    client.put(f"{API}/settings", json=settings)
    quote = add_product(client, new_quote(client), ups)
    assert first_line(quote)["unit_price"] == "420.0000"  # settings 5%

    client.patch(f"{API}/categories/{categories['ups']['id']}", json={"default_margin_pct": "10"})
    quote = patch_line(client, quote, first_line(quote), qty=1)
    assert first_line(quote)["unit_price"] == "440.0000"  # category 10%

    client.patch(f"{API}/customers/{customer['id']}", json={"default_margin_pct": "12.5"})
    quote = client.patch(f"{API}/quotes/{quote['id']}", json={"customer_id": customer["id"]}).json()
    assert first_line(quote)["unit_price"] == "450.0000"  # customer 12.5%

    quote = patch_line(client, quote, first_line(quote), margin_pct="0.333")
    line = first_line(quote)
    assert line["unit_price"] == "401.3300"  # 400 × 1.00333 = 401.332 -> 401.33
    assert line["effective_margin_pct"] == "0.3330"

    # typing the unit price wins and shows the margin it carries
    quote = patch_line(client, quote, line, unit_price="500")
    line = first_line(quote)
    assert line["unit_price_manual"] is True and line["unit_price"] == "500.0000"
    assert Decimal(line["effective_margin_pct"]) == Decimal("25")
    # a margin decides the price again
    line = first_line(patch_line(client, quote, line, margin_pct="0"))
    assert line["unit_price_manual"] is False and line["unit_price"] == "400.0000"


def test_rounding_is_half_up_to_cents(client, ups):
    quote = add_product(client, new_quote(client), ups, qty=3)
    line = first_line(
        patch_line(client, quote, first_line(quote), cost_usd="0.125", margin_pct="0")
    )
    assert line["unit_price"] == "0.1300"  # 0.125 -> 0.13, not banker's 0.12
    assert line["total"] == "0.3900"


def test_sections_discounts_and_totals(client, ups):
    quote = add_product(client, new_quote(client), ups, qty=2)
    quote = client.post(f"{API}/quotes/{quote['id']}/sections", json={"title": "Option B"}).json()
    second = quote["sections"][1]
    quote = client.post(
        f"{API}/quotes/{quote['id']}/lines",
        json={"section_id": second["id"], "name": "Installation", "unit_price": "150", "qty": 1},
    ).json()
    assert [s["subtotal"] for s in quote["sections"]] == ["800.0000", "150.0000"]
    assert quote["subtotal"] == "950.0000"
    quote = client.patch(f"{API}/quotes/{quote['id']}", json={"discount_pct": "10"}).json()
    assert quote["grand_total"] == "855.0000"
    quote = client.patch(
        f"{API}/quotes/{quote['id']}", json={"discount_pct": None, "discount_amount": "50"}
    ).json()
    assert quote["grand_total"] == "900.0000"
    res = client.delete(f"{API}/quotes/{quote['id']}/sections/{second['id']}")
    assert res.json()["subtotal"] == "800.0000"
    only = res.json()["sections"][0]["id"]
    res = client.delete(f"{API}/quotes/{quote['id']}/sections/{only}")
    assert res.status_code == 422 and res.json()["key"] == "quote.last_section"


def test_manual_item_saved_to_catalog(client, categories):
    quote = new_quote(client)
    quote = client.post(
        f"{API}/quotes/{quote['id']}/lines",
        json={"section_id": quote["sections"][0]["id"], "name": "Computer bag", "cost_usd": "3.5",
              "qty": 10, "category_id": categories["other"]["id"], "save_to_catalog": True,
              "description_lines": [{"text": "Black, 11.6 inch", "emphasis": False}]},
    ).json()  # fmt: skip
    line = first_line(quote)
    assert line["kind"] == "manual" and line["product_id"] is not None
    product = client.get(f"{API}/products/{line['product_id']}").json()
    assert product["is_manual"] is True and product["current_price_usd"] == "3.5000"
    assert product["description_en"] == "Black, 11.6 inch"
    res = client.post(
        f"{API}/quotes/{quote['id']}/lines",
        json={"section_id": quote["sections"][0]["id"], "name": "X", "save_to_catalog": True},
    )
    assert res.status_code == 422 and res.json()["key"] == "quote.category_required"


def test_warnings_from_the_product(client, ups):
    client.patch(f"{API}/products/{ups['id']}", json={"status": "discontinued",
                                                       "confirm_before_order": True})  # fmt: skip
    quote = add_product(client, new_quote(client), ups, qty=60)
    codes = {w["code"] for w in first_line(quote)["warnings"]}
    assert {"status", "confirm_before_order", "over_max_order"} <= codes
    listing = client.get(f"{API}/quotes").json()
    assert listing["items"][0]["warnings"] == 1


def test_line_numbers_order_and_layout(client, ups):
    quote = new_quote(client)
    for _ in range(3):
        quote = add_product(client, quote, ups)
    lines = quote["sections"][0]["lines"]
    quote = patch_line(client, quote, lines[1], line_no="3")  # the sample numbers 1, 3, 4
    assert [line["printed_no"] for line in quote["sections"][0]["lines"]] == ["1", "3", "3"]
    ids = [line["id"] for line in lines]
    quote = client.post(
        f"{API}/quotes/{quote['id']}/lines/reorder",
        json={"section_id": quote["sections"][0]["id"], "line_ids": ids[::-1]},
    ).json()
    assert [line["id"] for line in quote["sections"][0]["lines"]] == ids[::-1]
    section = quote["sections"][0]
    quote = client.patch(
        f"{API}/quotes/{quote['id']}/sections/{section['id']}", json={"layout": "list"}
    ).json()
    assert quote["sections"][0]["layout"] == "list"


def test_only_drafts_change_and_revisions(client, ups):
    quote = add_product(client, new_quote(client), ups)
    sent = client.patch(f"{API}/quotes/{quote['id']}", json={"status": "sent"}).json()
    res = client.patch(
        f"{API}/quotes/{quote['id']}/lines/{first_line(sent)['id']}", json={"qty": 2}
    )
    assert res.status_code == 409 and res.json()["key"] == "quote.locked"

    revision = client.post(f"{API}/quotes/{quote['id']}/revision").json()
    assert revision["offer_no"] == quote["offer_no"] and revision["revision"] == 2
    assert revision["display_no"] == f"{quote['offer_no']} R2"
    assert revision["status"] == "draft" and revision["parent_quote_id"] == quote["id"]
    assert first_line(revision)["unit_price"] == first_line(sent)["unit_price"]
    assert [r["revision"] for r in revision["revisions"]] == [1, 2]

    duplicate = client.post(f"{API}/quotes/{quote['id']}/duplicate").json()
    assert duplicate["offer_no"] == f"WKZ{TODAY}-02" and duplicate["revision"] == 1


def test_list_and_search(client, customer, ups):
    new_quote(client, customer_id=customer["id"])
    new_quote(client)
    listing = client.get(f"{API}/quotes", params={"q": "linux"}).json()
    assert listing["total"] == 1 and listing["items"][0]["customer_code"] == "SP002"
    assert client.get(f"{API}/quotes", params={"status": "sent"}).json()["total"] == 0


# ------------------------------------------------------------------ images


def png_bytes(color: str = "red", size: tuple[int, int] = (300, 200)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


def test_product_photos_reach_quote_lines(client, ups):
    files = [("files", ("a.png", png_bytes("red"))), ("files", ("b.png", png_bytes("blue")))]
    ids = client.post(f"{API}/products/{ups['id']}/images", files=files).json()
    assert len(ids) == 2
    assert client.get(f"{API}/products/{ups['id']}").json()["image_ids"] == ids
    image = client.get(f"{API}/images/{ids[0]}")
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    quote = add_product(client, new_quote(client), ups)
    assert first_line(quote)["image_ids"] == ids
    # unlinking keeps the file for documents that print it
    assert client.delete(f"{API}/products/{ups['id']}/images/{ids[0]}").json() == ids[1:]
    assert client.get(f"{API}/images/{ids[0]}").status_code == 200
    bad = client.post(f"{API}/products/{ups['id']}/images", files={"files": ("x.png", b"nope")})
    assert bad.status_code == 422 and bad.json()["key"] == "image.unreadable"


def test_company_logo_and_signature(client):
    res = client.post(f"{API}/settings/images/logo", files={"file": ("logo.png", png_bytes())})
    assert res.status_code == 201
    assert client.get(f"{API}/settings").json()["company"]["logo_image_id"] == res.json()
    assert client.delete(f"{API}/settings/images/logo").status_code == 204
    assert client.get(f"{API}/settings").json()["company"]["logo_image_id"] is None


# ------------------------------------------------------- combined products


def add_manual(client, quote: dict, name: str, cost: str, qty: int) -> dict:
    res = client.post(
        f"{API}/quotes/{quote['id']}/lines",
        json={"section_id": quote["sections"][0]["id"], "name": name, "cost_usd": cost,
              "qty": qty},
    )  # fmt: skip
    assert res.status_code == 201, res.json()
    return res.json()


def texts(line: dict) -> list[str]:
    return [d["text"] for d in line["description_lines"]]


def test_combine_lines_into_one_product_and_split_back(client, customer, ups):
    quote = add_product(client, new_quote(client, customer_id=customer["id"]), ups, qty=20)
    quote = add_manual(client, quote, "Battery 12V24AH", "21.5", 40)
    ids = [line["id"] for line in quote["sections"][0]["lines"]]

    res = client.post(f"{API}/quotes/{quote['id']}/lines/combine", json={"line_ids": ids[:1],
                      "name": "x"})  # fmt: skip
    assert res.status_code == 422 and res.json()["key"] == "quote.combine_two"

    quote = client.post(
        f"{API}/quotes/{quote['id']}/lines/combine",
        json={"line_ids": ids, "name": "UPS kit"},
    ).json()
    [line] = quote["sections"][0]["lines"]
    assert line["kind"] == "config" and line["name"] == "UPS kit" and line["qty"] == 20
    assert [(c["name"], c["qty"], c["cost_usd"]) for c in line["components"]] == [
        ("SP10KS", 1, "400.0000"), ("Battery 12V24AH", 2, "21.5000"),
    ]  # fmt: skip
    assert texts(line) == ["SP10KS", "2*Battery 12V24AH"]
    assert line["cost_usd"] == "443.0000" and line["total"] == "8860.0000"

    # the customer sees one row; the internal copy lists the parts and their cost
    customer_pdf = pdf_text(client.get(f"{API}/quotes/{quote['id']}/export.pdf").content)
    assert "UPS kit" in customer_pdf and "2*Battery 12V24AH" in customer_pdf
    assert "21.5" not in customer_pdf and "443" in customer_pdf
    internal = pdf_text(client.get(f"{API}/quotes/{quote['id']}/export.pdf?internal=true").content)
    assert "· Battery 12V24AH ×2" in internal and "860.00" in internal and "8,000.00" in internal

    # editing a part: price and description follow, until the description is typed by hand
    parts = line["components"]
    parts[1] = {**parts[1], "condition": "used", "qty": 1}
    line = first_line(patch_line(client, quote, line, components=parts))
    assert texts(line) == ["SP10KS", "Battery 12V24AH (Used)"]
    assert line["cost_usd"] == "421.5000"
    line = first_line(patch_line(client, quote, line, description_lines=[{"text": "Kit"}]))
    line = first_line(patch_line(client, quote, line, components=parts[:1]))
    assert texts(line) == ["Kit"] and line["cost_usd"] == "400.0000"
    line = first_line(patch_line(client, quote, line, describe=True))
    assert texts(line) == ["SP10KS"]

    quote = client.post(f"{API}/quotes/{quote['id']}/lines/{line['id']}/split").json()
    lines = quote["sections"][0]["lines"]
    assert [(x["kind"], x["name"], x["qty"], x["cost_usd"]) for x in lines] == [
        ("product", "SP10KS", 20, "400.0000"),
    ]
    assert texts(lines[0])[0].startswith("High-frequency")


def test_combined_product_from_catalog_parts(client, ups):
    quote = new_quote(client, language="zh")
    res = client.post(
        f"{API}/quotes/{quote['id']}/lines",
        json={"section_id": quote["sections"][0]["id"], "kind": "config", "name": "整机",
              "qty": 5, "model_no": "DN11", "components": [
                  {"product_id": ups["id"], "condition": "new"},
                  {"name": "Bag", "qty": 1},
              ]},
    )  # fmt: skip
    assert res.status_code == 201, res.json()
    line = first_line(res.json())
    assert texts(line) == ["SP10KS 在线式UPS (全新)", "Bag"]
    assert line["cost_usd"] == "400.0000" and line["model_no"] == "DN11"
    assert {"code": "no_price", "part": "Bag"} in line["warnings"]

    client.post(f"{API}/products/{ups['id']}/prices", json={"price_usd": "420"})
    line = first_line(client.get(f"{API}/quotes/{quote['id']}").json())
    assert line["cost_usd"] == "400.0000"
    assert {"code": "price_changed", "now": "420.0000", "was": "400.0000",
            "part": "SP10KS 在线式UPS"} in line["warnings"]  # fmt: skip
    quote = client.post(f"{API}/quotes/{quote['id']}/lines/{line['id']}/refresh-cost").json()
    assert first_line(quote)["cost_usd"] == "420.0000"

    copy = client.post(f"{API}/quotes/{quote['id']}/duplicate").json()
    assert len(first_line(copy)["components"]) == 2


# --------------------------------------------------------------- documents


def pdf_text(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_quote_pdf_and_excel(client, customer, ups):
    client.post(f"{API}/settings/images/logo", files={"file": ("logo.png", png_bytes())})
    client.post(f"{API}/products/{ups['id']}/images", files={"files": ("a.png", png_bytes())})
    quote = add_product(client, new_quote(client, customer_id=customer["id"]), ups, qty=20)
    pdf = client.get(f"{API}/quotes/{quote['id']}/export.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert pdf.headers["content-disposition"].startswith("inline")
    text = pdf_text(pdf.content)
    assert f"WKZ{TODAY}-01" in text and "Linux Technology SL" in text
    assert "SP10KS" in text and "8,000" in text and "Total price" in text
    assert date.today().strftime("%d/%m/%Y") in text

    section = quote["sections"][0]
    client.patch(f"{API}/quotes/{quote['id']}/sections/{section['id']}", json={"layout": "list"})
    text = pdf_text(client.get(f"{API}/quotes/{quote['id']}/export.pdf").content)
    assert "Quotation List" in text and "$8,000.00" in text and "Email:" in text

    xlsx = client.get(f"{API}/quotes/{quote['id']}/export.xlsx")
    assert xlsx.headers["content-disposition"].startswith("attachment")
    ws = load_workbook(io.BytesIO(xlsx.content)).active
    formulas = [c.value for row in ws.iter_rows() for c in row if str(c.value).startswith("=")]
    assert "=F8*G8" in formulas and "=SUM(H8:H8)" in formulas
    assert len(ws._images) == 2  # logo + photo


def test_internal_version_shows_cost_margin_and_profit(client, customer, ups):
    quote = add_product(client, new_quote(client, customer_id=customer["id"]), ups, qty=20)
    quote = patch_line(client, quote, first_line(quote), margin_pct="25")  # 400 -> 500
    quote = client.post(
        f"{API}/quotes/{quote['id']}/lines",
        json={"section_id": quote["sections"][0]["id"], "name": "Cable", "unit_price": "3"},
    ).json()
    client.patch(f"{API}/quotes/{quote['id']}", json={"discount_amount": "100"})

    customer_pdf = pdf_text(client.get(f"{API}/quotes/{quote['id']}/export.pdf").content)
    assert "8,000" not in customer_pdf and "INTERNAL" not in customer_pdf

    res = client.get(f"{API}/quotes/{quote['id']}/export.pdf?internal=true&download=true")
    assert res.status_code == 200
    assert res.headers["content-disposition"].endswith(f'WKZ{TODAY}-01_INTERNAL.pdf"')
    text = pdf_text(res.content)
    assert "INTERNAL" in text and "Linux Technology SL" in text
    assert "25.00%" in text and "8,000.00" in text and "10,000.00" in text
    # profit 2,000 on the UPS, minus the 100 discount; the cable has no cost
    assert "$1,900.00" in text and "23.75%" in text and "1 item(s) without a cost" in text

    xlsx = client.get(f"{API}/quotes/{quote['id']}/export.xlsx?internal=true")
    assert "_INTERNAL.xlsx" in xlsx.headers["content-disposition"]
    ws = load_workbook(io.BytesIO(xlsx.content)).active
    values = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
    assert "=C9*D9" in values and "=H9-G9" in values and "=I11+H14" in values


def test_list_layout_prints_the_name_of_a_line_without_specs(client):
    quote = new_quote(client, layout="list")
    quote = client.post(
        f"{API}/quotes/{quote['id']}/lines",
        json={"section_id": quote["sections"][0]["id"], "name": "Computer bag", "unit_price": "3"},
    ).json()
    assert "Computer bag" in pdf_text(client.get(f"{API}/quotes/{quote['id']}/export.pdf").content)
    ws = load_workbook(
        io.BytesIO(client.get(f"{API}/quotes/{quote['id']}/export.xlsx").content)
    ).active
    assert ws["B8"].value == "Computer bag"


def test_chinese_document(client, ups):
    quote = add_product(client, new_quote(client, language="zh"), ups)
    assert first_line(quote)["name"] == "SP10KS 在线式UPS"
    text = pdf_text(client.get(f"{API}/quotes/{quote['id']}/export.pdf").content)
    assert "报价单号" in text and "合计" in text and "在线式" in text


# --------------------------------------------------------------- proformas


def accepted_quote(client, customer, ups) -> dict:
    quote = add_product(client, new_quote(client, customer_id=customer["id"]), ups, qty=8000)
    quote = add_product(client, quote, ups, qty=10)
    return client.patch(f"{API}/quotes/{quote['id']}", json={"status": "accepted"}).json()


def test_proforma_from_accepted_quote(client, customer, ups):
    quote = add_product(client, new_quote(client, customer_id=customer["id"]), ups)
    line_id = first_line(quote)["id"]
    res = client.post(f"{API}/quotes/{quote['id']}/proforma", json={"line_ids": [line_id]})
    assert res.status_code == 409 and res.json()["key"] == "proforma.quote_not_accepted"

    quote = accepted_quote(client, customer, ups)
    first = first_line(quote)
    res = client.post(
        f"{API}/quotes/{quote['id']}/proforma", json={"line_ids": [first["id"]], "po_no": "PO-1"}
    )
    assert res.status_code == 201, res.json()
    pi = res.json()
    assert pi["pi_no"] == f"PI{TODAY}" and pi["status"] == "draft" and pi["po_no"] == "PO-1"
    assert pi["attention"] == "David" and pi["customer_snapshot"]["code"] == "SP002"
    assert [t["title"] for t in pi["terms"]] == [
        "Payment Term", "Lead time", "Delivery Place", "Warranty time",
    ]  # fmt: skip
    assert "Price based on FOB Shenzhen" in pi["terms"][0]["text"]
    assert len(pi["lines"]) == 1 and pi["total"] == "3200000.0000"

    pi = client.patch(
        f"{API}/proformas/{pi['id']}", json={"foc_pct": "1.5", "freight": "1200"}
    ).json()
    assert pi["total"] == "3201200.0000"
    pi = client.patch(f"{API}/proformas/{pi['id']}/lines/{pi['lines'][0]['id']}",
                      json={"qty": 7000}).json()  # fmt: skip
    assert pi["subtotal"] == "2800000.0000"

    second = client.post(f"{API}/quotes/{quote['id']}/proforma", json={"line_ids": [first["id"]]})
    assert second.json()["pi_no"] == f"PI{TODAY}-02"
    assert len(client.get(f"{API}/quotes/{quote['id']}").json()["proformas"]) == 2


def test_issued_proforma_is_immutable_and_revised(client, customer, ups):
    quote = accepted_quote(client, customer, ups)
    pi = client.post(
        f"{API}/quotes/{quote['id']}/proforma", json={"line_ids": [first_line(quote)["id"]]}
    ).json()
    issued = client.post(f"{API}/proformas/{pi['id']}/issue").json()
    assert issued["status"] == "issued" and issued["issued_at"] == today().isoformat()
    res = client.patch(f"{API}/proformas/{pi['id']}", json={"po_no": "X"})
    assert res.status_code == 409 and res.json()["key"] == "proforma.issued"
    assert client.delete(f"{API}/proformas/{pi['id']}").status_code == 409

    revised = client.post(f"{API}/proformas/{pi['id']}/revise").json()
    assert revised["pi_no"] == f"PI{TODAY}-R2" and revised["status"] == "draft"
    assert revised["revised_from_id"] == pi["id"]
    again = client.post(f"{API}/proformas/{pi['id']}/revise").json()
    assert again["pi_no"] == f"PI{TODAY}-R3"
    assert client.delete(f"{API}/quotes/{quote['id']}").json()["key"] == "quote.has_proformas"


def test_proforma_documents(client, customer, ups):
    settings = client.get(f"{API}/settings").json()
    settings["company"].update(seller_name="Laura Liang", seller_phone="008613723436409",
                               bank_account_no="1234 5678")  # fmt: skip
    client.put(f"{API}/settings", json=settings)
    client.post(f"{API}/settings/images/signature", files={"file": ("s.png", png_bytes())})
    quote = accepted_quote(client, customer, ups)
    pi = client.post(
        f"{API}/quotes/{quote['id']}/proforma",
        json={"line_ids": [first_line(quote)["id"]], "po_no": "PANZ20260914"},
    ).json()
    client.patch(f"{API}/proformas/{pi['id']}", json={"foc_pct": "1.5"})
    text = pdf_text(client.get(f"{API}/proformas/{pi['id']}/export.pdf").content)
    for needle in ("Proforma", "Invoice", pi["pi_no"], "PANZ20260914", "Laura Liang",
                   "1.5% FOC", "$3,200,000.00", "TERMS & CONDITION", "1234 5678",
                   "Seller:Shenzhen Sixunited"):  # fmt: skip
        assert needle in text, needle
    ws = load_workbook(
        io.BytesIO(client.get(f"{API}/proformas/{pi['id']}/export.xlsx").content)
    ).active
    assert ws["A4"].value.startswith("Proforma")
    assert any(str(c.value).startswith("=SUM(G") for row in ws.iter_rows() for c in row)


def test_sample_fixture_image_as_product_photo(client, ups):
    """A real JPEG screenshot as a product photo goes through the document copy."""
    data = (FIXTURES / "img_ssd.jpg").read_bytes()
    ids = client.post(f"{API}/products/{ups['id']}/images", files={"files": ("s.jpg", data)}).json()
    quote = add_product(client, new_quote(client), ups)
    client.patch(
        f"{API}/quotes/{quote['id']}/sections/{quote['sections'][0]['id']}", json={"layout": "list"}
    )
    assert client.get(f"{API}/quotes/{quote['id']}/export.pdf").status_code == 200
    assert ids
