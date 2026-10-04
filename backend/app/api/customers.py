from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import or_, select

from app.api.deps import SessionDep
from app.errors import ProblemError
from app.models import Customer
from app.schemas.quotes import CustomerCreate, CustomerOut, CustomerUpdate

router = APIRouter(prefix="/customers", tags=["customers"])


def _get(session: SessionDep, customer_id: int) -> Customer:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise ProblemError(404, "customer.not_found", "Customer not found", id=customer_id)
    return customer


def _check_code(session: SessionDep, code: str, exclude_id: int | None) -> str:
    code = code.strip().upper()
    clash = session.scalar(select(Customer).where(Customer.code == code))
    if clash is not None and clash.id != exclude_id:
        raise ProblemError(409, "customer.code_taken", "Code already used", code=code)
    return code


@router.get("", response_model=list[CustomerOut])
def list_customers(session: SessionDep, q: str | None = None) -> list[Customer]:
    stmt = select(Customer).order_by(Customer.code)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Customer.code.ilike(like),
                Customer.name.ilike(like),
                Customer.contact_name.ilike(like),
            )
        )
    return list(session.scalars(stmt))


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(session: SessionDep, body: CustomerCreate) -> Customer:
    data = body.model_dump(exclude_none=True)
    data["code"] = _check_code(session, body.code, None)
    customer = Customer(**data)
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(session: SessionDep, customer_id: int) -> Customer:
    return _get(session, customer_id)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(session: SessionDep, customer_id: int, body: CustomerUpdate) -> Customer:
    customer = _get(session, customer_id)
    data = body.model_dump(exclude_unset=True)
    if "code" in data:
        data["code"] = _check_code(session, data["code"] or "", customer.id)
    if "name" in data and not (data["name"] or "").strip():
        raise ProblemError(422, "customer.name_required", "The customer name is required")
    for key, value in data.items():
        setattr(customer, key, value)
    session.commit()
    session.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=204)
def delete_customer(session: SessionDep, customer_id: int) -> Response:
    """Quotes keep their customer snapshot; their link becomes empty."""
    session.delete(_get(session, customer_id))
    session.commit()
    return Response(status_code=204)
