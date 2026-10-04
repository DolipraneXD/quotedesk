"""Note rules (plan §1.4, §6): remark patterns (备注) that set product flags on import."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import SessionDep
from app.errors import ProblemError
from app.models import NoteRule
from app.schemas.catalog import NoteRuleOut

router = APIRouter(prefix="/note-rules", tags=["note rules"])


class NoteRuleIn(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=300)
    field: str | None = Field(default=None, min_length=1, max_length=60)
    kind: Literal["set", "qty", "text"] | None = None
    value: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    sort_order: int | None = None


def _check(rule: NoteRule) -> None:
    try:
        compiled = re.compile(rule.pattern)
    except re.error as exc:
        raise ProblemError(422, "note_rule.bad_pattern", str(exc), error=str(exc)) from exc
    if rule.kind == "qty" and compiled.groups < 1:
        raise ProblemError(422, "note_rule.qty_group", "A quantity rule needs a (number) group")
    if rule.kind == "set" and not rule.value:
        raise ProblemError(422, "note_rule.value_required", "A set rule needs a value")


def _get(session: SessionDep, rule_id: int) -> NoteRule:
    rule = session.get(NoteRule, rule_id)
    if rule is None:
        raise ProblemError(404, "note_rule.not_found", "Rule not found", id=rule_id)
    return rule


@router.get("", response_model=list[NoteRuleOut])
def list_rules(session: SessionDep) -> list[NoteRule]:
    return list(session.scalars(select(NoteRule).order_by(NoteRule.sort_order, NoteRule.id)))


@router.post("", response_model=NoteRuleOut, status_code=201)
def create_rule(session: SessionDep, body: NoteRuleIn) -> NoteRule:
    if not body.pattern or not body.field:
        raise ProblemError(422, "note_rule.incomplete", "Pattern and field are required")
    last = session.scalar(select(func.max(NoteRule.sort_order))) or 0
    rule = NoteRule(
        pattern=body.pattern,
        field=body.field,
        kind=body.kind or "set",
        value=body.value,
        enabled=body.enabled is not False,
        sort_order=last + 1,
    )
    _check(rule)
    session.add(rule)
    session.commit()
    return rule


@router.patch("/{rule_id}", response_model=NoteRuleOut)
def update_rule(session: SessionDep, rule_id: int, body: NoteRuleIn) -> NoteRule:
    rule = _get(session, rule_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None or key == "value":
            setattr(rule, key, value)
    _check(rule)
    session.commit()
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(session: SessionDep, rule_id: int) -> Response:
    session.delete(_get(session, rule_id))
    session.commit()
    return Response(status_code=204)
