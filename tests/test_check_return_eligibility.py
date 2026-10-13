"""HW1 additional tool: check_return_eligibility (offline, no API keys)."""

from __future__ import annotations

import pytest

from agent import db, tools
from agent.agent import TOOLS_BY_ROLE
from agent.auth import AuthContext

SHOPPER_1 = AuthContext(user_id=1, role="shopper")
MERCHANT_STORE_2 = AuthContext(user_id=9002, role="merchant", store_id=2)
SUPPORT = AuthContext(user_id=9501, role="support")
DATA_QUALITY_ORDERS = {8001, 8002}


def test_outside_platform_window_explains_and_cites(world: dict) -> None:
    result = tools.check_return_eligibility(SHOPPER_1, 3980)
    assert result["ok"] is True
    assert result["eligible"] is False
    assert result["return_window_days"] == 30
    assert result["window_source"] == "platform_default"
    assert result["policy_id"] == "cw-returns"
    assert result["delivered_at"] == "2026-05-17"
    assert result["last_day_to_return"] == "2026-06-16"
    assert result["days_since_delivery"] == 45
    assert "cw-returns" in result["reason"]


def test_inside_platform_window(world: dict) -> None:
    result = tools.check_return_eligibility(SHOPPER_1, 4127)
    assert result["ok"] is True
    assert result["eligible"] is True
    assert result["last_day_to_return"] == "2026-07-19"


def test_store_override_takes_precedence(world: dict) -> None:
    # Juniper Home Goods (store 2) has a 14-day window; order 569 was
    # delivered 25 days before the as-of date, inside the platform's 30.
    result = tools.check_return_eligibility(MERCHANT_STORE_2, 569)
    assert result["ok"] is True
    assert result["eligible"] is False
    assert result["return_window_days"] == 14
    assert result["window_source"] == "store_override"
    assert result["policy_id"] == "store-juniper-home-goods-policy"


@pytest.mark.parametrize("status_order,status", [(180, "placed"), (335, "shipped"), (3988, "refunded")])
def test_not_delivered_or_already_closed_is_not_eligible(world: dict, status_order: int, status: str) -> None:
    result = tools.check_return_eligibility(SUPPORT, status_order)
    assert result["ok"] is True
    assert result["status"] == status
    assert result["eligible"] is False
    assert status in result["reason"]


def test_scope_is_checked_before_revealing_anything(world: dict) -> None:
    result = tools.check_return_eligibility(MERCHANT_STORE_2, 4127)
    assert result == {
        "ok": False,
        "error": "permission_denied",
        "reason": "role 'merchant' (user 9002) may not view order #4127",
    }


def test_unknown_order(world: dict) -> None:
    assert tools.check_return_eligibility(SUPPORT, 999999)["error"] == "not_found"


@pytest.mark.parametrize("order_id", sorted(DATA_QUALITY_ORDERS))
def test_inconsistent_records_get_no_answer(world: dict, order_id: int) -> None:
    result = tools.check_return_eligibility(SUPPORT, order_id)
    assert result["ok"] is False
    assert result["error"] == "inconsistent_record"
    assert "eligible" not in result


def test_agrees_with_stamped_refund_eligible_for_every_order(world: dict) -> None:
    with db.connection() as conn:
        orders = [row["id"] for row in conn.execute("SELECT id FROM orders ORDER BY id")]
        stamped = {
            row["id"]: bool(row["refund_eligible"])
            for row in conn.execute("SELECT id, refund_eligible FROM orders")
        }
    for order_id in orders:
        if order_id in DATA_QUALITY_ORDERS:
            continue
        result = tools.check_return_eligibility(SUPPORT, order_id)
        assert result["ok"] is True, (order_id, result)
        assert result["eligible"] is stamped[order_id], order_id


def test_registered_for_every_role() -> None:
    for role, role_tools in TOOLS_BY_ROLE.items():
        assert "check_return_eligibility" in [tool.name for tool in role_tools], role
