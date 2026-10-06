"""Apply a reviewed import to the catalog, and undo it (plan §4.1 step 7).

Commit runs in one transaction: every created or updated product, every new price
row, and the import's status change land together or not at all. Each row records
what it changed in ``commit_info`` so revert can restore the previous state exactly.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.errors import ProblemError
from app.models import Brand, BrandAlias, Import, ImportRow, PriceHistory, Product
from app.services import catalog, search
from app.services.importer import assembly
from app.services.importer.matcher import FLAG_FIELDS
from app.services.importer.normalize import brand_key

RESTORABLE_FIELDS = (
    "category_id", "brand_id", "name_zh", "name_en", "name_en_auto", "attributes", "erp_code",
    "erp_code_alt", "mpn", "status", *FLAG_FIELDS, "stock_qty", "demand_qty", "stock_after_qty",
    "max_order_qty", "from_stock_qty", "payment_terms", "supply_note", "market", "notes_raw",
    "platform", "last_import_id",
)  # fmt: skip


def _snapshot(product: Product) -> dict[str, Any]:
    return {k: getattr(product, k) for k in RESTORABLE_FIELDS}


def _brand_for(session: Session, staged: dict[str, Any], created: dict[str, Brand]) -> int | None:
    if staged.get("brand_id"):
        return int(staged["brand_id"])
    name = (staged.get("brand_name") or "").strip()
    if not name:
        return None
    key = brand_key(name)
    if key in created:
        return created[key].id
    # "江波龙（Airdisk）" -> canonical Airdisk, Chinese name 江波龙
    match = re.fullmatch(r"(.+?)\s*[(（](.+?)[)）]", name)
    zh, en = (match.group(1), match.group(2)) if match else (None, name)
    if zh and not re.search(r"[一-鿿]", zh):
        zh, en = None, name
    canonical = en.strip()
    existing = session.scalar(select(Brand).where(func.lower(Brand.canonical) == canonical.lower()))
    if existing is not None:
        created[key] = existing
        return existing.id
    brand = Brand(canonical=canonical, name_en=canonical, name_zh=zh, needs_review=True)
    session.add(brand)
    taken = set(session.scalars(select(BrandAlias.alias_key)))
    for alias, lang in ((name, "zh" if zh else "en"), (canonical, "en"), (zh, "zh")):
        if alias and brand_key(alias) not in taken:
            taken.add(brand_key(alias))
            brand.aliases.append(BrandAlias(alias=alias, alias_key=brand_key(alias), lang=lang))
    session.flush()
    created[key] = brand
    return brand.id


def _product_data(staged: dict[str, Any], brand_id: int | None) -> dict[str, Any]:
    fields = staged["fields"]
    return {
        "category_id": staged["category_id"],
        "brand_id": brand_id,
        "name_zh": staged["name_zh"],
        "name_en": staged.get("name_en"),
        "attributes": staged["attributes"],
        "mpn": staged.get("mpn"),
        **{k: v for k, v in fields.items()},
    }


def _apply_prices(
    session: Session, imp: Import, product: Product, staged: dict[str, Any]
) -> dict[str, int | None]:
    """New current prices; returns the previously current row id per tier for revert."""
    previous: dict[str, int | None] = {}
    for price in staged["prices"]:
        tier = price["tier"]
        previous[tier] = session.scalar(
            select(PriceHistory.id).where(
                PriceHistory.product_id == product.id,
                PriceHistory.tier == tier,
                PriceHistory.is_current.is_(True),
            )
        )
        catalog.set_price(
            session,
            product,
            Decimal(price["price_usd"]),
            tier=tier,
            price_date=date.fromisoformat(price["price_date"]) if price.get("price_date") else None,
            import_id=imp.id,
            source_ref=price.get("source_ref"),
            amount_original=Decimal(price["amount_original"])
            if price.get("amount_original")
            else None,
            currency_original=price.get("currency_original"),
            fx_rate=Decimal(price["fx_rate"]) if price.get("fx_rate") else None,
        )
    return previous


def commit_import(session: Session, imp: Import) -> dict[str, int]:
    if imp.status != "review":
        raise ProblemError(409, "import.not_in_review", "Only an import in review can be committed")
    rows = list(
        session.scalars(
            select(ImportRow)
            .where(ImportRow.import_id == imp.id)
            .order_by(ImportRow.sheet, ImportRow.row_index, ImportRow.id)
        )
    )
    undecided = [r for r in rows if r.status == "possible_match" and r.decision is None]
    if undecided:
        raise ProblemError(
            409,
            "import.undecided",
            "Decide every possible match first",
            count=len(undecided),
        )
    stats = {"new": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    failures: list[tuple[int, dict[str, Any]]] = []
    created_brands: dict[str, Brand] = {}
    brands_before = set(session.scalars(select(Brand.id)))
    for row in rows:
        staged = row.parsed.get("staged") or {}
        if row.decision not in ("create", "update"):
            stats["unchanged" if row.status == "unchanged" else "skipped"] += 1
            continue
        try:
            with session.begin_nested():
                brand_id = _brand_for(session, staged, created_brands)
                data = _product_data(staged, brand_id)
                if row.decision == "update" and row.matched_product_id:
                    product = session.get(Product, row.matched_product_id)
                    if product is None:
                        raise ProblemError(
                            409, "import.product_gone", "Matched product was deleted"
                        )
                    before = _snapshot(product)
                    if product.status == "inactive":
                        data.pop("status")
                    data["attributes"] = {**product.attributes, **data["attributes"]}
                    codes = [
                        c for c in [staged.get("erp_code"), *staged.get("erp_code_alt", [])] if c
                    ]
                    known = {product.erp_code, *(product.erp_code_alt or [])}
                    if product.erp_code is None and codes:
                        data["erp_code"] = codes.pop(0)
                    extra = [c for c in codes if c not in known and c != data.get("erp_code")]
                    if extra:
                        data["erp_code_alt"] = [*(product.erp_code_alt or []), *extra]
                    for key in ("name_en", "mpn"):  # don't blank fields the row lacks
                        if not data.get(key):
                            data.pop(key, None)
                    catalog.update_product(session, product, data)
                    created = False
                    stats["updated"] += 1
                else:
                    data["erp_code"] = staged.get("erp_code")
                    data["erp_code_alt"] = staged.get("erp_code_alt") or []
                    data["name_en_auto"] = bool(data.get("name_en"))
                    product = catalog.create_product(session, data)
                    product.created_import_id = imp.id
                    before = None
                    created = True
                    stats["new"] += 1
                product.last_import_id = imp.id
                previous = _apply_prices(session, imp, product, staged)
                search.index_product(session, product)
                row.commit_info = {
                    "product_id": product.id,
                    "created": created,
                    "previous_prices": previous,
                    "before": _jsonable_snapshot(before),
                }
        except ProblemError as exc:
            failures.append(
                (row.id, {"code": "commit_failed", "key": exc.key, "detail": exc.detail})
            )
    if failures:
        # nothing is applied; keep only the per-row error notes so review shows them
        session.rollback()
        for row_id, problem in failures:
            failed = session.get(ImportRow, row_id)
            if failed is not None:
                failed.issues = [*failed.issues, problem]
        session.commit()
        raise ProblemError(
            409, "import.commit_failed", "Some rows could not be applied", errors=len(failures)
        )
    linked = assembly.link_configurations(session, rows)
    imp.status = "committed"
    imp.committed_at = datetime.now(UTC)
    imp.stats = {
        **imp.stats,
        "committed": stats,
        "configurations": linked,
        "created_brands": sorted(set(session.scalars(select(Brand.id))) - brands_before),
    }
    session.commit()
    return stats


def _jsonable_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in snapshot.items()}


def revert_import(session: Session, imp: Import) -> None:
    if imp.status != "committed":
        raise ProblemError(409, "import.not_committed", "Only a committed import can be reverted")
    later = session.scalar(
        select(Import.id).where(
            Import.status == "committed", Import.committed_at > imp.committed_at
        )
    )
    if later is not None:
        raise ProblemError(
            409, "import.not_latest", "Revert the newer import first", newer_id=later
        )
    assembly.unlink_configurations(session, (imp.stats or {}).get("configurations") or [])
    rows = list(
        session.scalars(
            select(ImportRow)
            .where(ImportRow.import_id == imp.id, ImportRow.commit_info.is_not(None))
            .order_by(ImportRow.id.desc())
        )
    )
    for row in rows:
        info = row.commit_info or {}
        product = session.get(Product, info.get("product_id"))
        if product is None:
            continue
        session.execute(
            delete(PriceHistory).where(
                PriceHistory.product_id == product.id, PriceHistory.import_id == imp.id
            )
        )
        for previous_id in (info.get("previous_prices") or {}).values():
            if previous_id:
                prev = session.get(PriceHistory, previous_id)
                if prev is not None:
                    prev.is_current = True
        session.flush()
        if info.get("created"):
            remaining = session.scalar(
                select(func.count()).where(PriceHistory.product_id == product.id)
            )
            if not remaining:
                catalog.delete_product(session, product)
                continue
        elif info.get("before"):
            for key, value in info["before"].items():
                setattr(product, key, value)
            session.flush()
            session.expire(product, ["category", "brand"])
            product.fingerprint = catalog.resolve_fingerprint(
                session, product.category, product.brand, product.attributes, product.name_zh,
                product.erp_code, product.id,
            )  # fmt: skip
        catalog.refresh_current_price(session, product)
        search.index_product(session, product)
        row.commit_info = None
    session.flush()
    for brand_id in (imp.stats or {}).get("created_brands", []):
        brand = session.get(Brand, brand_id)
        if brand and not session.scalar(select(func.count()).where(Product.brand_id == brand_id)):
            session.delete(brand)
    imp.status = "reverted"
    session.commit()
