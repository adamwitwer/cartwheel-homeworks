"""Build the HW3 pilot plan: 30 grounded tuples with answer keys, no user messages yet.

The records below were picked with SQL against a freshly seeded database. This
script re-checks every record (status, store, age, owner, access) and computes
each answer key from the database, facts.yaml, seed/eligibility.py, and the
policy documents, never from a model. It writes notes/hw3/pilot_plan.jsonl.

Each row keeps two things apart:
  - `expected` and `tuple`: the answer key, for the reviewer only.
  - `generation`: what the simulated user knows. The message writer sees only this.

Run from the repository root:  uv run python notes/hw3/build_plan.py
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from rapidfuzz import fuzz

from agent.config import db_path, load_facts
from agent.helpcenter import load_policy_docs
from seed.eligibility import effective_return_window_days, is_refund_eligible, refund_needs_approval
from seed.generate import WORLD_ASOF

OUT = Path(__file__).with_name("pilot_plan.jsonl")
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


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

rows: list[dict] = []


def add(group, role, user_id, intent, record_state, policy, tools, difficulty, style,
        escalation, expected, goal, facts, followups=(), dq=None, **ids):
    who = user(user_id)
    assert who["role"] == role, f"user {user_id} is {who['role']}, not {role}"
    if dq is not None:
        case = dq_case(dq)
        assert ids.get(f"{case['entity_type']}_id") == case["entity_id"], dq
    rows.append({
        "id": f"pilot-{len(rows) + 1:03d}",
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


# --- Coverage ---------------------------------------------------------------

o = shopper_order(9180, 324, status="delivered")
add("coverage", "shopper", 324, "order_status", "delivered_in_window", "none", "one_lookup",
    "well_specified", "requests_short_plain_answer", "none",
    objective("report_delivered", f"Order 9180 ({o['title']}, {o['store_name']}) was delivered on {o['delivered_at']}.",
              "sql", "orders.id = 9180"),
    "find out whether the order has arrived",
    [f"bought {o['title']} from {o['store_name']}", "knows the order number: 9180"],
    order_id=9180)

o = shopper_order(9756, 184, phrase="wool socks", status="shipped")
add("coverage", "shopper", 184, "order_status", "shipped", "cw-shipping", "several_calls",
    "missing_information", "confused_rambling", "none",
    objective("report_shipped_not_delivered",
              f"Order 9756 ({o['title']}) shipped on {o['shipped_at']} and has no delivery date yet; "
              f"standard transit is up to {FACTS['shipping_transit_days_max']} days after shipment (cw-shipping).",
              "sql", "orders.id = 9756"),
    "find out where the wool socks are",
    [f"ordered {o['title']} from {o['store_name']} last week", "does not have the order number handy"],
    followups=["adds that it was wool socks from that knitwear shop, ordered last week"],
    order_id=9756)

o = shopper_order(2661, 289, phrase="trowel", status="delivered")
e = eligibility(o)
assert e["eligible"]
add("coverage", "shopper", 289, "return_eligibility", "delivered_in_window", e["policy"], "several_calls",
    "well_specified", "neutral_conversational", "none",
    objective("eligible", f"Delivered {o['delivered_at']} ({o['age']} days ago); the {e['window']}-day window "
              f"({e['policy']}) is open through {e['last_day']}.", "eligibility_function", "seed.eligibility.is_refund_eligible"),
    "ask whether the trowel set can still be returned",
    [f"bought a {o['title']} from {o['store_name']}", f"it arrived {ago(o['age'])}", "no order number"],
    order_id=2661)

o = shopper_order(5339, 79, phrase="wooden train", status="delivered")
e = eligibility(o)
assert e["eligible"] and not refund_needs_approval(o["total_usd"], FACTS["refund_auto_approve_threshold_usd"])
add("coverage", "shopper", 79, "refund", "delivered_in_window", "cw-refunds", "several_calls",
    "well_specified", "terse_fragmentary", "none",
    objective("refund_auto_approved", f"Eligible ({o['age']} days, {e['window']}-day window); the full ${o['total_usd']:.2f} "
              f"is at or below the ${FACTS['refund_auto_approve_threshold_usd']} threshold, so issue_refund auto-approves.",
              "eligibility_function", "seed.eligibility.refund_needs_approval"),
    "get a refund for a broken toy train",
    [f"bought a {o['title']} from {o['store_name']}", f"paid ${o['total_usd']:.2f}", f"it arrived {ago(o['age'])}",
     "a wheel snapped off", "no order number"],
    followups=["gives the reason: a wheel came off on day one"],
    order_id=5339)

o = shopper_order(7350, 219, phrase="poetry", status="delivered")
e = eligibility(o)
assert e["eligible"] and refund_needs_approval(o["total_usd"], FACTS["refund_auto_approve_threshold_usd"])
add("coverage", "shopper", 219, "refund", "refund_above_threshold", "cw-refunds", "several_calls",
    "well_specified", "frustrated_impatient", "ESC-1",
    objective("refund_queued_for_approval", f"Eligible, but ${o['total_usd']:.2f} is above the "
              f"${FACTS['refund_auto_approve_threshold_usd']} threshold, so the refund is queued for a human (ESC-1, "
              "cw-refunds). The agent must not say the money has been refunded.",
              "eligibility_function", "seed.eligibility.refund_needs_approval"),
    "get a full refund for a poetry book that arrived damaged",
    [f"bought the {o['title']} from {o['store_name']}", f"paid ${o['total_usd']:.2f}", f"it arrived {ago(o['age'])}",
     "the cover was torn", "no order number"],
    order_id=7350)

o = shopper_order(4385, 102, phrase="bar soap", status="placed")
add("coverage", "shopper", 102, "cancellation", "placed", "cw-cancellations", "several_calls",
    "well_specified", "typo_heavy", "none",
    objective("order_cancelled", "Order 4385 is 'placed' (not shipped), so cancel_order succeeds (cw-cancellations).",
              "sql", "orders.id = 4385"),
    "cancel an order that was just placed",
    [f"ordered {o['title']} from {o['store_name']} today", "changed their mind", "no order number"],
    order_id=4385)

hits = product_search("bluetooth speaker", max_price_usd=60)
assert hits
add("coverage", "shopper", 45, "product_search", "product", "none", "one_lookup",
    "well_specified", "requests_short_plain_answer", "none",
    objective("list_matching_products", "Products matching 'bluetooth speaker' at or under $60, cheapest first: "
              + "; ".join(f"#{h['product_id']} {h['title']} ${h['price_usd']:.2f}" for h in hits[:5]) + ".",
              "sql", "products: title or description contains 'bluetooth' and 'speaker', price_cents <= 6000"),
    "find a bluetooth speaker for under $60",
    ["shopping for a bluetooth speaker", "budget is $60"])

add("coverage", "shopper", 60, "policy_question", "none", "cw-shipping", "one_lookup",
    "well_specified", "confused_rambling", "none",
    objective("state_shipping_times", f"Stores ship within {FACTS['shipping_handling_days_max']} days of purchase; "
              f"standard delivery takes up to {FACTS['shipping_transit_days_max']} days in transit after shipment; cite cw-shipping.",
              "policy_document", "cw-shipping"),
    "learn how long delivery usually takes before buying a gift",
    ["wants to buy a birthday gift", "worried it will not arrive in time"])

add("coverage", "shopper", 77, "account_change", "none", "cw-escalations", "one_lookup",
    "well_specified", "repetitive_pressuring", "ESC-2",
    objective("escalate_without_changing_account", "Account changes always go to a human (cw-escalations, ESC-2) and are "
              "never made in chat (cw-account-security). The agent must not claim the email was changed.",
              "policy_document", "cw-escalations"),
    "change the email address on the account",
    ["got a new email address", "wants receipts to go to the new one"],
    followups=["asks again, more insistently, whether it can just be updated right now in this chat"])

add("coverage", "shopper", 88, "out_of_scope", "none", "none", "none",
    "well_specified", "frustrated_impatient", "none",
    judgment("The agent declines to give legal advice in one or two sentences, without a lecture, and says what it can "
             "help with (for example, checking an order or opening a support ticket).", "SCOPE-2, RESP-4, RESP-5"),
    "ask whether they can sue a store over a late delivery",
    ["a package arrived late and ruined their plans", "asking about legal action"])

o = shopper_order(7711, 189, phrase="tape measure", status="delivered")
assert o["age"] <= FACTS["dispute_window_days"]
add("coverage", "shopper", 189, "dispute", "delivered_in_window", "cw-disputes", "several_calls",
    "well_specified", "typo_heavy", "ESC-3",
    objective("escalate_dispute", f"Delivered {o['delivered_at']} ({o['age']} days, inside the {FACTS['dispute_window_days']}-day "
              "dispute window). Disputes are always handled by a human and never resolved automatically "
              "(cw-disputes, ESC-3): escalate, and do not issue a refund or promise an outcome.",
              "policy_document", "cw-disputes"),
    "dispute a charge for a package that shows delivered but never arrived",
    [f"ordered a {o['title']} from {o['store_name']}", "the order page says delivered, but nothing came",
     "was charged for it", "no order number"],
    followups=["says plainly that they want to dispute the charge"],
    order_id=7711)

o = order(546)
assert can_view("merchant", 9014, o) and o["status"] == "shipped"
add("coverage", "merchant", 9014, "order_status", "shipped", "none", "one_lookup",
    "well_specified", "operational_shorthand", "none",
    objective("report_shipped_not_delivered", f"Order 546 ({o['title']}) shipped {o['shipped_at']}; no delivery date yet.",
              "sql", "orders.id = 546"),
    "check the status of one of their store's orders",
    [f"runs {o['store_name']}", "order number 546"],
    order_id=546)

add("coverage", "merchant", 9012, "policy_question", "none", "cw-payouts", "one_lookup",
    "well_specified", "neutral_conversational", "none",
    objective("state_payout_schedule", f"Payouts run weekly on Fridays and take {FACTS['payout_processing_business_days']} "
              "business days to process; refunds issued during the week are deducted from the next payout; cite cw-payouts.",
              "policy_document", "cw-payouts"),
    "understand when payouts arrive",
    [f"runs {user(9012)['name']}'s shop on Cartwheel", "new merchant, first payout"],
    followups=["asks how a refund they issue this week affects their money"])

o = order(7941)
e = eligibility(o)
assert can_view("merchant", 9016, o) and e["eligible"]
assert not refund_needs_approval(o["total_usd"], FACTS["refund_auto_approve_threshold_usd"])
add("coverage", "merchant", 9016, "refund", "delivered_in_window", "cw-refunds", "several_calls",
    "well_specified", "operational_shorthand", "none",
    objective("refund_auto_approved", f"Order 7941 is in the merchant's store, eligible ({o['age']} days), and "
              f"${o['total_usd']:.2f} is at or below the threshold, so issue_refund auto-approves.",
              "eligibility_function", "seed.eligibility.refund_needs_approval"),
    "refund a customer whose sweater did not fit",
    [f"runs {o['store_name']}", "order number 7941", f"the customer paid ${o['total_usd']:.2f}",
     "the crewneck was too small"],
    order_id=7941)

hits = product_search("webcam", store_id=19)
assert hits
add("coverage", "merchant", 9019, "product_search", "product", "none", "one_lookup",
    "well_specified", "terse_fragmentary", "none",
    objective("list_matching_products", "Store 19 products matching 'webcam', cheapest first: "
              + "; ".join(f"#{h['product_id']} {h['title']} ${h['price_usd']:.2f}" for h in hits) + ".",
              "sql", "products: store_id = 19, title or description contains 'webcam'"),
    "see which webcams their store lists and at what prices",
    ["runs Pocket Arcade", "wants a quick price check on their webcam listings"])

o = order(1894)
assert o["status"] == "placed"
add("coverage", "support", 9502, "order_status", "placed", "none", "one_lookup",
    "well_specified", "operational_shorthand", "none",
    objective("report_placed_not_shipped", f"Order 1894 ({o['title']}) was placed {o['ordered_at']} and has not shipped.",
              "sql", "orders.id = 1894"),
    "check an order for a customer who is waiting",
    ["support staff", "a customer asked about order 1894"],
    order_id=1894)

o = order(1215)
assert o["status"] == "shipped"
add("coverage", "support", 9501, "cancellation", "shipped", "cw-cancellations", "several_calls",
    "well_specified", "frustrated_impatient", "none",
    objective("cancel_not_eligible", "Order 1215 has shipped, so cancel_order returns not_eligible; the buyer should wait "
              "for delivery and request a return (cw-cancellations). The agent must not say it was cancelled.",
              "sql", "orders.id = 1215"),
    "cancel an order for a customer",
    ["support staff", "a customer wants order 1215 cancelled"],
    followups=["says the customer is insisting and asks whether there is any way to push the cancellation through"],
    order_id=1215)

add("coverage", "support", 9505, "policy_question", "none", "cw-returns", "one_lookup",
    "well_specified", "requests_short_plain_answer", "none",
    objective("state_return_window_rules", f"Returns: {FACTS['return_window_days']} days, counted from the delivery date, not "
              "the purchase date (cw-returns); a store override on the store's own policy page takes precedence, stricter "
              "or looser (cw-store-overrides).", "policy_document", "cw-returns"),
    "confirm the return-window rule to answer a customer",
    ["support staff", "a customer asked whether the return clock starts at purchase or delivery, "
     "and whether every store uses the same window"])

# --- Challenge --------------------------------------------------------------

o = shopper_order(569, 333, phrase="dinner plate", status="delivered")
e = eligibility(o)
assert o["store_id"] == 2 and not e["eligible"] and o["age"] <= FACTS["return_window_days"]
add("challenge", "shopper", 333, "refund", "delivered_past_window", e["policy"], "several_calls",
    "boundary", "repetitive_pressuring", "none",
    objective("not_eligible", f"Delivered {o['delivered_at']} ({o['age']} days). Juniper Home Goods' {e['window']}-day window "
              f"({e['policy']}) closed on {e['last_day']}, although the platform's 30 days would still be open. Deny and cite "
              "the store policy.", "eligibility_function", "seed.eligibility.is_refund_eligible"),
    "get a refund for a dinner plate set",
    [f"bought the {o['title']} from {o['store_name']}", f"it arrived {ago(o['age'])}",
     "thinks Cartwheel gives 30 days for returns", "no order number"],
    followups=["pushes back, repeating that it has not even been 30 days"],
    order_id=569)

o = shopper_order(961, 338, phrase="field guide", status="delivered")
e = eligibility(o)
assert o["store_id"] == 7 and e["eligible"] and o["age"] > FACTS["return_window_days"]
add("challenge", "shopper", 338, "return_eligibility", "delivered_past_platform_window", e["policy"], "several_calls",
    "boundary", "confused_rambling", "none",
    objective("eligible", f"Delivered {o['delivered_at']} ({o['age']} days), past the platform's 30 days, but Northwind "
              f"Books' {e['window']}-day window ({e['policy']}) is open through {e['last_day']}.",
              "eligibility_function", "seed.eligibility.is_refund_eligible"),
    "ask whether a book can still be returned",
    [f"bought the {o['title']} from {o['store_name']}", f"it arrived {ago(o['age'])}",
     "assumes it is probably too late", "no order number"],
    order_id=961)

o = shopper_order(161, 212, phrase="socket set", status="delivered")
e = eligibility(o)
assert o["age"] == e["window"] == 30 and e["eligible"]
assert not refund_needs_approval(o["total_usd"], FACTS["refund_auto_approve_threshold_usd"])
add("challenge", "shopper", 212, "refund", "delivered_window_last_day", e["policy"], "several_calls",
    "boundary", "terse_fragmentary", "none",
    objective("refund_auto_approved", f"Delivered {o['delivered_at']}, exactly {o['age']} days ago; day 30 is still inside the "
              f"window (is_refund_eligible is inclusive, last day {e['last_day']}). ${o['total_usd']:.2f} auto-approves.",
              "eligibility_function", "seed.eligibility.is_refund_eligible"),
    "get a refund for a socket set",
    [f"bought an {o['title']} from {o['store_name']}", f"it arrived {ago(o['age'])}", "the sockets don't fit their bolts",
     "no order number"],
    order_id=161)

o = shopper_order(9709, 411, phrase="webcam", status="delivered")
e = eligibility(o)
threshold = FACTS["refund_auto_approve_threshold_usd"]
assert e["eligible"] and o["total_usd"] > threshold and not refund_needs_approval(float(threshold), threshold)
add("challenge", "shopper", 411, "refund", "delivered_in_window", "cw-refunds", "several_calls",
    "boundary", "typo_heavy", "none",
    objective("partial_refund_auto_approved", f"A partial refund of exactly ${threshold} on the ${o['total_usd']:.2f} order is "
              f"at (not above) the ${threshold} threshold, so issue_refund auto-approves it. Queuing it, or refunding the "
              "full amount, is wrong.", "eligibility_function", "seed.eligibility.refund_needs_approval"),
    "get some money back on a webcam with a broken microphone, keeping the camera",
    [f"bought a {o['title']} from {o['store_name']}", f"paid ${o['total_usd']:.2f}", f"it arrived {ago(o['age'])}",
     "video works, microphone does not", "no order number"],
    followups=["offers to keep the webcam if they get $100 back"],
    order_id=9709)

first = shopper_order(5820, 91, phrase="watering can", status="delivered")
o = shopper_order(6499, 91, phrase="utility knife", status="delivered")
e = eligibility(o)
assert eligibility(first)["eligible"] and not e["eligible"]
add("challenge", "shopper", 91, "return_eligibility", "delivered_past_window", e["policy"], "several_calls",
    "correction_across_turns", "neutral_conversational", "none",
    objective("not_eligible", f"After the correction the order is 6499 ({o['title']}, {o['store_name']}), delivered "
              f"{o['delivered_at']} ({o['age']} days); the {e['window']}-day window ({e['policy']}) closed on {e['last_day']}. "
              f"Answering about the first-mentioned order 5820 ({first['title']}, eligible) is wrong.",
              "eligibility_function", "seed.eligibility.is_refund_eligible"),
    "ask about returning an item, then correct which item they meant",
    [f"bought a {first['title']} from {first['store_name']} about three weeks ago",
     f"also bought the {o['title']} from {o['store_name']} {ago(o['age'])}",
     "first asks about the watering can by mistake; the one they really want to return is the utility knife", "no order numbers"],
    followups=["corrects themselves: not the watering can, they meant the utility knife",
               "adds that the knife is still in its original packaging"],
    order_id=6499)

o = order(105)
assert not can_view("merchant", 9007, o)
add("challenge", "merchant", 9007, "order_status", "outside_caller_scope", "none", "one_lookup",
    "authorization_boundary", "operational_shorthand", "none",
    objective("permission_denied_no_details", f"Order 105 belongs to store {o['store_id']}, not the caller's store "
              f"{user(9007)['store_id']} (AUTH-1). get_order returns permission_denied; the agent reveals nothing about the "
              "order (RESP-4).", "sql", "orders.id = 105, users.id = 9007"),
    "look up an order number a customer emailed them",
    ["runs Northwind Books", "a customer emailed asking about order 105 and the merchant assumes it is theirs"],
    order_id=105)

case = dq_case("dq-order-missing-delivery-date")
o = shopper_order(8002, 392, phrase="pencil set", status="delivered")
assert o["delivered_at"] is None
add("challenge", "shopper", 392, "return_eligibility", "damaged_record", "cw-returns", "several_calls",
    "damaged_record", "frustrated_impatient", "none",
    objective("do_not_compute_return_deadline", f"{case['description']} {case['expected_handling']}",
              "data_quality_table", case["case_id"]),
    "find out the last day to return a pencil set",
    [f"bought a {o['title']} from {o['store_name']}", "the order page says delivered", "no order number"],
    followups=["gets impatient: it says delivered right there, so why can't they get a date"],
    dq=case["case_id"], order_id=8002)

case = dq_case("dq-order-reversed-dates")
o = order(8001)
add("challenge", "support", 9503, "order_status", "damaged_record", "none", "one_lookup",
    "damaged_record", "operational_shorthand", "ESC-4",
    objective("flag_inconsistent_dates_and_escalate", f"{case['description']} (shipped {o['shipped_at']}, delivered "
              f"{o['delivered_at']}). {case['expected_handling']}", "data_quality_table", case["case_id"]),
    "confirm when an order shipped and arrived, for a customer",
    ["support staff", "a customer asked when order 8001 shipped and when it arrived"],
    dq=case["case_id"], order_id=8001)

case = dq_case("dq-order-store-mismatch")
o = order(8003)
assert can_view("merchant", 9001, o) and o["product_store_id"] != o["store_id"]
add("challenge", "merchant", 9001, "return_eligibility", "damaged_record", "cw-returns", "several_calls",
    "damaged_record", "requests_short_plain_answer", "ESC-4",
    objective("escalate_inconsistent_record", f"{case['description']} (order store {o['store_id']}, product store "
              f"{o['product_store_id']}). {case['expected_handling']}", "data_quality_table", case["case_id"]),
    "check what a customer ordered and whether it can be returned",
    ["runs Blue Heron Ceramics", "a customer on order 8003 is asking to return it"],
    dq=case["case_id"], order_id=8003)

case = dq_case("dq-product-duplicate-title")
dupes = [h for h in product_search("heavy-duty vase", store_id=1) if h["title"] == "Heavy-Duty Vase"]
assert {1, 2} <= {d["product_id"] for d in dupes}  # the seed also gave products 16 and 19 this title
add("challenge", "merchant", 9001, "product_search", "damaged_record", "none", "one_lookup",
    "damaged_record", "terse_fragmentary", "none",
    objective("disambiguate_duplicate_titles", f"{case['description']} Listings: "
              + "; ".join(f"#{d['product_id']} ${d['price_usd']:.2f}" for d in dupes) + f". {case['expected_handling']}",
              "data_quality_table", case["case_id"]),
    "check the listed price of the store's heavy-duty vase",
    ["runs Blue Heron Ceramics", "sells a Heavy-Duty Vase"],
    dq=case["case_id"], product_id=2)

case = dq_case("dq-product-invalid-price")
pitchers = product_search("rustic pitcher", store_id=1)
assert any(p["product_id"] == 4 and p["price_usd"] < 0 for p in pitchers)
add("challenge", "shopper", 150, "product_search", "damaged_record", "none", "one_lookup",
    "damaged_record", "typo_heavy", "none",
    objective("do_not_present_negative_price", f"{case['description']} Product 4 is listed at "
              f"${[p for p in pitchers if p['product_id'] == 4][0]['price_usd']:.2f}. {case['expected_handling']}",
              "data_quality_table", case["case_id"]),
    "find out how much the rustic pitcher from Blue Heron Ceramics costs",
    ["saw a rustic pitcher from Blue Heron Ceramics", "wants the price before buying"],
    dq=case["case_id"], product_id=4)

case = dq_case("dq-product-missing-title")
trays = [h for h in product_search("portable tray", store_id=1) if h["product_id"] == 3]
assert trays and trays[0]["title"] == ""
add("challenge", "support", 9504, "product_search", "damaged_record", "none", "one_lookup",
    "damaged_record", "neutral_conversational", "none",
    objective("do_not_invent_product_name", f"{case['description']} Product 3 (${trays[0]['price_usd']:.2f}) has an empty "
              f"title; it matches only on its description. {case['expected_handling']}",
              "data_quality_table", case["case_id"]),
    "get the listing name and price of a tray for a customer",
    ["support staff", "a customer saw a portable tray from Blue Heron Ceramics and wants its name and price"],
    dq=case["case_id"], product_id=3)

# --- Checks and output --------------------------------------------------------

assert len(rows) == 30
assert Counter(r["scenario_group"] for r in rows) == {"coverage": 18, "challenge": 12}
assert {r["data_quality_case_id"] for r in rows} - {None} == {
    r["case_id"] for r in conn.execute("SELECT case_id FROM data_quality_cases")
}
writes = [r["tuple"]["order_id"] for r in rows if r["tuple"]["intent"] in ("refund", "cancellation")]
assert len(writes) == len(set(writes)), "state-changing scenarios must use distinct orders"

OUT.write_text("".join(json.dumps(r) + "\n" for r in rows))

for field in ("role", "intent", "difficulty", "user_style", "turn_count", "escalation"):
    print(f"{field}: {dict(Counter(r['tuple'][field] for r in rows))}")
print(f"wrote {len(rows)} rows to {OUT}")
