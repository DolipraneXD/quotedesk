"""Turns free-text remarks (备注) into product flags using the note_rules table."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol


class Rule(Protocol):
    pattern: str
    field: str
    kind: str
    value: str | None
    enabled: bool


def _parse_qty(number: str, unit: str | None) -> int | None:
    try:
        qty = Decimal(number)
    except InvalidOperation:
        return None
    if unit and unit.lower() == "k":
        qty *= 1000
    return int(qty)


def _coerce(value: str | None) -> Any:
    if value in ("true", "false"):
        return value == "true"
    return value


def apply_note_rules(note: str | None, rules: list[Rule]) -> dict[str, Any]:
    """Return the fields set by every matching rule; the first rule wins per field."""
    if not note:
        return {}
    result: dict[str, Any] = {}
    for rule in rules:
        if not rule.enabled or rule.field in result:
            continue
        match = re.search(rule.pattern, note, flags=re.IGNORECASE)
        if not match:
            continue
        if rule.kind == "qty":
            groups = match.groups()
            qty = _parse_qty(groups[0], groups[1] if len(groups) > 1 else None)
            if qty is not None:
                result[rule.field] = qty
        elif rule.kind == "text":
            result[rule.field] = note.strip()
        else:
            result[rule.field] = _coerce(rule.value)
    return result
