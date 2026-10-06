from decimal import Decimal

API = "/api/v1"


def make_ram(client, categories, **overrides):
    body = {
        "category_id": categories["ram_module"]["id"],
        "name_zh": "DDR4 8GB 2666MHZ 沃存 海力士颗粒",
        "attributes": {
            "type": "DDR4",
            "capacity_gb": "8GB",
            "speed_mhz": "2666MHZ",
            "form_factor": "SO DIMM",
            "chip_vendor": "海力士",
        },
        "price_usd": "14.50",
    }
    body.update(overrides)
    return client.post(f"{API}/products", json=body)


def brand_id(client, canonical):
    return next(b["id"] for b in client.get(f"{API}/brands").json() if b["canonical"] == canonical)


def test_seeded_reference_data(client, categories):
    assert len(categories) == 31
    assert categories["cpu"]["is_main"] is True
    assert categories["camera"]["is_main"] is False
    ram_keys = [f["key"] for f in categories["ram_module"]["attribute_schema"]]
    assert ram_keys[:5] == ["type", "capacity_gb", "speed_mhz", "form_factor", "chip_vendor"]
    brands = {b["canonical"]: b for b in client.get(f"{API}/brands").json()}
    assert {a["alias"] for a in brands["SK hynix"]["aliases"]} >= {"SK hynix", "海力士"}
    assert len(client.get(f"{API}/note-rules").json()) == 13


def test_seed_is_idempotent(client, session):
    from app.seed import seed

    seed(session)
    assert len(client.get(f"{API}/categories").json()) == 31


def test_create_and_get_product(client, categories):
    res = make_ram(client, categories)
    assert res.status_code == 201, res.json()
    product = res.json()
    assert Decimal(product["current_price_usd"]) == Decimal("14.5")
    assert product["price_date"] is not None
    fetched = client.get(f"{API}/products/{product['id']}").json()
    assert fetched["name_zh"] == "DDR4 8GB 2666MHZ 沃存 海力士颗粒"
    assert isinstance(fetched["current_price_usd"], str)  # money is never a JSON float


def test_duplicate_fingerprint_rejected(client, categories):
    first = make_ram(client, categories).json()
    res = make_ram(
        client,
        categories,
        name_zh="other spelling",
        attributes={
            "type": "ddr4",
            "capacity_gb": 8,
            "speed_mhz": "2666 MHz",
            "form_factor": "SODIMM",
            "chip_vendor": "SK hynix",
        },
    )
    assert res.status_code == 409
    assert res.json()["key"] == "product.duplicate"
    assert res.json()["params"]["existing_id"] == first["id"]


def test_different_brand_is_a_different_product(client, categories):
    assert make_ram(client, categories, brand_id=brand_id(client, "Wodposit")).status_code == 201
    assert make_ram(client, categories, brand_id=brand_id(client, "ADATA")).status_code == 201


def test_same_specs_with_different_erp_codes_are_two_products(client, categories):
    first = make_ram(client, categories, erp_code="E.M.R.0000036")
    assert first.status_code == 201
    second = make_ram(client, categories, erp_code="E.M.R.0000099")
    assert second.status_code == 201, second.json()
    assert second.json()["fingerprint"] != first.json()["fingerprint"]
    # without a code to tell them apart, it is still the same product
    assert make_ram(client, categories).json()["key"] == "product.duplicate"
    # editing the second keeps its own identity
    res = client.patch(f"{API}/products/{second.json()['id']}", json={"notes_raw": "checked"})
    assert res.status_code == 200, res.json()


def test_duplicate_erp_code_rejected(client, categories):
    make_ram(client, categories, erp_code="E.M.R.0000036")
    res = make_ram(
        client,
        categories,
        erp_code=" e.m.r.0000036 ",
        attributes={"type": "DDR5", "capacity_gb": 16},
    )
    assert res.status_code == 409
    assert res.json()["key"] == "product.duplicate_erp"


def test_invalid_number_attribute(client, categories):
    res = client.post(
        f"{API}/products",
        json={
            "category_id": categories["cpu"]["id"],
            "name_zh": "i5-1340P",
            "attributes": {"model": "i5-1340P", "tdp_w": "lots"},
        },
    )
    assert res.status_code == 422
    assert res.json()["key"] == "product.invalid_attribute"


def test_update_recomputes_fingerprint(client, categories):
    product = make_ram(client, categories).json()
    res = client.patch(
        f"{API}/products/{product['id']}",
        json={"attributes": {**product["attributes"], "capacity_gb": "16GB"}},
    )
    assert res.status_code == 200
    assert res.json()["fingerprint"] != product["fingerprint"]
    # the old identity is free again
    assert make_ram(client, categories).status_code == 201


def test_update_into_existing_identity_conflicts(client, categories):
    make_ram(client, categories)
    other = make_ram(client, categories, attributes={"type": "DDR5", "capacity_gb": 16}).json()
    res = client.patch(
        f"{API}/products/{other['id']}",
        json={
            "attributes": {
                "type": "DDR4",
                "capacity_gb": "8GB",
                "speed_mhz": "2666",
                "form_factor": "SODIMM",
                "chip_vendor": "海力士",
            }
        },
    )
    assert res.status_code == 409


def test_search_chinese_english_erp_and_short_terms(client, categories):
    make_ram(client, categories, erp_code="E.M.R.0000036", brand_id=brand_id(client, "Wodposit"))
    client.post(
        f"{API}/products",
        json={
            "category_id": categories["cpu"]["id"],
            "name_zh": "i5-1340P SRMJ7",
            "name_en": "Intel Core i5-1340P",
            "erp_code": "E.I.P.0000455",
            "attributes": {"model": "i5-1340P", "platform_family": "Raptor Lake-P"},
        },
    )

    def hits(q):
        return [
            p["name_zh"] for p in client.get(f"{API}/products", params={"q": q}).json()["items"]
        ]

    assert hits("海力士") == ["DDR4 8GB 2666MHZ 沃存 海力士颗粒"]
    assert hits("沃存") == ["DDR4 8GB 2666MHZ 沃存 海力士颗粒"]  # 2-char term: LIKE fallback
    assert hits("Wodposit") == ["DDR4 8GB 2666MHZ 沃存 海力士颗粒"]  # via brand
    assert hits("E.I.P.0000455") == ["i5-1340P SRMJ7"]
    assert hits("raptor lake") == ["i5-1340P SRMJ7"]  # via attributes, case-insensitive
    assert hits("core i5") == ["i5-1340P SRMJ7"]
    assert hits("ddr4 2666") == ["DDR4 8GB 2666MHZ 沃存 海力士颗粒"]
    assert hits("100%") == []
    assert len(hits("")) == 2


def test_list_filters_sort_and_paging(client, categories):
    make_ram(client, categories, price_usd="9.5")
    make_ram(client, categories, attributes={"type": "DDR5", "capacity_gb": 16}, price_usd="10")
    client.post(
        f"{API}/products",
        json={
            "category_id": categories["cpu"]["id"],
            "name_zh": "cpu",
            "attributes": {"model": "x"},
        },
    )
    res = client.get(f"{API}/products", params={"category": categories["ram_module"]["id"]}).json()
    assert res["total"] == 2
    prices = [
        p["current_price_usd"]
        for p in client.get(f"{API}/products", params={"sort": "price"}).json()["items"]
    ]
    assert [Decimal(p) for p in prices[:2]] == [Decimal("9.5"), Decimal("10")]  # numeric order
    assert prices[2] is None  # no price sorts last
    page = client.get(f"{API}/products", params={"page": 2, "page_size": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1


def test_manual_price_edit_keeps_history(client, categories):
    product = make_ram(client, categories).json()
    res = client.post(
        f"{API}/products/{product['id']}/prices", json={"price_usd": "15.25", "note": "deal"}
    )
    assert res.status_code == 201
    assert Decimal(res.json()["current_price_usd"]) == Decimal("15.25")
    history = client.get(f"{API}/products/{product['id']}/prices").json()
    assert [Decimal(h["price_usd"]) for h in history] == [Decimal("15.25"), Decimal("14.5")]
    assert [h["is_current"] for h in history] == [True, False]
    assert history[0]["import_id"] is None and history[0]["source_ref"] == "manual"


def test_forecast_tier_is_independent(client, categories):
    product = make_ram(client, categories).json()
    client.post(
        f"{API}/products/{product['id']}/prices", json={"price_usd": "13", "tier": "forecast"}
    )
    fetched = client.get(f"{API}/products/{product['id']}").json()
    assert Decimal(fetched["current_price_usd"]) == Decimal("14.5")
    assert Decimal(fetched["current_price_tier_forecast_usd"]) == Decimal("13")
    bad = client.post(
        f"{API}/products/{product['id']}/prices", json={"price_usd": "1", "tier": "x"}
    )
    assert bad.status_code == 422


def test_negative_price_rejected(client, categories):
    product = make_ram(client, categories).json()
    res = client.post(f"{API}/products/{product['id']}/prices", json={"price_usd": "-1"})
    assert res.status_code == 422


def test_merge_moves_history_codes_and_records_alias(client, categories):
    keep = make_ram(client, categories, erp_code="E.M.R.0000001").json()
    drop = make_ram(
        client,
        categories,
        name_zh="duplicate typed differently",
        erp_code="E.M.R.0000002",
        attributes={"type": "DDR4", "capacity_gb": 8, "speed_mhz": 2666, "form_factor": "UDIMM"},
        price_usd="20",
    ).json()
    res = client.post(f"{API}/products/{drop['id']}/merge", json={"into_id": keep["id"]})
    assert res.status_code == 200
    merged = res.json()
    assert merged["erp_code"] == "E.M.R.0000001"
    assert merged["erp_code_alt"] == ["E.M.R.0000002"]
    assert Decimal(merged["current_price_usd"]) == Decimal("14.5")  # keep's price stays current
    assert client.get(f"{API}/products/{drop['id']}").status_code == 404
    history = client.get(f"{API}/products/{keep['id']}/prices").json()
    assert sorted(Decimal(h["price_usd"]) for h in history) == [Decimal("14.5"), Decimal("20")]
    assert sum(h["is_current"] for h in history) == 1
    aliases = client.get(f"{API}/products/{keep['id']}/aliases").json()
    assert [a["fingerprint"] for a in aliases] == [drop["fingerprint"]]
    # the dropped identity now resolves to the kept product
    again = make_ram(
        client,
        categories,
        name_zh="x",
        attributes={"type": "DDR4", "capacity_gb": 8, "speed_mhz": 2666, "form_factor": "UDIMM"},
    )
    assert again.status_code == 409 and again.json()["params"]["existing_id"] == keep["id"]
    # search finds the kept product by the dropped ERP code
    found = client.get(f"{API}/products", params={"q": "E.M.R.0000002"}).json()["items"]
    assert [p["id"] for p in found] == [keep["id"]]


def test_merge_into_self_rejected(client, categories):
    product = make_ram(client, categories).json()
    res = client.post(f"{API}/products/{product['id']}/merge", json={"into_id": product["id"]})
    assert res.status_code == 422


def test_delete_product_removes_from_search(client, categories):
    product = make_ram(client, categories).json()
    assert client.delete(f"{API}/products/{product['id']}").status_code == 204
    assert client.get(f"{API}/products", params={"q": "海力士"}).json()["total"] == 0


def test_deactivate_and_invalid_status(client, categories):
    product = make_ram(client, categories).json()
    res = client.patch(f"{API}/products/{product['id']}", json={"status": "inactive"})
    assert res.json()["status"] == "inactive"
    res = client.patch(f"{API}/products/{product['id']}", json={"status": "gone"})
    assert res.status_code == 422


def test_brand_aliases(client, categories):
    res = client.post(f"{API}/brands", json={"canonical": "Netac", "name_zh": "朗科"})
    assert res.status_code == 201
    netac = res.json()
    assert {a["alias"] for a in netac["aliases"]} == {"Netac", "朗科"}
    res = client.post(f"{API}/brands/{netac['id']}/aliases", json={"alias": "NETAC Tech"})
    assert {a["alias"] for a in res.json()["aliases"]} >= {"NETAC Tech"}
    # an alias can only point at one brand
    taken = client.post(f"{API}/brands/{netac['id']}/aliases", json={"alias": "海力士"})
    assert taken.status_code == 409 and taken.json()["params"]["brand"] == "SK hynix"
    assert client.post(f"{API}/brands", json={"canonical": "netac"}).status_code == 409
    alias_id = next(a["id"] for a in res.json()["aliases"] if a["alias"] == "NETAC Tech")
    res = client.delete(f"{API}/brands/{netac['id']}/aliases/{alias_id}")
    assert "NETAC Tech" not in {a["alias"] for a in res.json()["aliases"]}


def test_brand_alias_drives_chip_vendor_fingerprint(client, categories):
    hynix = brand_id(client, "SK hynix")
    client.post(f"{API}/brands/{hynix}/aliases", json={"alias": "Hynix-CN"})
    make_ram(client, categories)
    res = make_ram(client, categories, attributes={**make_attrs(), "chip_vendor": "Hynix-CN"})
    assert res.status_code == 409


def make_attrs():
    return {
        "type": "DDR4",
        "capacity_gb": "8GB",
        "speed_mhz": "2666MHZ",
        "form_factor": "SO DIMM",
        "chip_vendor": "海力士",
    }


def test_brand_in_use_cannot_be_deleted(client, categories):
    adata = brand_id(client, "ADATA")
    make_ram(client, categories, brand_id=adata)
    assert client.delete(f"{API}/brands/{adata}").status_code == 409


def test_category_schema_edit(client, categories):
    cat = categories["camera"]
    schema = [
        {"key": "model", "label_en": "Model", "label_zh": "型号", "in_fingerprint": True},
        {"key": "resolution", "label_en": "Resolution", "label_zh": "分辨率"},
    ]
    res = client.patch(
        f"{API}/categories/{cat['id']}",
        json={"attribute_schema": schema, "default_margin_pct": "12.5"},
    )
    assert res.status_code == 200
    assert [f["key"] for f in res.json()["attribute_schema"]] == ["model", "resolution"]
    assert Decimal(res.json()["default_margin_pct"]) == Decimal("12.5")
    dup = client.patch(
        f"{API}/categories/{cat['id']}", json={"attribute_schema": [schema[0], schema[0]]}
    )
    assert dup.status_code == 422
    bad_key = client.patch(
        f"{API}/categories/{cat['id']}",
        json={"attribute_schema": [{**schema[0], "key": "Bad Key"}]},
    )
    assert bad_key.status_code == 422


def test_create_category(client):
    body = {"code": "smartwatch", "name_en": "Smartwatch", "name_zh": "智能手表"}
    assert client.post(f"{API}/categories", json=body).status_code == 201
    assert client.post(f"{API}/categories", json=body).status_code == 409


def test_problem_json_shape(client):
    res = client.get(f"{API}/products/999")
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["key"] == "product.not_found"


def test_note_rules_can_be_edited_and_stay_deleted(client):
    from app.migrate import upgrade_and_seed

    rules = client.get(f"{API}/note-rules").json()
    first = rules[0]
    res = client.patch(f"{API}/note-rules/{first['id']}", json={"enabled": False})
    assert res.status_code == 200 and res.json()["enabled"] is False
    bad = client.patch(f"{API}/note-rules/{first['id']}", json={"pattern": "(unclosed"})
    assert bad.status_code == 422 and bad.json()["key"] == "note_rule.bad_pattern"
    no_group = client.post(
        f"{API}/note-rules", json={"pattern": "可接", "field": "max_order_qty", "kind": "qty"}
    )
    assert no_group.json()["key"] == "note_rule.qty_group"
    made = client.post(
        f"{API}/note-rules", json={"pattern": "样品", "field": "sample", "value": "true"}
    )
    assert made.status_code == 201 and made.json()["sort_order"] > rules[-1]["sort_order"]

    assert client.delete(f"{API}/note-rules/{rules[1]['id']}").status_code == 204
    upgrade_and_seed()  # the next start does not bring a deleted default rule back
    patterns = [r["pattern"] for r in client.get(f"{API}/note-rules").json()]
    assert rules[1]["pattern"] not in patterns and "样品" in patterns
