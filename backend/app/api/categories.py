from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import SessionDep
from app.errors import ProblemError
from app.models import Category, Product
from app.schemas.catalog import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


def _out(category: Category, count: int) -> CategoryOut:
    out = CategoryOut.model_validate(category)
    out.product_count = count
    return out


def _counts(session: SessionDep) -> dict[int, int]:
    rows = session.execute(select(Product.category_id, func.count()).group_by(Product.category_id))
    return {cid: n for cid, n in rows}


def _validate_schema(body: CategoryCreate | CategoryUpdate) -> None:
    if body.attribute_schema is None:
        return
    keys = [f.key for f in body.attribute_schema]
    if len(keys) != len(set(keys)):
        raise ProblemError(422, "category.duplicate_attribute", "Attribute keys must be unique")


@router.get("", response_model=list[CategoryOut])
def list_categories(session: SessionDep) -> list[CategoryOut]:
    counts = _counts(session)
    categories = session.scalars(select(Category).order_by(Category.sort_order, Category.id))
    return [_out(c, counts.get(c.id, 0)) for c in categories]


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(session: SessionDep, body: CategoryCreate) -> CategoryOut:
    _validate_schema(body)
    if session.scalar(select(Category).where(Category.code == body.code)):
        raise ProblemError(409, "category.duplicate_code", "Category code exists", code=body.code)
    data = body.model_dump()
    category = Category(**data)
    session.add(category)
    session.commit()
    return _out(category, 0)


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(session: SessionDep, category_id: int, body: CategoryUpdate) -> CategoryOut:
    """Edit names, margin or the attribute schema.

    Changing which attributes are in the fingerprint does not rewrite existing
    fingerprints; they are recomputed the next time each product is saved or imported.
    """
    category = session.get(Category, category_id)
    if category is None:
        raise ProblemError(404, "category.not_found", "Category not found", id=category_id)
    _validate_schema(body)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(category, key, value)
    session.commit()
    return _out(category, _counts(session).get(category.id, 0))
