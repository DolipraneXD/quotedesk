from types import SimpleNamespace

import pytest

from app.seed import NOTE_RULES
from app.services.notes import apply_note_rules

RULES = [
    SimpleNamespace(pattern=p, field=f, kind=k, value=v, enabled=True) for p, f, k, v in NOTE_RULES
]


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("接单前确认", {"confirm_before_order": True}),
        ("实单前需确认", {"confirm_before_order": True}),
        ("已发停产通知，交期需确认", {"status": "discontinued", "lead_time_confirm": True}),
        ("停产", {"status": "discontinued"}),
        ("消耗完库存不接", {"status": "stock_only"}),
        ("无货无供应", {"status": "no_supply"}),
        ("Q4供应良好", {"supply_note": "Q4供应良好"}),
        ("可接单3.7K", {"max_order_qty": 3700}),
        ("可接单20K", {"max_order_qty": 20000}),
        ("库存可接12K", {"from_stock_qty": 12000}),
        ("库存可接1629pcs", {"from_stock_qty": 1629}),
        (
            "可接13K,预付30%，尾款到发货",
            {"max_order_qty": 13000, "payment_terms": "可接13K,预付30%，尾款到发货"},
        ),
        ("新料需验证", {"needs_validation": True}),
        ("现询", {"quote_on_request": True}),
        ("主推", {"recommended": True}),
        ("大众市场", {"market": "consumer"}),
        ("random remark", {}),
        ("", {}),
        (None, {}),
    ],
)
def test_note_rules(note, expected):
    assert apply_note_rules(note, RULES) == expected


def test_disabled_rule_is_skipped():
    rules = [SimpleNamespace(**{**vars(r), "enabled": False}) for r in RULES]
    assert apply_note_rules("接单前确认", rules) == {}
