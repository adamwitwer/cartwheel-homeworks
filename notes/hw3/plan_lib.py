"""Shared lookups and row builders for the HW3 plan scripts.

Used by build_plan.py (pilot) and build_final_plan.py (final). Every answer key is
computed from the database, facts.yaml, seed/eligibility.py, and the policy
documents. The database is opened read-only.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from rapidfuzz import fuzz

from agent.config import db_path, load_facts
from agent.helpcenter import load_policy_docs
from seed.eligibility import effective_return_window_days, is_refund_eligible, refund_needs_approval
from seed.generate import WORLD_ASOF

FACTS = load_facts()
POLICY_IDS = {doc.policy_id for doc in load_policy_docs()}
FIND_ORDER_MIN_SCORE = 70  # same cutoff as agent/tools.py find_order

conn = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def user(user_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    assert row is not None, f"no user {user_id}"
    return row


def order(order_id: int) -> dict:
    row = conn.execute(
        """SELECT o.*, p.title, p.store_id AS product_store_id, s.name AS store_name,
                  s.slug, s.return_window_days_override AS override,
                  s.restocking_fee_opt_in AS restocking
           FROM orders o JOIN products p ON p.id = o.product_id
           JOIN stores s ON s.id = o.store_id WHERE o.id = ?""",
        (order_id,),
    ).fetchone()
    assert row is not None, f"no order {order_id}"
    o = dict(row)
    o["total_usd"] = o["total_cents"] / 100
    o["delivered"] = date.fromisoformat(o["delivered_at"]) if o["delivered_at"] else None
    o["age"] = (WORLD_ASOF - o["delivered"]).days if o["delivered"] else None
    return o


def can_view(role: str, user_id: int, o: dict) -> bool:
    """AUTH-1, checked from the rows rather than through the agent's own code."""
    if role == "support":
        return True
    if role == "shopper":
        return o["user_id"] == user_id
    return o["store_id"] == user(user_id)["store_id"]


def return_window(o: dict) -> tuple[int, str]:
    window = effective_return_window_days(FACTS["return_window_days"], o["override"])
    if o["override"] is None:
        return window, "cw-returns"
    store_policy = f"store-{o['slug']}-policy"
    assert store_policy in POLICY_IDS, store_policy
    return window, store_policy


def eligibility(o: dict) -> dict:
    window, policy = return_window(o)
    eligible = is_refund_eligible(
        status=o["status"], delivered_at=o["delivered"], as_of=WORLD_ASOF, return_window_days=window
    )
    assert bool(o["refund_eligible"]) == eligible, f"order {o['id']}: seeded flag disagrees"
    last_day = o["delivered"] + timedelta(days=window)
    return {"eligible": eligible, "window": window, "policy": policy, "last_day": last_day.isoformat()}


def matching_orders(user_id: int, phrase: str) -> list[int]:
    """Orders of this shopper whose product title find_order would match for `phrase`."""
    rows = conn.execute(
        "SELECT o.id, p.title FROM orders o JOIN products p ON p.id = o.product_id WHERE o.user_id = ?",
        (user_id,),
    ).fetchall()
    return [r["id"] for r in rows if fuzz.partial_ratio(phrase.lower(), r["title"].lower()) >= FIND_ORDER_MIN_SCORE]


def product_search(query: str, store_id: int | None = None, max_price_usd: float | None = None) -> list[dict]:
    """TOOL-3 semantics, written in SQL terms: every token in title or description."""
    rows = conn.execute(
        "SELECT * FROM products WHERE (? IS NULL OR store_id = ?)", (store_id, store_id)
    ).fetchall()
    tokens = query.lower().split()
    hits = [
        r for r in rows
        if all(t in f"{r['title']} {r['description']}".lower() for t in tokens)
        and (max_price_usd is None or r["price_cents"] / 100 <= max_price_usd)
    ]
    hits.sort(key=lambda r: (r["price_cents"], r["id"]))
    return [{"product_id": r["id"], "title": r["title"], "price_usd": r["price_cents"] / 100} for r in hits]


def dq_case(case_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM data_quality_cases WHERE case_id = ?", (case_id,)).fetchone()
    assert row is not None, case_id
    return row


def ago(days: int) -> str:
    """How a user would describe a delivery age, without an exact date."""
    if days <= 10:
        return "about a week ago"
    if days <= 17:
        return "about two weeks ago"
    if days <= 24:
        return "about three weeks ago"
    if days <= 28:
        return "three or four weeks ago"
    if days <= 37:
        return "about a month ago"
    return "about six weeks ago"


def objective(outcome: str, reason: str, source_type: str, reference: str) -> dict:
    return {
        "evaluation": "objective",
        "outcome": outcome,
        "reason": reason,
        "source": {"type": source_type, "reference": reference},
    }


def judgment(criterion: str, reference: str) -> dict:
    return {
        "evaluation": "human_judgment",
        "criterion": criterion,
        "source": {"type": "specification", "reference": reference},
    }


class Plan:
    """Rows of one plan, numbered with `id_format` (e.g. "pilot-{:03d}")."""

    def __init__(self, id_format: str):
        self.id_format = id_format
        self.rows: list[dict] = []

    def add(self, group, role, user_id, intent, record_state, policy, tools, difficulty, style,
            escalation, expected, goal, facts, followups=(), dq=None, **ids):
        who = user(user_id)
        assert who["role"] == role, f"user {user_id} is {who['role']}, not {role}"
        if dq is not None:
            case = dq_case(dq)
            assert ids.get(f"{case['entity_type']}_id") == case["entity_id"], dq
        self.rows.append({
            "id": self.id_format.format(len(self.rows) + 1),
            "scenario_group": group,
            "data_quality_case_id": dq,
            "tuple": {
                "role": role, "user_id": user_id, "intent": intent, "record_state": record_state,
                "applicable_policy": policy, "tools_needed": tools, "difficulty": difficulty,
                "user_style": style, "turn_count": 1 + len(followups), "escalation": escalation, **ids,
            },
            "expected": expected,
            "generation": {
                "role": role, "goal": goal, "user_visible_facts": facts,
                "style": style, "followup_plan": list(followups),
            },
        })


def shopper_order(order_id: int, user_id: int, phrase: str | None = None, status: str | None = None) -> dict:
    """Load a shopper's order and check ownership, status, and find_order uniqueness."""
    o = order(order_id)
    assert can_view("shopper", user_id, o), f"shopper {user_id} cannot see {order_id}"
    if status:
        assert o["status"] == status, f"order {order_id} is {o['status']}"
    if phrase:
        hits = matching_orders(user_id, phrase)
        assert hits == [order_id], f"'{phrase}' matches {hits} for shopper {user_id}"
    return o
