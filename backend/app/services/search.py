"""Product full-text search over the ``products_fts`` FTS5 table (trigram tokenizer).

Trigram matching needs at least 3 characters, but many useful Chinese terms are 2
(镁光, 威刚). Shorter terms fall back to LIKE on the same table; at 50k rows a scan of
the FTS content is still well under the 100 ms budget.
"""

from __future__ import annotations

from sqlalchemy import Select, select, text
from sqlalchemy.orm import Session

from app.models import Product

FTS_COLUMNS = ("name_zh", "name_en", "erp_code", "mpn", "brand", "attributes_text")


def _attributes_text(product: Product) -> str:
    return " ".join(str(v) for v in (product.attributes or {}).values() if v not in (None, ""))


def index_product(session: Session, product: Product) -> None:
    brand = product.brand
    brand_text = " ".join(x for x in ([brand.canonical, brand.name_zh or ""] if brand else []) if x)
    session.execute(text("DELETE FROM products_fts WHERE rowid = :id"), {"id": product.id})
    session.execute(
        text(
            "INSERT INTO products_fts(rowid, name_zh, name_en, erp_code, mpn, brand, "
            "attributes_text) VALUES (:id, :name_zh, :name_en, :erp, :mpn, :brand, :attrs)"
        ),
        {
            "id": product.id,
            "name_zh": product.name_zh,
            "name_en": product.name_en or "",
            "erp": " ".join([product.erp_code or "", *(product.erp_code_alt or [])]).strip(),
            "mpn": product.mpn or "",
            "brand": brand_text,
            "attrs": _attributes_text(product),
        },
    )


def remove_product(session: Session, product_id: int) -> None:
    session.execute(text("DELETE FROM products_fts WHERE rowid = :id"), {"id": product_id})


def reindex_all(session: Session) -> int:
    session.execute(text("DELETE FROM products_fts"))
    count = 0
    for product in session.scalars(select(Product)):
        index_product(session, product)
        count += 1
    return count


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def matching_ids_query(q: str) -> Select[tuple[int]] | None:
    """A ``SELECT rowid`` over products_fts matching every whitespace-separated term."""
    terms = [t for t in q.split() if t]
    if not terms:
        return None
    clauses: list[str] = []
    params: dict[str, str] = {}
    long_terms = [t for t in terms if len(t) >= 3]
    if long_terms:
        params["match"] = " AND ".join('"' + t.replace('"', '""') + '"' for t in long_terms)
        clauses.append("products_fts MATCH :match")
    for i, term in enumerate(t for t in terms if len(t) < 3):
        params[f"like{i}"] = f"%{_escape_like(term)}%"
        ors = " OR ".join(f"{col} LIKE :like{i} ESCAPE '\\'" for col in FTS_COLUMNS)
        clauses.append(f"({ors})")
    sql = "SELECT rowid AS id FROM products_fts WHERE " + " AND ".join(clauses)
    return select(text("id")).select_from(text(f"({sql}) AS fts_hits")).params(**params)
