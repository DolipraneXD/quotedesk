"""Normalize an extracted row and match it against the catalog (plan §4.1 step 5, §3.4).

Pure with respect to the database once a ``MatchContext`` is built: the context
loads categories, brands, remark rules and a product index up front, so analyzing
hundreds of rows costs no further queries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ProblemError
from app.models import Category, NoteRule, Product, ProductAlias
from app.services.brands import BrandResolver
from app.services.catalog import clean_attributes, erp_codes_of
from app.services.importer.normalize import brand_key, compute_fingerprint, split_erp_codes
from app.services.notes import apply_note_rules

USD_QUANT = Decimal("0.0001")
FUZZY_THRESHOLD = 0.85
PRICE_SWING_PCT = Decimal("30")
FLAG_FIELDS = (
    "confirm_before_order", "lead_time_confirm", "needs_validation", "quote_on_request",
    "recommended",
)  # fmt: skip
COMPARED_FIELDS = (
    "status", *FLAG_FIELDS, "stock_qty", "demand_qty", "stock_after_qty", "max_order_qty",
    "from_stock_qty", "notes_raw", "platform",
)  # fmt: skip


def issue(code: str, /, **params: Any) -> dict[str, Any]:
    assert "code" not in params, "an issue parameter may not be called 'code'"
    return {"code": code, **{k: str(v) for k, v in params.items()}}


def trigrams(text: str) -> set[str]:
    key = brand_key(text)
    if len(key) < 3:
        return {key} if key else set()
    return {key[i : i + 3] for i in range(len(key) - 2)}


def similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def jsonable(value: Any) -> Any:
    """Decimals and dates as strings so analysis results fit in JSON columns."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    return value


@dataclass
class SheetInfo:
    currency: str | None = None
    fx_rate: Decimal | None = None
    price_date: date | None = None


@dataclass
class Analysis:
    status: str  # new | updated | unchanged | possible_match | problem
    decision: str | None
    match_type: str | None  # erp | mpn | fingerprint | fuzzy | new
    matched_product_id: int | None
    candidates: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    staged: dict[str, Any]
    target_key: str | None = None  # identity used to spot duplicates within one import


@dataclass
class MatchContext:
    session: Session
    default_fx: Decimal
    import_date: date
    categories: dict[str, Category] = field(default_factory=dict)
    resolver: BrandResolver | None = None
    rules: list[NoteRule] = field(default_factory=list)
    by_erp: dict[str, int] = field(default_factory=dict)
    by_mpn: dict[tuple[int, str], int] = field(default_factory=dict)
    by_fingerprint: dict[str, int] = field(default_factory=dict)
    names: dict[int, list[tuple[int, str, set[str]]]] = field(default_factory=dict)
    products: dict[int, Product] = field(default_factory=dict)

    @classmethod
    def build(cls, session: Session, default_fx: Decimal, import_date: date) -> MatchContext:
        ctx = cls(session=session, default_fx=default_fx, import_date=import_date)
        ctx.categories = {c.code: c for c in session.scalars(select(Category))}
        ctx.resolver = BrandResolver(session)
        ctx.rules = list(
            session.scalars(select(NoteRule).order_by(NoteRule.sort_order, NoteRule.id))
        )
        for p in session.scalars(select(Product)):
            ctx.add_product(p)
        for alias in session.scalars(select(ProductAlias)):
            ctx.by_fingerprint.setdefault(alias.fingerprint, alias.product_id)
        return ctx

    def add_product(self, p: Product) -> None:
        self.products[p.id] = p
        for code in [p.erp_code, *(p.erp_code_alt or [])]:
            if code:
                self.by_erp[code.upper()] = p.id
        if p.mpn:
            self.by_mpn[(p.category_id, p.mpn.strip().upper())] = p.id
        self.by_fingerprint[p.fingerprint] = p.id
        self.names.setdefault(p.category_id, []).append((p.id, p.name_zh, trigrams(p.name_zh)))


def effective_row(source: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
    """The extracted row with the user's review edits applied."""
    row = dict(source)
    for key, value in (edits or {}).items():
        if key == "attributes" and isinstance(value, dict):
            attrs = {a["key"]: a["value"] for a in row.get("attributes") or []}
            attrs.update(value)
            row["attributes"] = [
                {"key": k, "value": v} for k, v in attrs.items() if v not in (None, "")
            ]
        else:
            row[key] = value
    return row


def assembly_fields(row: dict[str, Any]) -> dict[str, Any]:
    """The complete unit a row belongs to (a BOM: the unit row and its part rows)."""
    key = (row.get("assembly") or "").strip()
    role = row.get("assembly_role")
    if not key or role not in ("unit", "part"):
        return {"assembly": None, "assembly_role": None}
    return {"assembly": key, "assembly_role": role}


def stage_prices(
    row: dict[str, Any], sheet: SheetInfo, ctx: MatchContext, source_ref: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    staged: dict[str, dict[str, Any]] = {}
    override = to_decimal(row.get("price_usd"))  # manual correction in review
    for item in row.get("prices") or []:
        amount = to_decimal(item.get("amount"))
        if amount is None or amount <= 0:
            continue
        tier = item.get("tier") if item.get("tier") in ("standard", "forecast") else "standard"
        currency = item.get("currency") or sheet.currency or "USD"
        fx = to_decimal(item.get("fx_rate")) or sheet.fx_rate
        if currency == "CNY":
            if fx is None:
                fx = ctx.default_fx
                issues.append(issue("default_fx", rate=fx))
            usd = (amount / fx).quantize(USD_QUANT, rounding=ROUND_HALF_UP)
            original, original_currency = amount, "CNY"
        else:
            usd = amount.quantize(USD_QUANT, rounding=ROUND_HALF_UP)
            original = to_decimal(item.get("original_amount")) or amount
            original_currency = item.get("original_currency") or "USD"
        price_date = _parse_date(item.get("date")) or sheet.price_date or ctx.import_date
        column = item.get("column") or ""
        staged[tier] = {
            "tier": tier,
            "price_usd": usd,
            "amount_original": original,
            "currency_original": original_currency,
            "fx_rate": fx if (currency == "CNY" or original_currency == "CNY") else None,
            "price_date": price_date,
            "source_ref": f"{source_ref}{column}" if column else source_ref,
        }
    if override is not None:
        base = staged.get("standard", {})
        staged["standard"] = {
            "tier": "standard",
            "price_usd": override,
            "amount_original": override,
            "currency_original": "USD",
            "fx_rate": None,
            "price_date": base.get("price_date") or sheet.price_date or ctx.import_date,
            "source_ref": base.get("source_ref") or source_ref,
        }
    return list(staged.values()), issues


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    number = to_decimal(value)
    return int(number) if number is not None else None


def analyze_row(
    ctx: MatchContext,
    source: dict[str, Any],
    edits: dict[str, Any],
    sheet: SheetInfo,
    source_ref: str,
) -> Analysis:
    row = effective_row(source, edits)
    issues = [issue("llm", text=t) for t in row.get("issues") or []]
    confidence = to_decimal(row.get("confidence"))
    if confidence is not None and confidence < Decimal("0.6"):
        issues.append(issue("low_confidence", value=confidence))

    def problem(problem_code: str, /, **params: Any) -> Analysis:
        found = [*issues, issue(problem_code, **params)]
        return Analysis("problem", "skip", None, None, [], found, jsonable(row))

    category = ctx.categories.get(row.get("category_code") or "")
    if category is None:
        return problem("unknown_category", category=row.get("category_code"))
    name_zh = (row.get("name_zh") or "").strip()
    if not name_zh:
        return problem("missing_name")

    raw_attrs = {a["key"]: a["value"] for a in row.get("attributes") or [] if a.get("key")}
    try:
        attributes = clean_attributes(category.attribute_schema, raw_attrs)
    except ProblemError as exc:
        return problem("invalid_attribute", key=exc.params.get("key"))

    assert ctx.resolver is not None
    brand_text = (row.get("brand") or "").strip()
    brand = ctx.resolver.find(brand_text) if brand_text else None
    if brand_text and brand is None:
        issues.append(issue("new_brand", brand=brand_text))
    brand_canonical = brand.canonical if brand else (brand_text or None)

    fingerprint = compute_fingerprint(
        category.code,
        brand_canonical,
        category.attribute_schema,
        attributes,
        ctx.resolver.canonical,
        name_zh,
    )
    erp_codes = []
    for code in row.get("erp_codes") or []:
        erp_codes.extend(split_erp_codes(code))
    erp_codes = list(dict.fromkeys(erp_codes))
    mpn = (row.get("mpn") or "").strip() or None

    prices, price_issues = stage_prices(row, sheet, ctx, source_ref)
    issues.extend(price_issues)
    unit = assembly_fields(row)
    if unit["assembly_role"] == "unit":
        issues.append(issue("assembly_unit", unit=unit["assembly"]))
        if row.get("parts_total"):
            issues.append(issue("parts_total", **row["parts_total"]))
    elif unit["assembly_role"] == "part":
        issues.append(issue("assembly_part", unit=unit["assembly"]))
        if row.get("unit_fx_rate"):
            issues.append(issue("unit_fx", unit=unit["assembly"], rate=row["unit_fx_rate"]))

    notes = " ".join(t for t in (row.get("notes_raw"), row.get("no_price_reason")) if t)
    flags = apply_note_rules(notes, ctx.rules)  # type: ignore[arg-type]
    fields: dict[str, Any] = {
        "status": flags.get("status", "active"),
        **{f: bool(flags.get(f, False)) for f in FLAG_FIELDS},
        "stock_qty": _int_or_none(row.get("stock_qty")),
        "demand_qty": _int_or_none(row.get("demand_qty")),
        "stock_after_qty": _int_or_none(row.get("stock_after_qty")),
        "max_order_qty": flags.get("max_order_qty"),
        "from_stock_qty": flags.get("from_stock_qty"),
        "payment_terms": flags.get("payment_terms"),
        "supply_note": flags.get("supply_note"),
        "market": flags.get("market"),
        "notes_raw": row.get("notes_raw") or None,
        "platform": row.get("platform") or None,
    }
    if row.get("status") in ("active", "discontinued", "stock_only", "no_supply", "inactive"):
        fields["status"] = row["status"]  # explicit review edit wins over remark rules

    staged = {
        "category_id": category.id,
        "category_code": category.code,
        "name_zh": name_zh,
        "name_en": (row.get("name_en") or "").strip() or None,
        "brand_id": brand.id if brand else None,
        "brand_name": brand_canonical,
        "brand_new": bool(brand_text and brand is None),
        "attributes": attributes,
        "fingerprint": fingerprint,
        "erp_code": erp_codes[0] if erp_codes else None,
        "erp_code_alt": erp_codes[1:],
        "mpn": mpn,
        "fields": fields,
        "prices": prices,
        "no_price_reason": row.get("no_price_reason"),
        **unit,
    }

    # Matching precedence: ERP code, MPN within category, fingerprint, fuzzy name.
    match_type: str | None = None
    product_id: int | None = None
    for code in erp_codes:
        if code in ctx.by_erp:
            match_type, product_id = "erp", ctx.by_erp[code]
            break
    if product_id is None and mpn and (category.id, mpn.upper()) in ctx.by_mpn:
        match_type, product_id = "mpn", ctx.by_mpn[(category.id, mpn.upper())]
    if product_id is None and fingerprint in ctx.by_fingerprint:
        holder = ctx.products.get(ctx.by_fingerprint[fingerprint])
        if erp_codes and _codes_conflict(holder, erp_codes):
            # same specifications, different ERP code: a different product
            issues.append(issue("erp_variant", product=holder.name_zh if holder else ""))
            fingerprint = compute_fingerprint(
                category.code, brand_canonical, category.attribute_schema, attributes,
                ctx.resolver.canonical, name_zh, erp_codes[0],
            )  # fmt: skip
            staged["fingerprint"] = fingerprint
        if fingerprint in ctx.by_fingerprint:
            match_type, product_id = "fingerprint", ctx.by_fingerprint[fingerprint]

    # A user's explicit choice in review overrides automatic matching.
    if edits.get("match_product_id"):
        match_type, product_id = "manual", int(edits["match_product_id"])
    if edits.get("force_new"):
        match_type, product_id = "new", None

    if product_id is not None and product_id in ctx.products:
        product = ctx.products[product_id]
        return _compare(product, match_type or "", staged, issues, fingerprint)

    candidates: list[dict[str, Any]] = []
    if not edits.get("force_new"):
        grams = trigrams(name_zh)
        scored = [
            (similarity(grams, other), pid, name)
            for pid, name, other in ctx.names.get(category.id, [])
            # a product with another ERP code is never the same product
            if not (erp_codes and _codes_conflict(ctx.products.get(pid), erp_codes))
        ]
        candidates = [
            {"product_id": pid, "name_zh": name, "score": round(score, 3)}
            for score, pid, name in sorted(scored, reverse=True)[:3]
            if score >= FUZZY_THRESHOLD
        ]
    staged_json = jsonable(staged)
    if candidates:
        return Analysis(
            "possible_match", None, "fuzzy", None, candidates, issues, staged_json, fingerprint
        )
    return Analysis("new", "create", "new", None, [], issues, staged_json, fingerprint)


def _codes_conflict(product: Product | None, erp_codes: list[str]) -> bool:
    codes = erp_codes_of(product) if product is not None else set()
    return bool(codes) and not codes & set(erp_codes)


def _compare(
    product: Product,
    match_type: str,
    staged: dict[str, Any],
    issues: list[dict[str, Any]],
    fingerprint: str,
) -> Analysis:
    diff: dict[str, Any] = {"prices": {}, "fields": []}
    changed = False
    if match_type in ("erp", "mpn") and product.fingerprint != fingerprint:
        issues.append(issue("identity_changed"))
    current = {
        "standard": product.current_price_usd,
        "forecast": product.current_price_tier_forecast_usd,
    }
    for price in staged["prices"]:
        old = current.get(price["tier"])
        new = price["price_usd"]
        entry: dict[str, Any] = {"old": old, "new": new, "pct": None}
        if old is None or old != new:
            changed = True
            if old:
                pct = ((new - old) / old * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                entry["pct"] = pct
                if abs(pct) > PRICE_SWING_PCT:
                    issues.append(issue("price_swing", pct=pct))
        if product.price_date and price["price_date"] < product.price_date:
            issues.append(issue("older_price_date", current=product.price_date))
        diff["prices"][price["tier"]] = entry
    fields = staged["fields"]
    for key in COMPARED_FIELDS:
        if key == "status" and product.status == "inactive":
            continue  # a manual deactivation is never overwritten by an import
        if getattr(product, key) != fields.get(key):
            diff["fields"].append(key)
    new_attrs = {k: v for k, v in staged["attributes"].items() if product.attributes.get(k) != v}
    if new_attrs:
        diff["fields"].append("attributes")
    if diff["fields"]:
        changed = True
    staged = {**staged, "diff": diff}
    status = "updated" if changed else "unchanged"
    return Analysis(
        status,
        "update" if changed else "skip",
        match_type,
        product.id,
        [],
        issues,
        jsonable(staged),
        f"product:{product.id}",
    )
