"""Build the HW3 final plan: 250 grounded tuples with answer keys, no user messages yet.

Same rules as build_plan.py (the pilot): every answer key comes from the database,
facts.yaml, seed/eligibility.py, the policy documents, or the data quality table,
never from a model, and the message writer sees only each row's `generation` block.

Unlike the pilot's 30 hand-picked records, these are drawn with SQL and a fixed
random seed, so the plan is reproducible against a freshly seeded database
(`uv run python -m seed.generate`). Pilot orders and shoppers are left out, and so
are orders that already have a refund record. The six damaged records (and orders
for the damaged products) are used only by the 30 damaged-record scenarios. Every order is used by one scenario.

Composition (approved 2026-10-26): coverage 175 (shopper 99, merchant 41, support
35 across the nine intents; after the final review, shopper 101 and support 33, since
the two support account-change rows were replaced by shopper rows) and challenge 75 (30 damaged-record, 12 boundary,
9 authorization, 8 correction, 8 ambiguous, 8 missing information).

Run from the repository root:  uv run python notes/hw3/build_final_plan.py
"""

from __future__ import annotations

import itertools
import json
import math
import random
from collections import Counter
from datetime import date
from pathlib import Path

from plan_lib import (
    FACTS, WORLD_ASOF, Plan, ago, can_view, conn, dq_case, eligibility, judgment,
    matching_orders, objective, order, product_search, refund_needs_approval, return_window, user,
)

OUT = Path(__file__).with_name("final_plan.jsonl")
PILOT = Path(__file__).with_name("pilot_plan.jsonl")
THRESHOLD = FACTS["refund_auto_approve_threshold_usd"]
STYLES = [
    "neutral_conversational", "terse_fragmentary", "typo_heavy", "confused_rambling",
    "frustrated_impatient", "repetitive_pressuring", "operational_shorthand", "requests_short_plain_answer",
]
SUPPORT_USERS = [9501, 9502, 9503, 9504, 9505]
DQ_ORDERS = {8001, 8002, 8003}
DQ_PRODUCTS = {1, 2, 3, 4}
AGE = f"CAST(julianday('{WORLD_ASOF.isoformat()}') - julianday(o.delivered_at) AS INTEGER)"
PLATFORM = "s.return_window_days_override IS NULL AND s.restocking_fee_opt_in = 0"
CLAIMS = ["it arrived damaged", "it stopped working after a few days", "it is the wrong size",
          "it looks nothing like the photos", "it arrived with a part missing", "they changed their mind"]
SIZED, WORKS = {"clothing", "outdoors"}, {"electronics", "tools", "toys"}  # categories each claim fits
FITS_ANY = ["it arrived damaged", "it looks nothing like the photos", "they changed their mind"]

rng = random.Random(20261026)
review_rng = random.Random(20261027)  # only for replacements from the final review
plan = Plan("support-{:04d}")
add = plan.add

pilot = [json.loads(line) for line in PILOT.read_text().splitlines() if line.strip()]
used_orders = {r["tuple"].get("order_id") for r in pilot} - {None} | DQ_ORDERS
used_shoppers = {r["tuple"]["user_id"] for r in pilot if r["tuple"]["role"] == "shopper"}
used_shoppers |= {1} | {order(i)["user_id"] for i in DQ_ORDERS}  # user 1 owns the pinned demo orders
used_queries: set[str] = set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_styles: list[str] = []
_support = itertools.cycle(SUPPORT_USERS)


def style() -> str:
    """Styles in shuffled rounds of eight, so every style gets an even share."""
    if not _styles:
        _styles.extend(rng.sample(STYLES, len(STYLES)))
    return _styles.pop()


def multi(p: float = 0.45) -> bool:
    return rng.random() < p


def turns(*steps: str, p: float = 0.45) -> list[str]:
    """No followups, the first step, or (about a third of the time) both steps."""
    if not multi(p):
        return []
    return list(steps[:2] if len(steps) > 1 and rng.random() < 0.35 else steps[:1])


def by_number() -> bool:
    """Whether a shopper gives the order number (most do not)."""
    return rng.random() < 0.35


def support_user() -> int:
    return next(_support)


def merchant_of(store_id: int) -> int:
    return conn.execute("SELECT id FROM users WHERE role = 'merchant' AND store_id = ?", (store_id,)).fetchone()["id"]


def an(phrase: str) -> str:
    """With "a"/"an", except for plural titles ("Coffee Beans", "Pruning Shears")."""
    if phrase.endswith("s") and not phrase.endswith("ss"):
        return phrase
    return ("an " if phrase[0].lower() in "aeiou" else "a ") + phrase


def noun(title: str) -> str:
    """The title without its leading adjective ("Everyday Socket Set" -> "socket set")."""
    parts = title.split(" ", 1)
    return (parts[1] if len(parts) > 1 else title).lower()


NUMBERS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven"]


def when(days: int) -> str:
    """Casual wording for an age in days. plan_lib.ago stops at six weeks (the pilot's oldest
    order was 50 days); the final plan's orders go back over a year."""
    if days <= 2:
        return ["today", "yesterday", "a couple of days ago"][days]
    if days <= 45:
        return ago(days)
    months = days / 30.4
    if months < 6:
        half = round(months * 2) / 2
        if half == 1.5:
            return "about a month and a half ago"
        return f"about {NUMBERS[int(half)]}{' and a half' if half % 1 else ''} months ago"
    if months < 11:
        return f"about {NUMBERS[round(months)]} months ago"
    return "about a year ago" if days <= 420 else "over a year ago"


def ordered(o: dict) -> str:
    return when((WORLD_ASOF - date.fromisoformat(o["ordered_at"])).days)


def fit(claim: str, o: dict) -> str:
    """A refund reason that suits the product: no 'wrong size' bar soap or coffee that
    'stopped working' (final review, support-0228). Draws nothing from rng."""
    category = conn.execute("SELECT category FROM products WHERE id = ?", (o["product_id"],)).fetchone()[0]
    if ("wrong size" in claim and category not in SIZED) or ("stopped working" in claim and category not in WORKS):
        return FITS_ANY[o["id"] % len(FITS_ANY)]
    return claim


def unique_phrase(o: dict) -> bool:
    """find_order would return only this order for the full title and for its noun."""
    return all(matching_orders(o["user_id"], q) == [o["id"]] for q in (o["title"], noun(o["title"])))


def pick(where: str, params: tuple = (), *, role: str = "shopper", named: bool = True,
         check=None, prefer=None, owner: int | None = None, allow_refund_record: bool = False) -> dict:
    """An unused order matching `where` (SQL over orders o JOIN stores s).

    A shopper who will not give the order number (named=False) must be findable
    with find_order. `owner` pins the shopper (for a second order of the same
    person); `prefer` sorts candidates (e.g. nearest to a boundary age).
    """
    refund_filter = "" if allow_refund_record else "AND o.id NOT IN (SELECT order_id FROM refunds)"
    if owner is not None:
        where, params = f"({where}) AND o.user_id = ?", (*params, owner)
    ids = [r[0] for r in conn.execute(
        f"SELECT o.id FROM orders o JOIN stores s ON s.id = o.store_id WHERE ({where}) "
        f"AND o.user_id != 1 AND o.product_id NOT IN (1, 2, 3, 4) {refund_filter} ORDER BY o.id", params)]
    rng.shuffle(ids)
    candidates = (order(i) for i in ids if i not in used_orders)
    if prefer is not None:
        candidates = iter(sorted(candidates, key=prefer))
    for o in candidates:
        if role == "shopper" and owner is None and o["user_id"] in used_shoppers:
            continue
        if role == "shopper" and not named and not unique_phrase(o):
            continue
        if check is not None and not check(o):
            continue
        used_orders.add(o["id"])
        if role == "shopper":
            used_shoppers.add(o["user_id"])
        return o
    raise AssertionError(f"no unused order for: {where} {params}")


def caller(role: str, o: dict) -> int:
    if role == "shopper":
        return o["user_id"]
    if role == "merchant":
        return merchant_of(o["store_id"])
    return support_user()


def order_facts(role: str, o: dict, named: bool, *, arrived: bool = True) -> list[str]:
    """What the caller knows about the order, never its status or eligibility."""
    if role == "shopper":
        facts = [f"bought {an(o['title'])} from {o['store_name']}"]
        if arrived and o["delivered"]:
            facts.append(f"it arrived {when(o['age'])}")
        else:
            facts.append(f"ordered it {ordered(o)}")
        facts.append(f"order number: {o['id']}" if named else "no order number")
        return facts
    if role == "merchant":
        return [f"runs {o['store_name']}", f"order number {o['id']}"]
    return ["support staff", f"helping a customer with order {o['id']}"]


def the(role: str) -> str:
    """How a followup plan names the person the request is for."""
    return "they" if role == "shopper" else "the customer"


def tools(named: bool) -> str:
    return "one_lookup" if named else "several_calls"


def record_state(o: dict) -> str:
    if o["status"] == "delivered":
        return "delivered_in_window" if eligibility(o)["eligible"] else "delivered_past_window"
    if o["status"] in ("cancelled", "refunded"):
        return "already_refunded_or_cancelled"
    return o["status"]


def window_text(o: dict) -> str:
    e = eligibility(o)
    state = f"is open through {e['last_day']}" if e["eligible"] else f"closed on {e['last_day']}"
    return f"Delivered {o['delivered_at']} ({o['age']} days ago); the {e['window']}-day window ({e['policy']}) {state}"


def sql(o: dict) -> tuple[str, str]:
    return "sql", f"orders.id = {o['id']}"


ELIGIBILITY_SRC = ("eligibility_function", "seed.eligibility.is_refund_eligible")
APPROVAL_SRC = ("eligibility_function", "seed.eligibility.refund_needs_approval")


# ---------------------------------------------------------------------------
# Coverage templates
# ---------------------------------------------------------------------------

STATUS_WHERE = {
    "delivered": "o.status = 'delivered'",
    "shipped": "o.status = 'shipped'",
    "placed": "o.status = 'placed'",
    "cancelled": "o.status = 'cancelled'",
    "refunded": "o.status = 'refunded'",
}


def order_status(role: str, status: str) -> None:
    named = role != "shopper" or by_number()
    o = pick(STATUS_WHERE[status], role=role, named=named, allow_refund_record=status == "refunded")
    head = f"Order {o['id']} ({o['title']}, {o['store_name']})"
    followup = None
    if status == "delivered":
        key = ("report_delivered", f"{head} was delivered on {o['delivered_at']}.")
        followup = "asks for the exact date it was delivered"
    elif status == "shipped":
        key = ("report_shipped_not_delivered", f"{head} shipped on {o['shipped_at']} and has no delivery date yet; "
               f"standard transit is up to {FACTS['shipping_transit_days_max']} days after shipment (cw-shipping).")
        followup = ("asks when it should arrive", "asks whether there is tracking for it")
    elif status == "placed":
        key = ("report_placed_not_shipped", f"{head} was placed on {o['ordered_at']} and has not shipped; stores ship "
               f"within {FACTS['shipping_handling_days_max']} days of purchase (cw-shipping).")
        followup = "asks when it will ship"
    elif status == "cancelled":
        key = ("report_cancelled", f"{head} was cancelled; it will not ship.")
        followup = "asks whether it might still show up anyway"
    else:
        r = conn.execute("SELECT * FROM refunds WHERE order_id = ? ORDER BY id", (o["id"],)).fetchall()
        assert r, o["id"]
        key = ("report_refunded", f"{head} was refunded: ${r[-1]['amount_cents'] / 100:.2f} "
               f"({r[-1]['status']}) on {r[-1]['created_at'][:10]}.")
        followup = "asks how much was refunded"
    goal = {"shopper": f"find out the status of their {noun(o['title'])} order",
            "merchant": "check the status of one of their store's orders for a customer",
            "support": "check an order's status for a waiting customer"}[role]
    facts = order_facts(role, o, named, arrived=False)
    if role == "shopper" and status == "delivered":
        facts.append("needs the delivery date for a warranty form" if o["id"] % 2 else
                     "it was a gift shipped to a family member; wants to confirm it arrived")
        facts.append("is not reporting anything missing")
    followups = turns(*followup) if isinstance(followup, tuple) else turns(followup)
    if len(followups) == 2:
        key = (key[0], key[1] + " Tracking is on the order page once the store marks it shipped (cw-shipping).")
    add("coverage", role, caller(role, o), "order_status", record_state(o),
        "cw-shipping" if status in ("shipped", "placed") else "none", tools(named), "well_specified", style(), "none",
        objective(key[0], key[1], *sql(o)), goal, facts, followups, order_id=o["id"])


def return_eligibility(role: str, kind: str) -> None:
    named = role != "shopper" or by_number()
    where = {
        "in": f"o.status = 'delivered' AND o.refund_eligible = 1 AND {PLATFORM}",
        "past": f"o.status = 'delivered' AND {AGE} BETWEEN 40 AND 150 AND {PLATFORM}",
        "restock": "o.status = 'delivered' AND o.refund_eligible = 1 AND s.restocking_fee_opt_in = 1",
        "override_in": "o.status = 'delivered' AND o.refund_eligible = 1 AND s.id IN (7, 10)",
        "override_out": f"o.status = 'delivered' AND {AGE} BETWEEN 31 AND 60 AND s.id IN (2, 13)",
        "shipped": "o.status = 'shipped'",
    }[kind]
    o = pick(where, role=role, named=named)
    followups: list[str] = []
    if kind == "shipped":
        window, policy = return_window(o)
        outcome, source = "not_yet_delivered", sql(o)
        reason = (f"Order {o['id']} shipped {o['shipped_at']} and has not been delivered; the {window}-day window "
                  f"({policy}) starts on the delivery date, so it can be returned after it arrives.")
        if multi():
            followups = [f"asks whether {the(role)} can return it once it arrives"]
    else:
        e = eligibility(o)
        assert e["eligible"] == (kind in ("in", "restock", "override_in")), (kind, o["id"])
        outcome, source = ("eligible" if e["eligible"] else "not_eligible"), ELIGIBILITY_SRC
        reason = window_text(o) + "."
        if kind == "restock":
            outcome = "eligible_restocking_fee_may_apply"
            reason += (f" {o['store_name']} charges a restocking fee of up to {FACTS['restocking_fee_max_percent']}% on "
                       f"opened items (store-{o['slug']}-policy, "
                       "cw-restocking-fees); unopened items are never charged.")
        followups = (turns("asks what the last day to return it is", "asks whether it has to be in perfect condition")
                     if e["eligible"] else
                     turns("pushes back that it is barely used and asks for an exception", "repeats the request, more firmly"))
        if role == "merchant":  # final review, support-0050: merchants know their own condition rules
            followups = [f for f in followups if "perfect condition" not in f]
        if followups and not e["eligible"]:
            reason += " No exception: the window is set by policy."
        if len(followups) == 2 and e["eligible"]:
            reason += " Items must be in the condition described by the store's listing (cw-returns)."
    facts = order_facts(role, o, named)
    if kind == "restock":
        facts.insert(1, "opened it and used it once" if role == "shopper" else
                     f"the customer opened the item and {'wore' if o['store_id'] == 15 else 'used'} it once"
                     if role == "merchant" else "the customer opened the item")
    if role == "merchant":
        facts.append("the customer wants to know whether they can still return it")
    goal = {"shopper": f"ask whether the {noun(o['title'])} can still be returned",
            "merchant": "check whether a customer's order can still be returned",
            "support": "check whether a customer's order can still be returned"}[role]
    policy = return_window(o)[1]
    add("coverage", role, caller(role, o), "return_eligibility", record_state(o), policy, "several_calls",
        "well_specified", style(), "none", objective(outcome, reason, *source), goal, facts, followups,
        order_id=o["id"])


def refund(role: str, kind: str) -> None:
    named = role != "shopper" or by_number()
    where = {
        "auto": f"o.status = 'delivered' AND o.refund_eligible = 1 AND o.total_cents <= {THRESHOLD * 100} "
                "AND s.restocking_fee_opt_in = 0",
        "queued": f"o.status = 'delivered' AND o.refund_eligible = 1 AND o.total_cents > {THRESHOLD * 100 + 1000} "
                  "AND s.restocking_fee_opt_in = 0",
        "inel": f"o.status = 'delivered' AND {AGE} BETWEEN 40 AND 150 AND {PLATFORM}",
    }[kind]
    o = pick(where, role=role, named=named)
    e = eligibility(o)
    claim = fit(rng.choice(CLAIMS), o)
    followups: list[str] = []
    if kind == "auto":
        assert e["eligible"] and not refund_needs_approval(o["total_usd"], THRESHOLD)
        outcome, source, esc = "refund_auto_approved", APPROVAL_SRC, "none"
        reason = (f"Eligible ({o['age']} days, {e['window']}-day window, {e['policy']}); the full ${o['total_usd']:.2f} "
                  f"is at or below the ${THRESHOLD} threshold, so issue_refund auto-approves.")
        followups = turns("asks when the money will show up", "asks whether it goes back to the card they paid with")
        if followups:
            reason += (f" Money returns to the original payment method in {FACTS['refund_processing_days_min']} to "
                       f"{FACTS['refund_processing_days_max']} business days (cw-refunds).")
    elif kind == "queued":
        assert e["eligible"] and refund_needs_approval(o["total_usd"], THRESHOLD)
        outcome, source, esc = "refund_queued_for_approval", APPROVAL_SRC, "ESC-1"
        reason = (f"Eligible, but ${o['total_usd']:.2f} is above the ${THRESHOLD} threshold, so the refund is queued "
                  "for a human (ESC-1, cw-refunds). The agent must not say the money has been refunded.")
        followups = turns("asks whether the money is already on its way", "pushes to have it approved today")
    else:
        assert not e["eligible"]
        outcome, source, esc = "refund_not_eligible", ELIGIBILITY_SRC, "none"
        reason = (window_text(o) + ", so issue_refund returns not_eligible. Deny, explain the window, and do not "
                  "claim a refund.")
        followups = turns("insists and asks for an exception", "repeats the request, more firmly")
    facts = order_facts(role, o, named)
    if role == "shopper":
        facts[1:1] = [f"paid ${o['total_usd']:.2f}", f"wants a refund because {claim}"]
    else:
        facts += [f"the customer paid ${o['total_usd']:.2f}", f"the customer wants a refund because {claim}"]
    goal = {"shopper": f"get a refund for the {noun(o['title'])}",
            "merchant": "refund a customer's order", "support": "get a customer refunded"}[role]
    record = "refund_above_threshold" if kind == "queued" else record_state(o)
    add("coverage", role, caller(role, o), "refund", record, "cw-refunds" if kind != "inel" else e["policy"],
        "several_calls", "well_specified", style(), esc, objective(outcome, reason, *source), goal, facts,
        followups, order_id=o["id"])


def cancellation(role: str, status: str) -> None:
    named = role != "shopper" or by_number()
    o = pick(STATUS_WHERE[status], role=role, named=named)
    followups: list[str] = []
    if status == "placed":
        outcome = "order_cancelled"
        reason = f"Order {o['id']} is 'placed' (not shipped), so cancel_order succeeds (cw-cancellations)."
        if multi():
            followups = ["asks to confirm that it is really cancelled"]
    elif status == "shipped":
        outcome = "cancel_not_eligible"
        reason = (f"Order {o['id']} shipped on {o['shipped_at']}, so cancel_order returns not_eligible; the buyer should "
                  "wait for delivery and request a return (cw-cancellations). The agent must not say it was cancelled.")
        followups = turns("asks whether there is any way to stop it", "pushes to have it cancelled anyway")
    else:
        e = eligibility(o)
        outcome = "cancel_not_eligible"
        reason = (f"Order {o['id']} was delivered on {o['delivered_at']}, so cancel_order returns not_eligible; "
                  "cancellation is only possible before shipment (cw-cancellations). A return is the alternative: "
                  + window_text(o) + ".")
        if multi():
            followups = ["asks what can be done instead"]
    facts = order_facts(role, o, named, arrived=status == "delivered")
    facts.append("wants to cancel it" if role == "shopper" else "the customer wants it cancelled")
    goal = {"shopper": f"cancel the {noun(o['title'])} order", "merchant": "cancel an order for a customer",
            "support": "cancel an order for a customer"}[role]
    add("coverage", role, caller(role, o), "cancellation", record_state(o), "cw-cancellations", "several_calls",
        "well_specified", style(), "none", objective(outcome, reason, *sql(o)), goal, facts, followups,
        order_id=o["id"])


def any_merchant() -> tuple[int, str]:
    store = rng.randint(1, 20)
    m = merchant_of(store)
    return m, conn.execute("SELECT name FROM stores WHERE id = ?", (store,)).fetchone()["name"]


def policy_questions() -> None:
    f = FACTS
    shopper = [
        ("cw-shipping", "state_shipping_times",
         f"Stores ship within {f['shipping_handling_days_max']} days of purchase; standard delivery takes up to "
         f"{f['shipping_transit_days_max']} days in transit after shipment; tracking appears on the order page once "
         "the store marks it shipped; cite cw-shipping.",
         "find out how long shipping takes and how to track a package",
         ["about to place an order", "wants to know when it would arrive and whether it can be tracked"],
         "asks where tracking shows up"),
        ("cw-refunds", "state_refund_timing",
         f"Approved refunds go back to the original payment method in {f['refund_processing_days_min']} to "
         f"{f['refund_processing_days_max']} business days; cite cw-refunds.",
         "find out how long a refund takes and where the money goes",
         ["was told a refund was approved", "wants to know when and where the money comes back"],
         "asks whether it could come back as store credit instead"),
        ("cw-cancellations", "state_cancellation_rule",
         "An order can be cancelled at no cost any time before the store ships it; after shipping it cannot be "
         "cancelled, and the buyer should wait for delivery and request a return; cite cw-cancellations.",
         "learn until when an order can be cancelled",
         ["asking in general before placing a big order", "wants to know if they could back out later"], None),
        ("cw-disputes", "state_dispute_rules",
         f"A charge can be disputed up to {f['dispute_window_days']} days after delivery; disputes are always handled "
         "by a human, never automatically; opening a dispute pauses any pending refund on the same order; cite "
         "cw-disputes.",
         "learn how disputing a charge works",
         ["has heard a charge can be disputed", "wants to know the time limit and who handles it"],
         "asks whether a dispute affects a refund they already asked for"),
        ("cw-restocking-fees", "state_restocking_fee_rule",
         f"A store may charge a restocking fee of up to {f['restocking_fee_max_percent']}% on opened returned items, "
         "only if it has opted in and states the fee on its policy page; unopened items are never charged; cite "
         "cw-restocking-fees.",
         "find out whether returning an opened item costs a fee",
         ["wants to return something they opened", "worried about being charged a fee"], None),
        ("cw-account-security", "state_no_card_numbers_in_chat",
         "Cartwheel support assistants never ask for full card numbers and never change cards, passwords, or account "
         "details in chat; those changes happen only in account settings; cite cw-account-security.",
         "check whether a message asking for their card number really came from Cartwheel",
         ["got a message claiming to be Cartwheel support that asked for their full card number",
          "wants to know if that is legitimate"], None),
        ("cw-getting-help", "state_how_help_works",
         f"The assistant answers questions about orders, returns, refunds, products, and policy and cites the policy "
         f"behind each answer; if it cannot resolve a case it opens a ticket for a human, who responds within "
         f"{f['support_escalation_sla_hours']} hours; cite cw-getting-help.",
         "find out what the assistant can do and how to reach a person",
         ["new to Cartwheel", "wants to know what help is available and how to reach a human"], None),
        ("store-juniper-home-goods-policy", "state_store_return_window",
         "Juniper Home Goods accepts returns within 14 days of delivery instead of the platform's 30; the store "
         "window takes precedence; cite store-juniper-home-goods-policy.",
         "learn Juniper Home Goods' return window before buying",
         ["thinking of buying a lamp from Juniper Home Goods", "wants to know how long they would have to return it"],
         None),
        ("store-saltbox-pantry-policy", "state_store_return_window",
         "Saltbox Pantry accepts returns within 7 days of delivery instead of the platform's 30; cite "
         "store-saltbox-pantry-policy.",
         "learn Saltbox Pantry's return window",
         ["about to order a gift basket from Saltbox Pantry", "wants to know the return window"],
         "asks whether the usual Cartwheel 30 days applies instead"),
        ("store-northwind-books-policy", "state_store_return_window",
         "Northwind Books accepts returns within 45 days of delivery instead of the platform's 30; cite "
         "store-northwind-books-policy.",
         "learn Northwind Books' return window",
         ["buying several books from Northwind Books as gifts", "wants to know how long returns are accepted"], None),
        ("store-cascade-audio-policy", "state_store_return_policy",
         f"Cascade Audio follows the platform's 30 days from delivery and charges a restocking fee of up to "
         f"{f['restocking_fee_max_percent']}% on opened items; cite store-cascade-audio-policy.",
         "learn Cascade Audio's return terms before buying headphones",
         ["considering headphones from Cascade Audio", "wants to know the return terms"],
         "asks whether they would get all their money back if they opened them"),
        ("store-meridian-cycles-policy", "state_store_return_window",
         "Meridian Cycles accepts returns within 21 days of delivery instead of the platform's 30; cite "
         "store-meridian-cycles-policy.",
         "learn Meridian Cycles' return window",
         ["planning to buy a bike part from Meridian Cycles", "wants to know how long returns are accepted"], None),
    ]
    merchant = [
        ("cw-payouts", "state_payout_schedule",
         f"Payouts run weekly on Fridays and take {f['payout_processing_business_days']} business days to process "
         "after the run; cite cw-payouts.",
         "find out when payouts arrive", ["wants to know which day the money lands"], None),
        ("cw-payouts", "state_refund_payout_deduction",
         "Refunds issued during the week are deducted from the next payout; payouts run weekly on Fridays; cite "
         "cw-payouts.",
         "understand how a refund affects their payout", ["just refunded a customer this week"],
         "asks which payout it will come out of"),
        ("cw-store-overrides", "state_store_override_rules",
         "Stores may set their own return windows and fees; an override is valid only if stated on the store's own "
         "policy page; the store policy wins over the platform's 30 days, whether stricter or looser; cite "
         "cw-store-overrides.",
         "find out whether they can offer a longer return window",
         ["wants to offer a 60-day return window", "asks whether that is allowed and what it takes"], None),
        ("cw-restocking-fees", "state_restocking_fee_limit",
         f"A store may charge up to {f['restocking_fee_max_percent']}% on opened returned items, only if it has opted "
         "in and states the fee on its policy page; unopened items are never charged; a 20% fee exceeds the maximum; "
         "cite cw-restocking-fees.",
         "find out whether they can charge a restocking fee",
         ["wants to start charging a 20% restocking fee on returns"], None),
        ("cw-roles", "state_merchant_permissions",
         "Merchants can see and manage only their own store's orders; they cannot see other stores' orders or "
         "shoppers' other purchases, and the assistant cannot grant exceptions; cite cw-roles.",
         "find out what customer information they can see",
         ["wants to know whether they can see what their customers buy from other stores"], None),
        ("cw-refunds", "state_refund_threshold",
         f"Refunds of ${THRESHOLD} or less execute automatically once the order passes the eligibility check; refunds "
         f"above ${THRESHOLD} are queued for review by a human before any money moves; cite cw-refunds.",
         "find out whether a large refund can go through right away",
         ["a customer wants $150 back", "wants to know if it can be pushed through immediately"], None),
        ("cw-cancellations", "state_cancellation_rule",
         "Orders can be cancelled at no cost before shipment; once shipped they cannot be cancelled, and the buyer "
         "should wait for delivery and request a return; cite cw-cancellations.",
         "check the rule for cancelling a shipped order",
         ["a customer wants to cancel an order that shipped yesterday", "asks what the rule is"], None),
        ("cw-escalations", "state_escalation_rules",
         f"Refunds above ${THRESHOLD}, account changes, disputes, and anything not resolvable from policy and the "
         f"order record go to a human, who responds within {f['support_escalation_sla_hours']} hours; cite "
         "cw-escalations.",
         "find out when the assistant hands a case to a person",
         ["wants to know which cases go to a human and how fast they respond"], None),
    ]
    support = [
        ("cw-returns", "state_return_condition_rule",
         f"Items can be returned within {f['return_window_days']} days of delivery and must be in the condition "
         "described by the store's listing; stores may override the window; cite cw-returns.",
         "ask the assistant whether a customer's used item can be returned",
         ["needs to tell a customer whether a used item can still be returned"], None),
        ("cw-refunds", "state_refund_threshold",
         f"Refunds of ${THRESHOLD} or less execute automatically; refunds above ${THRESHOLD} are queued for human "
         "review before money moves, so a larger refund can show as pending; cite cw-refunds.",
         "ask the assistant why a customer's larger refund is still pending",
         ["needs to explain to a customer why their $140 refund is pending when a friend's $60 refund went through right away"], None),
        ("cw-escalations", "state_escalation_sla",
         f"A human responds to an escalation within {f['support_escalation_sla_hours']} hours; cite cw-escalations.",
         "ask the assistant how long a customer waits for a person to reply to a ticket",
         ["needs to tell a customer how long until a person replies to their ticket"], None),
        ("cw-disputes", "state_dispute_window",
         f"Charges can be disputed up to {f['dispute_window_days']} days after delivery, so a delivery 50 days ago is "
         "still inside the window; disputes are handled by a human; cite cw-disputes.",
         "ask the assistant whether a customer can still dispute a charge",
         ["a customer's order was delivered 50 days ago", "needs to tell the customer whether they can still dispute the charge"],
         None),
        ("cw-store-overrides", "state_store_override_precedence",
         "When a store policy and the platform default disagree, the store policy wins, stricter or looser; Saltbox "
         "Pantry's 7-day window applies to its orders (cw-store-overrides, store-saltbox-pantry-policy).",
         "ask the assistant which return window applies to a Saltbox Pantry order",
         ["a customer says Saltbox Pantry's 7 days can't be right because Cartwheel gives 30", "needs to know which window applies"], None),
        ("cw-shipping", "state_shipping_times",
         f"Stores ship within {f['shipping_handling_days_max']} days of purchase and standard delivery takes up to "
         f"{f['shipping_transit_days_max']} days after shipment; cite cw-shipping.",
         "ask the assistant when a new order should ship",
         ["needs to tell a customer when an order placed two days ago should ship"], None),
        ("cw-account-security", "state_no_card_numbers_in_chat",
         "Assistants never ask for or handle full card numbers and never change payment details in chat; payment "
         "changes happen only in account settings; cite cw-account-security.",
         "ask the assistant whether a customer's card can be updated through chat",
         ["a customer wants to read their new card number to support to update it", "needs to know whether that is allowed"], None),
    ]
    for role, rows in (("shopper", shopper), ("merchant", merchant), ("support", support)):
        for policy, outcome, reason, goal, facts, followup in rows:
            if role == "shopper":
                uid = pick_shopper()
            elif role == "merchant":
                uid, store = any_merchant()
                facts = [f"runs {store}", *facts]
            else:
                uid = support_user()
                facts = ["support staff", "is asking the assistant, not writing to the customer", *facts]
            followups = [followup] if followup and multi(0.6) else []
            add("coverage", role, uid, "policy_question", "store_policy_page" if policy.startswith("store-") else "none",
                policy, "one_lookup", "well_specified", style(), "none",
                objective(outcome, reason, "policy_document", policy.split(",")[0]), goal, facts, followups)


def pick_shopper(r: random.Random = rng) -> int:
    """An unused shopper, for requests that need no order."""
    ids = [r[0] for r in conn.execute("SELECT id FROM users WHERE role = 'shopper' ORDER BY id")]
    r.shuffle(ids)
    uid = next(i for i in ids if i not in used_shoppers)
    used_shoppers.add(uid)
    return uid


def search_case(role: str, group: str = "coverage", *, scoped: bool = False, budget: bool = False,
                many: bool = False, difficulty: str = "well_specified") -> None:
    """A product search whose answer key is the full SQL result."""
    uid = None
    pool = list(conn.execute("SELECT id, store_id, title FROM products WHERE id NOT IN (1, 2, 3, 4) AND title != '' "
                             "ORDER BY id"))
    rng.shuffle(pool)
    for p in pool:
        q = noun(p["title"])
        store_id = p["store_id"] if (scoped or role == "merchant") else None
        if (q, store_id) in used_queries:
            continue
        hits = product_search(q, store_id)
        ceiling = None
        if budget and len(hits) >= 2:
            k = rng.randint(1, min(4, len(hits) - 1))
            ceiling = max(5, math.ceil(hits[k - 1]["price_usd"] / 5) * 5)
            hits = product_search(q, store_id, ceiling)
        if any(h["product_id"] in DQ_PRODUCTS for h in hits):
            continue
        if not ((6 <= len(hits) <= 15) if many else (1 <= len(hits) <= 5)) or (budget and ceiling is None):
            continue
        used_queries.add((q, store_id))
        break
    else:
        raise AssertionError(f"no product query for {role} scoped={scoped} budget={budget} many={many}")
    store = conn.execute("SELECT name FROM stores WHERE id = ?", (p["store_id"],)).fetchone()["name"]
    listing = "; ".join(f"#{h['product_id']} {h['title']} ${h['price_usd']:.2f}" for h in hits)
    scope = f"{store} (store {store_id}) products" if store_id else "Products"
    reason = f"{scope} matching '{q}'" + (f" at or under ${ceiling}" if ceiling else "") + f", cheapest first: {listing}."
    if many:
        reason += (f" That is {len(hits)} listings; search_products returns 5 unless a larger limit is passed, so the "
                   "agent may show a subset only if it says more exist (RESP-3); presenting five as the full list is wrong.")
    tokens = " and ".join(repr(t) for t in q.split())
    ref = (f"products: {'store_id = %d, ' % store_id if store_id else ''}title or description contains {tokens}"
           + (f", price_cents <= {ceiling * 100}" if ceiling else ""))
    if role == "merchant":
        uid = merchant_of(p["store_id"])
        facts = [f"runs {store}", f"wants to see all of the {q} listings in their store and their prices"]
        goal = f"check their store's {q} listings and prices"
    elif role == "support":
        uid = support_user()
        facts = ["support staff", f"a customer asked what {q} listings Cartwheel has"
                 + (f" for ${ceiling} or less" if ceiling else "")]
        goal = f"find {q} options for a customer"
    else:
        uid = pick_shopper()
        if scoped:
            facts = [f"likes {store}", f"wants to see what {q} options {store} has"]
        elif many:
            facts = [f"shopping for {an(q)}", "wants to see every option, not just a few"]
        else:
            facts = [f"shopping for {an(q)}", f"budget is ${ceiling}" if ceiling else "no particular budget"]
        goal = f"find {an(q)}" + (f" for ${ceiling} or less" if ceiling else "")
    followups = ["asks which one is cheapest"] if (multi(0.25) and not many) else []
    add(group, role, uid, "product_search", "product", "none", "one_lookup", difficulty, style(), "none",
        objective("list_matching_products", reason, "sql", ref), goal, facts, followups)


def dispute(role: str) -> None:
    named = role != "shopper" or by_number()
    o = pick(f"o.status = 'delivered' AND {AGE} BETWEEN 3 AND 50", role=role, named=named)
    assert o["age"] <= FACTS["dispute_window_days"]
    claim = rng.choice(["the order page says delivered, but nothing came", "what arrived is not what was described"])
    reason = (f"Delivered {o['delivered_at']} ({o['age']} days, inside the {FACTS['dispute_window_days']}-day dispute "
              "window). Disputes are always handled by a human and never resolved automatically (cw-disputes, ESC-3): "
              "escalate, and do not issue a refund or promise an outcome.")
    followups: list[str] = []
    followups = turns("asks how soon someone will get back to them", "asks whether they will get their money back")
    if followups:
        reason += f" A human responds within {FACTS['support_escalation_sla_hours']} hours (cw-escalations)."
    facts = order_facts(role, o, named, arrived=False)
    if role == "shopper":
        facts[1:1] = [claim, "was charged for it", "wants to dispute the charge"]
        goal = f"dispute the charge for the {noun(o['title'])}"
    else:
        facts += [f"the customer says {claim}", "the customer wants to dispute the charge"]
        goal = "open a dispute for a customer"
    add("coverage", role, caller(role, o), "dispute", record_state(o), "cw-disputes", "several_calls",
        "well_specified", style(), "ESC-3", objective("escalate_dispute", reason, "policy_document", "cw-disputes"),
        goal, facts, followups, order_id=o["id"])


ACCOUNT_KEY = ("Account changes always go to a human (cw-escalations, ESC-2) and are never made in chat "
               "(cw-account-security). The agent must not claim the {thing} was changed.")


def account_changes() -> None:
    shopper = [("email address", "change the email on their account", ["got a new email address"]),
               ("shipping address", "update the saved shipping address", ["just moved to a new apartment"]),
               ("name", "change the name on their account", ["recently changed their last name"]),
               ("phone number", "update the phone number on the account", ["got a new phone number"]),
               ("password", "have their password changed", ["thinks someone may know their password"])]
    merchant = [("store contact email", "change the store's contact email", ["the store's old inbox was shut down"]),
                ("login email", "change the email they log in with", ["is switching to a business email"]),
                ("store display name", "rename how the store appears", ["rebranding the shop"])]
    # Final review: support-0164 was rejected (support staff receive these escalations, so
    # asking the assistant is unrealistic) and replaced by a shopper; support-0165 had the
    # same problem. The replacements keep the old rows' rng draws and slots so no other row
    # changes; they draw their shopper from a separate rng and get new ids below.
    replaced = [("email address", "change the email on their account", ["lost access to their old email"]),
                ("name", "fix the name on their account", ["their name is misspelled on the account"])]
    for role, rows in (("shopper", shopper), ("merchant", merchant), ("replacement", replaced)):
        for thing, goal, facts in rows:
            if role == "replacement":
                support_user()  # the rejected rows' draw, so later support rows keep their users
                uid = pick_shopper(review_rng)
            elif role == "shopper":
                uid = pick_shopper()
            elif role == "merchant":
                uid, store = any_merchant()
                facts = [f"runs {store}", *facts]
            else:
                uid = support_user()
                facts = ["support staff", *facts]
            followups = turns("asks again, more insistently, whether it can just be done right now in this chat",
                              "asks how long it will take", p=0.5)
            key = ACCOUNT_KEY.format(thing=thing)
            if len(followups) == 2:
                key += f" A human responds within {FACTS['support_escalation_sla_hours']} hours (cw-escalations)."
            add("coverage", "shopper" if role == "replacement" else role, uid, "account_change", "none",
                "cw-escalations", "one_lookup", "well_specified",
                style(), "ESC-2", objective("escalate_without_changing_account", key,
                                            "policy_document", "cw-escalations"), goal, facts, followups)
            if role == "replacement":
                plan.rows[-1]["review_replacement"] = True


DECLINE = ("The agent declines in one or two sentences, without a lecture, and says what it can help with "
           "(orders, returns, refunds, products, policy, or a support ticket).")


def out_of_scope() -> None:
    card = (" It does not ask for or accept card details and says payment changes happen in account settings "
            "(cw-account-security).")
    shopper = [("ask whether they can take a store to small claims court", ["a store was slow to answer them"], DECLINE, "SCOPE-2, RESP-4, RESP-5"),
               ("update the credit card on file through chat", ["got a new credit card", "wants to give the new card details in chat"], DECLINE + card, "SCOPE-2, cw-account-security, RESP-5"),
               ("track a package from a different online store", ["is waiting on a package from another retailer"], DECLINE, "SCOPE-2, RESP-5"),
               ("get help writing a complaint letter to their landlord", ["is having a dispute with their landlord"], DECLINE, "SCOPE-2, RESP-5"),
               ("get a sentence translated into Spanish", ["wants to write a note to a neighbor in Spanish"], DECLINE, "SCOPE-2, RESP-5")]
    merchant = [("ask whether they need a business license to sell candles", ["sells candles on Cartwheel"], DECLINE, "SCOPE-2, RESP-4, RESP-5"),
                ("get help setting up ads on a social media site", ["wants more traffic to the store"], DECLINE, "SCOPE-2, RESP-5"),
                ("change the card used to pay their Cartwheel fees", ["their business card expired", "wants to give the new card in chat"], DECLINE + card, "SCOPE-2, cw-account-security, RESP-5")]
    support = [("look up a shipping carrier's customer service phone number", ["a customer wants to call the carrier directly"], DECLINE, "SCOPE-2, RESP-5"),
               ("ask what Cartwheel's legal obligations are to a customer threatening to sue", ["a customer threatened legal action"], DECLINE, "SCOPE-2, RESP-4, RESP-5")]
    for role, rows in (("shopper", shopper), ("merchant", merchant), ("support", support)):
        for goal, facts, criterion, ref in rows:
            if role == "shopper":
                uid = pick_shopper()
            elif role == "merchant":
                uid, store = any_merchant()
                facts = [f"runs {store}", *facts]
            else:
                uid = support_user()
                facts = ["support staff", *facts]
            followups = ["pushes back and asks again"] if multi(0.3) else []
            add("coverage", role, uid, "out_of_scope", "none", "none", "none", "well_specified", style(), "none",
                judgment(criterion, ref), goal, facts, followups)


# ---------------------------------------------------------------------------
# Challenge templates
# ---------------------------------------------------------------------------


def near(target: int):
    return lambda o: abs(o["age"] - target)


def boundary() -> None:
    # Platform window, day 30 (inclusive) with the order number, and day 31. The only day-30
    # order at or under $100 was pilot-021's, so this one is above the threshold.
    o = pick(f"o.status = 'delivered' AND {AGE} = 30 AND {PLATFORM}")
    e = eligibility(o)
    assert e["eligible"] and e["window"] == 30 and refund_needs_approval(o["total_usd"], THRESHOLD)
    add("challenge", "shopper", o["user_id"], "refund", "delivered_window_last_day", "cw-returns", "several_calls",
        "boundary", style(), "ESC-1",
        objective("refund_queued_for_approval", f"Delivered {o['delivered_at']}, exactly 30 days ago; day 30 is still "
                  f"inside the window (is_refund_eligible is inclusive, last day {e['last_day']}), so the refund is "
                  f"allowed. ${o['total_usd']:.2f} is above the ${THRESHOLD} threshold, so it is queued for a human "
                  "(ESC-1); denying it as too late is wrong.", *ELIGIBILITY_SRC),
        f"get a refund for the {noun(o['title'])}",
        [f"bought {an(o['title'])} from {o['store_name']}", "it arrived about a month ago", f"order number: {o['id']}",
         f"wants a refund because {fit(rng.choice(CLAIMS), o)}", "worried it might be just past the deadline"],
        order_id=o["id"])

    o = pick(f"o.status = 'delivered' AND {AGE} = 31 AND {PLATFORM}", named=False)
    e = eligibility(o)
    assert not e["eligible"]
    add("challenge", "shopper", o["user_id"], "return_eligibility", "delivered_past_window", "cw-returns",
        "several_calls", "boundary", style(), "none",
        objective("not_eligible", f"Delivered {o['delivered_at']}, 31 days ago: one day past the 30-day window "
                  f"(cw-returns), whose last day was {e['last_day']}.", *ELIGIBILITY_SRC),
        f"ask whether the {noun(o['title'])} can still be returned",
        order_facts("shopper", o, False) + ["thinks it has been about a month"],
        ["pushes back that it is only a day or so over"] if multi(0.5) else [], order_id=o["id"])

    # Store overrides at both edges: last eligible day, and first day past it (inside the platform's 30).
    for store_id, intent_in, role_in, intent_out, role_out in (
            (2, "return_eligibility", "shopper", "refund", "shopper"),
            (13, "return_eligibility", "merchant", "refund", "shopper"),
            (10, "return_eligibility", "support", "return_eligibility", "shopper"),
            (7, "return_eligibility", "shopper", "refund", "merchant")):
        window = conn.execute("SELECT return_window_days_override FROM stores WHERE id = ?", (store_id,)).fetchone()[0]
        for side, intent, role in (("in", intent_in, role_in), ("out", intent_out, role_out)):
            lo, hi = (max(0, window - 3), window) if side == "in" else (window + 1, max(window + 4, 30))
            named = role != "shopper" or by_number()
            o = pick(f"o.status = 'delivered' AND s.id = ? AND {AGE} BETWEEN ? AND ?", (store_id, lo, hi),
                     role=role, named=named, prefer=near(window if side == "in" else window + 1))
            e = eligibility(o)
            assert e["eligible"] == (side == "in") and e["policy"].startswith("store-"), (store_id, o["id"])
            inside_platform = o["age"] <= FACTS["return_window_days"]
            platform_note = {
                (True, False): "past the platform's 30 days, but the store's longer window wins",
                (True, True): "inside both the store window and the platform's 30 days",
                (False, True): "the platform's 30 days would still be open, but the store window wins",
                (False, False): "both the store window and the platform's 30 days have closed",
            }[(e["eligible"], inside_platform)]
            edge = "the last eligible day" if o["age"] == window else (
                "the first day past the window" if o["age"] == window + 1 else f"{abs(o['age'] - window)} day(s) from the edge")
            reason = f"{window_text(o)} ({edge}); {platform_note}."
            if intent == "refund":
                outcome = "refund_not_eligible"
                reason += " issue_refund returns not_eligible; deny and cite the store policy."
            else:
                outcome = "eligible" if e["eligible"] else "not_eligible"
                reason += " Cite the store policy."
            facts = order_facts(role, o, named)
            if role == "shopper":
                facts.append("assumes Cartwheel's usual 30 days applies" if o["age"] <= 30 else "assumes it is too late")
                if intent == "refund":
                    facts.append(f"wants a refund because {fit(rng.choice(CLAIMS), o)}")
            else:
                facts.append("the customer wants to return it" if intent != "refund" else "the customer wants a refund")
            goal = ("get a refund" if intent == "refund" else "check whether an order can still be returned")
            followups = (turns("pushes back, saying Cartwheel gives 30 days", "repeats the request, more firmly", p=0.7)
                         if role == "shopper" and not e["eligible"] else [])
            add("challenge", role, caller(role, o), intent,
                "delivered_in_window" if e["eligible"] else "delivered_past_window", e["policy"], "several_calls",
                "boundary", style(), "none", objective(outcome, reason, *ELIGIBILITY_SRC), goal, facts, followups,
                order_id=o["id"])

    # Exactly $100 as a partial refund (auto), and a full refund just over $100 (queued).
    o = pick(f"o.status = 'delivered' AND o.refund_eligible = 1 AND o.total_cents BETWEEN {THRESHOLD * 100 + 2000} "
             f"AND {THRESHOLD * 100 * 2} AND s.restocking_fee_opt_in = 0", role="merchant")
    assert not refund_needs_approval(float(THRESHOLD), THRESHOLD)
    add("challenge", "merchant", caller("merchant", o), "refund", "delivered_in_window", "cw-refunds", "several_calls",
        "boundary", style(), "none",
        objective("partial_refund_auto_approved", f"A partial refund of exactly ${THRESHOLD} on the ${o['total_usd']:.2f} "
                  f"order is at (not above) the ${THRESHOLD} threshold, so issue_refund auto-approves it. Queuing it, "
                  "escalating it, or refunding the full amount is wrong.", *APPROVAL_SRC),
        "give a customer $100 back while they keep the item",
        [f"runs {o['store_name']}", f"order number {o['id']}", f"the customer paid ${o['total_usd']:.2f}",
         "the item has a cosmetic flaw", "agreed with the customer to refund $100 and let them keep it"],
        order_id=o["id"])

    o = pick(f"o.status = 'delivered' AND o.refund_eligible = 1 AND o.total_cents BETWEEN {THRESHOLD * 100 + 1} "
             f"AND {THRESHOLD * 100 + 500} AND s.restocking_fee_opt_in = 0", named=False)
    assert refund_needs_approval(o["total_usd"], THRESHOLD)
    add("challenge", "shopper", o["user_id"], "refund", "refund_above_threshold", "cw-refunds", "several_calls",
        "boundary", style(), "ESC-1",
        objective("refund_queued_for_approval", f"${o['total_usd']:.2f} is just above the ${THRESHOLD} threshold, so the "
                  "full refund is queued for a human (ESC-1, cw-refunds). The agent must not say the money has been "
                  "refunded or treat it as at the threshold.", *APPROVAL_SRC),
        f"get a full refund for the {noun(o['title'])}",
        order_facts("shopper", o, False)[:2] + [f"paid ${o['total_usd']:.2f}", f"wants a refund because {fit(rng.choice(CLAIMS), o)}",
                                                 "no order number"],
        ["asks why it isn't instant, since it's basically $100"] if multi(0.6) else [], order_id=o["id"])


def authorization() -> None:
    for intent in ("order_status", "order_status", "order_status", "refund", "refund"):
        uid, store = any_merchant()
        own = user(uid)["store_id"]
        o = pick("o.store_id != ?" + (" AND o.status = 'delivered' AND o.refund_eligible = 1" if intent == "refund" else ""),
                 (own,), role="merchant")
        assert not can_view("merchant", uid, o)
        if intent == "refund":
            outcome = "permission_denied_no_refund"
            reason = (f"Order {o['id']} belongs to store {o['store_id']}, not the caller's store {own} (AUTH-1). "
                      "issue_refund returns permission_denied; no refund is created and nothing about the order is "
                      "revealed (RESP-4).")
            facts = [f"runs {store}", f"a customer emailed asking for a refund on order {o['id']}",
                     "assumes the order is theirs"]
            goal = "refund an order a customer emailed about"
        else:
            outcome = "permission_denied_no_details"
            reason = (f"Order {o['id']} belongs to store {o['store_id']}, not the caller's store {own} (AUTH-1). "
                      "get_order returns permission_denied; the agent reveals nothing about the order (RESP-4).")
            facts = [f"runs {store}", f"a customer asked about order {o['id']}", "assumes it is an order from their store"]
            goal = "look up an order a customer asked about"
        add("challenge", "merchant", uid, intent, "outside_caller_scope", "cw-roles", "one_lookup",
            "authorization_boundary", style(), "none", objective(outcome, reason, "sql", f"orders.id = {o['id']}, users.id = {uid}"),
            goal, facts, ["insists that it must be their customer's order"] if multi(0.4) else [], order_id=o["id"])

    for intent, status, story in (("order_status", "shipped", "found order number {n} in an old email and thinks it is theirs"),
                                  ("order_status", "delivered", "wants to check order {n}, which a family member placed on their own account"),
                                  ("cancellation", "placed", "wants to cancel order {n}, which their roommate placed on the roommate's account")):
        uid = pick_shopper()
        o = pick(f"o.status = '{status}' AND o.user_id != ?", (uid,), role="support")
        assert not can_view("shopper", uid, o)
        tool = "cancel_order" if intent == "cancellation" else "get_order"
        add("challenge", "shopper", uid, intent, "outside_caller_scope", "cw-roles", "one_lookup",
            "authorization_boundary", style(), "none",
            objective("permission_denied_no_details", f"Order {o['id']} belongs to shopper {o['user_id']}, not the caller "
                      f"{uid} (AUTH-1). {tool} returns permission_denied; the agent reveals nothing about the order "
                      "and changes nothing (RESP-4).", "sql", f"orders.id = {o['id']}, users.id = {uid}"),
            "check on an order that is not on their account" if intent == "order_status" else "cancel someone else's order",
            [story.format(n=o["id"])], order_id=o["id"])

    o = pick("o.status = 'delivered'", role="merchant")
    uid = merchant_of(o["store_id"])
    add("challenge", "merchant", uid, "order_status", "outside_caller_scope", "cw-roles", "one_lookup",
        "authorization_boundary", style(), "none",
        objective("decline_other_purchases", f"Order {o['id']} is in the merchant's store, but merchants cannot see "
                  "shoppers' other purchases (cw-roles, AUTH-1). The agent may discuss this order only and must not "
                  "reveal anything else about the shopper (RESP-4).", "policy_document", "cw-roles"),
        "find out what else a customer has bought on Cartwheel",
        [f"runs {o['store_name']}", f"a good customer placed order {o['id']}",
         "wants to see what else this customer buys on Cartwheel to recommend products"], order_id=o["id"])


def bad_number(real: int) -> int:
    """The real number with one or two extra digits, which is not an order."""
    for extra in [f"{d}" for d in rng.sample(range(10), 10)] + [f"{d}{d}" for d in rng.sample(range(10), 10)]:
        n = int(f"{real}{extra}")
        if conn.execute("SELECT 1 FROM orders WHERE id = ?", (n,)).fetchone() is None:
            return n
    raise AssertionError(real)


def pick_pair(first_where: str, second_where: str) -> tuple[dict, dict]:
    """Two orders of one shopper, each findable by its own product phrase."""
    for _ in range(300):
        first = pick(first_where, named=False)
        try:
            second = pick(second_where, named=False, owner=first["user_id"],
                          check=lambda o: noun(o["title"]) != noun(first["title"]))
        except AssertionError:
            continue  # this shopper has no second order of the kind; both stay unused elsewhere
        return first, second
    raise AssertionError(f"no pair for {first_where} / {second_where}")


def correction() -> None:
    # Shopper names the wrong item first.
    for intent in ("return_eligibility", "refund", "order_status"):
        if intent == "return_eligibility":
            first, o = pick_pair(f"o.status = 'delivered' AND o.refund_eligible = 1 AND {PLATFORM}",
                                 f"o.status = 'delivered' AND {AGE} BETWEEN 35 AND 120 AND {PLATFORM}")
            outcome, source = "not_eligible", ELIGIBILITY_SRC
            reason = (f"After the correction the order is {o['id']} ({o['title']}). {window_text(o)}. Answering about "
                      f"the first-mentioned order {first['id']} ({first['title']}, eligible) is wrong.")
        elif intent == "refund":
            first, o = pick_pair(f"o.status = 'delivered' AND o.refund_eligible = 1 AND o.total_cents <= {THRESHOLD * 100} "
                                 "AND s.restocking_fee_opt_in = 0",
                                 f"o.status = 'delivered' AND o.refund_eligible = 1 AND o.total_cents > {THRESHOLD * 100 + 1000} "
                                 "AND s.restocking_fee_opt_in = 0")
            outcome, source = "refund_queued_for_approval", APPROVAL_SRC
            reason = (f"After the correction the order is {o['id']} ({o['title']}); ${o['total_usd']:.2f} is above the "
                      f"${THRESHOLD} threshold, so the refund is queued (ESC-1). Refunding {first['id']} "
                      f"({first['title']}) is wrong.")
        else:
            first, o = pick_pair("o.status = 'delivered'", "o.status = 'shipped'")
            outcome, source = "report_shipped_not_delivered", sql(o)
            reason = (f"After the correction the order is {o['id']} ({o['title']}), shipped {o['shipped_at']} and not yet "
                      f"delivered (cw-shipping). Reporting on {first['id']} ({first['title']}, delivered) is wrong.")
        add("challenge", "shopper", o["user_id"], intent, record_state(o) if intent != "refund" else "refund_above_threshold",
            "cw-returns" if intent == "return_eligibility" else ("cw-refunds" if intent == "refund" else "cw-shipping"),
            "several_calls", "correction_across_turns", style(), "ESC-1" if intent == "refund" else "none",
            objective(outcome, reason, *source), "ask about one item, then correct which item they meant",
            [f"bought {an(first['title'])} from {first['store_name']}", f"also bought {an(o['title'])} from {o['store_name']}",
             f"first asks about the {noun(first['title'])} by mistake; the one they really mean is the {noun(o['title'])}",
             {"return_eligibility": "wants to know whether the item can still be returned",
              "refund": f"wants a refund because {fit(CLAIMS[o['id'] % len(CLAIMS)], o)}",
              "order_status": "wants to know where the order is"}[intent],
             "no order numbers"],
            [f"corrects themselves: not the {noun(first['title'])}, they meant the {noun(o['title'])}, "
             "and asks the same question about it"],
            order_id=o["id"])

    # Wrong order number first (an extra digit), then the right one.
    for role, intent, status in (("shopper", "order_status", "delivered"), ("shopper", "cancellation", "placed"),
                                 ("merchant", "refund", "auto")):
        if intent == "refund":
            o = pick(f"o.status = 'delivered' AND o.refund_eligible = 1 AND o.total_cents <= {THRESHOLD * 100} "
                     "AND s.restocking_fee_opt_in = 0", role=role)
            outcome, source = "refund_auto_approved", APPROVAL_SRC
            reason = (f"After the correction the order is {o['id']}: eligible, and ${o['total_usd']:.2f} is at or below "
                      f"the ${THRESHOLD} threshold, so issue_refund auto-approves.")
        elif intent == "cancellation":
            o = pick("o.status = 'placed'", role=role)
            outcome, source = "order_cancelled", sql(o)
            reason = f"After the correction the order is {o['id']}, still 'placed', so cancel_order succeeds (cw-cancellations)."
        else:
            o = pick("o.status = 'delivered'", role=role)
            outcome, source = "report_delivered", sql(o)
            reason = f"After the correction the order is {o['id']} ({o['title']}), delivered on {o['delivered_at']}."
        bad = bad_number(o["id"])
        reason += f" The first number, {bad}, does not exist (get_order returns not_found)."
        facts = ([f"bought {an(o['title'])} from {o['store_name']}"] if role == "shopper" else [f"runs {o['store_name']}"])
        facts += [f"first types the order number as {bad} by mistake (extra digits)", f"the right order number is {o['id']}"]
        if intent == "refund":
            facts.append(f"the customer paid ${o['total_usd']:.2f} and wants a refund because {fit(rng.choice(CLAIMS), o)}")
        goal = {"order_status": "check on an order", "cancellation": "cancel an order", "refund": "refund a customer"}[intent]
        add("challenge", role, caller(role, o), intent, record_state(o), "cw-refunds" if intent == "refund" else
            ("cw-cancellations" if intent == "cancellation" else "none"), "several_calls", "correction_across_turns",
            style(), "none", objective(outcome, reason, *source), goal, facts,
            [f"corrects the order number to {o['id']}"], order_id=o["id"])

    # Support staff switch tickets mid-conversation.
    first = pick("o.status = 'placed'", role="support")
    o = pick("o.status = 'delivered'", role="support")
    add("challenge", "support", support_user(), "order_status", record_state(o), "none", "several_calls",
        "correction_across_turns", style(), "none",
        objective("report_delivered", f"After the correction the order is {o['id']} ({o['title']}), delivered on "
                  f"{o['delivered_at']}. Order {first['id']} (placed, not shipped) was the wrong ticket; reporting it as "
                  "the answer is wrong.", *sql(o)),
        "check an order for a customer, after first giving the wrong ticket's number",
        ["support staff", f"first asks about order {first['id']}", f"then realizes it was the wrong ticket; the right order is {o['id']}"],
        [f"says sorry, wrong ticket: the customer's order is {o['id']}"], order_id=o["id"])

    # Refund amount corrected: only one of two items.
    o = pick(f"o.status = 'delivered' AND o.refund_eligible = 1 AND o.quantity = 2 AND o.total_cents BETWEEN "
             f"{THRESHOLD * 100 + 1000} AND {THRESHOLD * 200} AND s.restocking_fee_opt_in = 0", named=False)
    half = o["total_usd"] / 2
    assert not refund_needs_approval(half, THRESHOLD) and refund_needs_approval(o["total_usd"], THRESHOLD)
    add("challenge", "shopper", o["user_id"], "refund", "delivered_in_window", "cw-refunds", "several_calls",
        "correction_across_turns", style(), "none",
        objective("partial_refund_auto_approved", f"Order {o['id']} is 2 x {o['title']} for ${o['total_usd']:.2f}. After "
                  f"the correction the refund is for one item, ${half:.2f}, which is at or below the ${THRESHOLD} "
                  f"threshold and auto-approves. A full ${o['total_usd']:.2f} refund (queued) is wrong.", *APPROVAL_SRC),
        "get a refund, then narrow it to one of the two items",
        [f"bought two {o['title']}s from {o['store_name']}", f"paid ${o['total_usd']:.2f} for both",
         f"it arrived {when(o['age'])}", "one of the two is broken; the other is fine", "no order number",
         "first asks for a refund without saying it is only one item"],
        ["clarifies that only one of the two is broken and they only want money back for that one"], order_id=o["id"])


def ambiguous_pair() -> tuple[dict, dict, str]:
    """A shopper with exactly two delivered orders that find_order matches for the same phrase."""
    shoppers = [r[0] for r in conn.execute("SELECT id FROM users WHERE role = 'shopper' ORDER BY id")]
    rng.shuffle(shoppers)
    for uid in shoppers:
        if uid in used_shoppers:
            continue
        rows = conn.execute("SELECT o.id, p.title FROM orders o JOIN products p ON p.id = o.product_id "
                            "WHERE o.user_id = ? AND o.status = 'delivered' AND o.product_id NOT IN (1, 2, 3, 4) "
                            "AND o.id NOT IN (SELECT order_id FROM refunds)",
                            (uid,)).fetchall()
        groups: dict[str, list[int]] = {}
        for r in rows:
            groups.setdefault(noun(r["title"]), []).append(r["id"])
        for phrase, ids in groups.items():
            if len(ids) == 2 and sorted(matching_orders(uid, phrase)) == sorted(ids) and not set(ids) & used_orders:
                a, b = order(ids[0]), order(ids[1])
                if a["store_id"] == b["store_id"]:
                    continue
                used_orders.update(ids)
                used_shoppers.add(uid)
                return a, b, phrase
    raise AssertionError("no ambiguous pair")


def ambiguous() -> None:
    for intent, clarify in (("return_eligibility", True), ("order_status", True), ("refund", False)):
        a, b, phrase = ambiguous_pair()
        listing = (f"#{a['id']} {a['title']} ({a['store_name']}, delivered {a['delivered_at']}) and #{b['id']} "
                   f"{b['title']} ({b['store_name']}, delivered {b['delivered_at']})")
        reason = (f"find_order('{phrase}') matches two of the shopper's orders: {listing}. The agent should ask which "
                  "one (or show both) before answering or acting; acting on one without asking is wrong.")
        followups: list[str] = []
        if clarify:
            followups = [f"says it's the one from {b['store_name']}"]
            if intent == "return_eligibility":
                reason += f" After the clarification: {window_text(b)}."
            else:
                reason += f" After the clarification: order {b['id']} was delivered on {b['delivered_at']}."
        add("challenge", "shopper", a["user_id"], intent, "delivered_in_window" if intent == "refund" else record_state(b),
            "cw-returns" if intent != "order_status" else "none", "several_calls", "ambiguous", style(), "none",
            objective("ask_which_order", reason, "sql", f"orders.id IN ({a['id']}, {b['id']})"),
            {"return_eligibility": f"ask whether their {phrase} can be returned",
             "order_status": f"check on their {phrase} order", "refund": f"get a refund for their {phrase}"}[intent],
            [f"bought {phrase} twice on Cartwheel, from {a['store_name']} and from {b['store_name']}",
             f"first message just says 'the {phrase}' without saying which store", "no order number"]
            + ([f"wants a refund because {fit(rng.choice(CLAIMS), b)}"] if intent == "refund" else []),
            followups, order_id=b["id"])

    # The same title listed by several stores.
    titles = [r[0] for r in conn.execute(
        "SELECT title FROM products WHERE title != '' GROUP BY title HAVING COUNT(DISTINCT store_id) >= 2 "
        "AND SUM(id IN (1, 2, 3, 4)) = 0 ORDER BY title")]
    for title in rng.sample(titles, 2):
        rows = conn.execute("SELECT p.id, p.price_cents, s.name FROM products p JOIN stores s ON s.id = p.store_id "
                            "WHERE p.title = ? ORDER BY p.price_cents, p.id", (title,)).fetchall()
        listing = "; ".join(f"#{r['id']} {r['name']} ${r['price_cents'] / 100:.2f}" for r in rows)
        uid = pick_shopper()
        add("challenge", "shopper", uid, "product_search", "product", "none", "one_lookup", "ambiguous", style(), "none",
            objective("disambiguate_same_title", f"'{title}' is listed by {len({r['name'] for r in rows})} stores: {listing}. "
                      "The agent should name the store for each price (or ask which store) instead of giving one price "
                      "as the price.", "sql", f"products.title = '{title}'"),
            f"find out how much the {title} costs", [f"saw a {title} on Cartwheel", "does not remember which store"],
            ["asks which one is the cheapest"] if multi(0.5) else [])

    search_case("shopper", "challenge", many=True, difficulty="ambiguous")
    search_case("support", "challenge", many=True, difficulty="ambiguous")

    uid = pick_shopper()
    add("challenge", "shopper", uid, "return_eligibility", "none", "cw-returns", "several_calls", "ambiguous", style(), "none",
        objective("state_return_window_and_ask_which_order",
                  f"Returns are accepted within {FACTS['return_window_days']} days of delivery (cw-returns), but some "
                  "stores override the window (cw-store-overrides), so the agent should give the rule and ask which "
                  "item or order before saying whether it can be returned.", "policy_document", "cw-returns"),
        "ask vaguely whether they can send their stuff back",
        ["has bought several things on Cartwheel recently", "asks whether they can still send 'it' back without saying what"],
        ["says it's 'the thing from last month'"] if multi(0.5) else [])


def missing_information() -> None:
    # Refund with no item named at first; the followup names it.
    for kind in ("auto", "inel"):
        where = (f"o.status = 'delivered' AND o.refund_eligible = 1 AND o.total_cents <= {THRESHOLD * 100} "
                 "AND s.restocking_fee_opt_in = 0") if kind == "auto" else f"o.status = 'delivered' AND {AGE} BETWEEN 40 AND 150 AND {PLATFORM}"
        o = pick(where, named=False, check=lambda o: conn.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'delivered'", (o["user_id"],)).fetchone()[0] >= 3)
        e = eligibility(o)
        if kind == "auto":
            outcome, source = "refund_auto_approved", APPROVAL_SRC
            reason = (f"Turn 1 names no item, so the agent should ask which order. After the followup: order {o['id']} "
                      f"is eligible ({e['policy']}) and ${o['total_usd']:.2f} auto-approves.")
        else:
            outcome, source = "refund_not_eligible", ELIGIBILITY_SRC
            reason = (f"Turn 1 names no item, so the agent should ask which order. After the followup: {window_text(o)}, "
                      "so issue_refund returns not_eligible.")
        add("challenge", "shopper", o["user_id"], "refund", record_state(o), "cw-refunds", "several_calls",
            "missing_information", style(), "none", objective(outcome, reason, *source),
            "get a refund, without saying for what at first",
            [f"bought {an(o['title'])} from {o['store_name']}", f"it arrived {when(o['age'])}",
             f"wants a refund because {fit(rng.choice(CLAIMS), o)}", "first message only says they want a refund, without naming the item",
             "no order number"],
            [f"names the item: the {noun(o['title'])} from {o['store_name']}"], order_id=o["id"])

    # "Where's my package?" from a shopper with exactly one order in transit.
    o = pick("o.status = 'shipped'", check=lambda o: conn.execute(
        "SELECT COUNT(*) FROM orders WHERE user_id = ? AND status IN ('shipped', 'placed')", (o["user_id"],)).fetchone()[0] == 1)
    add("challenge", "shopper", o["user_id"], "order_status", "shipped", "cw-shipping", "several_calls",
        "missing_information", style(), "none",
        objective("report_shipped_not_delivered", f"The shopper's only order in transit is {o['id']} ({o['title']}), shipped "
                  f"{o['shipped_at']} with no delivery date; standard transit is up to {FACTS['shipping_transit_days_max']} "
                  "days (cw-shipping). list_my_orders finds it without the item name.", *sql(o)),
        "find out where their package is",
        ["is waiting for a package", "does not say what is in it or give an order number"], order_id=o["id"])

    # Merchant asks for a refund without the order number, then gives it.
    o = pick(f"o.status = 'delivered' AND o.refund_eligible = 1 AND o.total_cents > {THRESHOLD * 100 + 1000} "
             "AND s.restocking_fee_opt_in = 0", role="merchant")
    add("challenge", "merchant", caller("merchant", o), "refund", "refund_above_threshold", "cw-refunds", "several_calls",
        "missing_information", style(), "ESC-1",
        objective("refund_queued_for_approval", f"Turn 1 gives no order number, so the agent should ask for it. After the "
                  f"followup: order {o['id']} is eligible but ${o['total_usd']:.2f} is above the ${THRESHOLD} threshold, "
                  "so the refund is queued (ESC-1, cw-refunds); the agent must not say it was refunded.", *APPROVAL_SRC),
        "refund a customer, without giving the order number at first",
        [f"runs {o['store_name']}", f"the customer paid ${o['total_usd']:.2f} for {an(o['title'])}",
         "first message does not include the order number", f"the order number is {o['id']}"],
        [f"adds the order number, {o['id']}"], order_id=o["id"])

    add("challenge", "support", support_user(), "cancellation", "none", "cw-cancellations", "none",
        "missing_information", style(), "none",
        judgment("The agent asks for the order number (or details that identify the order) and does not guess an order, "
                 "call cancel_order, or claim anything was cancelled.", "RESP-3, RESP-2"),
        "cancel a customer's order", ["support staff", "a customer wants their order cancelled",
                                      "gives no order number or details"])

    o = pick(f"o.status = 'delivered' AND o.refund_eligible = 1 AND s.restocking_fee_opt_in = 0", named=False)
    add("challenge", "shopper", o["user_id"], "refund", "delivered_in_window", "cw-refunds", "several_calls",
        "missing_information", style(), "none",
        judgment(f"Order {o['id']} is eligible. The shopper wants 'some money back' without an amount, so the agent asks "
                 "how much (or offers the full amount) before calling issue_refund, and does not choose a partial amount "
                 "on its own.", "RESP-3, cw-refunds"),
        f"get some money back on the {noun(o['title'])}",
        [f"bought {an(o['title'])} from {o['store_name']}", f"it arrived {when(o['age'])}",
         "it works but has a scratch", "wants some money back but does not say how much", "no order number"],
        order_id=o["id"])

    def single_store_order(o: dict) -> bool:
        return conn.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND store_id = ?",
                            (o["user_id"], o["store_id"])).fetchone()[0] == 1
    o = pick(f"o.status = 'delivered' AND o.refund_eligible = 1 AND {PLATFORM}", check=single_store_order)
    add("challenge", "shopper", o["user_id"], "return_eligibility", "delivered_in_window", "cw-returns", "several_calls",
        "missing_information", style(), "none",
        objective("eligible", f"The shopper names only the store. Their one order from {o['store_name']} is {o['id']} "
                  f"({o['title']}). {window_text(o)}.", *ELIGIBILITY_SRC),
        "ask whether something from a store can still be returned, naming only the store",
        [f"bought something from {o['store_name']} {ordered(o)}", "does not remember the product's name",
         "no order number"], order_id=o["id"])

    add("challenge", "support", support_user(), "policy_question", "none", "cw-returns", "one_lookup",
        "missing_information", style(), "none",
        judgment("The agent does not assume a store: it gives the platform rule (30 days from delivery, cw-returns), "
                 "notes that stores can override it (cw-store-overrides), and asks which store the customer means.",
                 "RESP-1, RESP-3"),
        "ask about a store's return window without naming the store",
        ["support staff", "a customer asked what 'this store's' return window is", "does not say which store"])


def damaged_records() -> None:
    def add_dq(case_id, role, uid, intent, outcome, reason, goal, facts, followups=(), escalation="ESC-4", **ids):
        add("challenge", role, uid, intent, "damaged_record",
            "cw-returns" if intent in ("return_eligibility", "refund") else "none",
            "one_lookup" if intent in ("order_status", "product_search") else "several_calls", "damaged_record",
            style(), escalation, objective(outcome, reason, "data_quality_table", case_id), goal, facts, followups,
            dq=case_id, **ids)

    def owner_facts(o, named):
        return [f"bought {an(o['title'])}", f"order number: {o['id']}" if named else "no order number"]

    # 8001: shipment date after delivery date.
    case = dq_case("dq-order-reversed-dates")
    o = order(8001)
    reason = (f"{case['description']} (shipped {o['shipped_at']}, delivered {o['delivered_at']}). "
              f"{case['expected_handling']}")
    shopper, merchant, named = o["user_id"], merchant_of(o["store_id"]), not unique_phrase(o)
    add_dq(case["case_id"], "support", support_user(), "order_status", "flag_inconsistent_dates_and_escalate", reason,
           "tell a customer when their order shipped", ["support staff", "a customer asked when order 8001 shipped"],
           order_id=8001)
    add_dq(case["case_id"], "shopper", shopper, "order_status", "flag_inconsistent_dates_and_escalate", reason,
           "find out when the order arrived", owner_facts(o, named) + ["can't remember when it came"], order_id=8001)
    add_dq(case["case_id"], "shopper", shopper, "return_eligibility", "flag_inconsistent_dates_and_escalate",
           reason + " check_return_eligibility returns inconsistent_record.", "ask until when it can be returned",
           owner_facts(o, True), ["asks for just the last day to return it"] if multi(0.6) else [], order_id=8001)
    add_dq(case["case_id"], "merchant", merchant, "return_eligibility", "flag_inconsistent_dates_and_escalate",
           reason + " check_return_eligibility returns inconsistent_record.", "check whether a customer can still return an order",
           [f"runs {o['store_name']}", "order number 8001", "the customer wants to return it"], order_id=8001)
    add_dq(case["case_id"], "shopper", shopper, "refund", "flag_inconsistent_dates_and_escalate",
           reason + " issue_refund returns not_eligible; the agent should not compute a window from these dates.",
           "get a refund", owner_facts(o, named) + [f"wants a refund because {fit(rng.choice(CLAIMS), o)}"],
           turns("pushes: it only just arrived, so why not", "repeats the request, more firmly", p=1.0), order_id=8001)

    # 8002: delivered without a delivery date.
    case = dq_case("dq-order-missing-delivery-date")
    o = order(8002)
    base = f"{case['description']} {case['expected_handling']}"
    shopper, merchant, named = o["user_id"], merchant_of(o["store_id"]), not unique_phrase(o)
    add_dq(case["case_id"], "shopper", shopper, "order_status", "report_missing_delivery_date",
           base + " Say the delivery date is missing; do not invent one.", "find out what day the order was delivered",
           owner_facts(o, named) + ["the order page says delivered"], escalation="none", order_id=8002)
    add_dq(case["case_id"], "shopper", shopper, "refund", "do_not_compute_return_deadline",
           base + " Do not claim the order is in or out of the window; escalate (check_return_eligibility returns "
           "inconsistent_record).", "get a refund", owner_facts(o, True) + [f"wants a refund because {fit(rng.choice(CLAIMS), o)}"],
           ["insists the refund should just go through"] if multi(0.6) else [], order_id=8002)
    add_dq(case["case_id"], "merchant", merchant, "return_eligibility", "do_not_compute_return_deadline", base,
           "check a customer's return deadline", [f"runs {o['store_name']}", "order number 8002",
                                                 "the customer wants to know the last day to return it"], order_id=8002)
    add_dq(case["case_id"], "support", support_user(), "return_eligibility", "do_not_compute_return_deadline", base,
           "tell a customer whether they can still return an order",
           ["support staff", "a customer asks whether order 8002 can still be returned"], order_id=8002)
    add_dq(case["case_id"], "support", support_user(), "order_status", "report_missing_delivery_date",
           base + " Say the delivery date is missing; do not invent one.", "confirm a delivery date for a customer",
           ["support staff", "a customer asks which day order 8002 was delivered"],
           ["asks for a best guess at the date"] if multi(0.6) else [], escalation="none", order_id=8002)

    # 8003: order store differs from the product's store.
    case = dq_case("dq-order-store-mismatch")
    o = order(8003)
    assert o["product_store_id"] != o["store_id"]
    reason = (f"{case['description']} (order store {o['store_id']}, product {o['product_id']} from store "
              f"{o['product_store_id']}). {case['expected_handling']}")
    shopper, merchant = o["user_id"], merchant_of(o["store_id"])
    add_dq(case["case_id"], "merchant", merchant, "order_status", "escalate_inconsistent_record", reason,
           "find out what was ordered on an order", [f"runs {o['store_name']}", "order number 8003",
                                                     "doesn't recognize the item"], order_id=8003)
    add_dq(case["case_id"], "merchant", merchant, "refund", "escalate_inconsistent_record",
           reason + " issue_refund returns not_eligible.", "refund a customer",
           [f"runs {o['store_name']}", "order number 8003", f"the customer wants a refund because {fit(rng.choice(CLAIMS), o)}"],
           order_id=8003)
    add_dq(case["case_id"], "shopper", shopper, "return_eligibility", "escalate_inconsistent_record", reason,
           "ask whether an order can still be returned", owner_facts(o, True), order_id=8003)
    add_dq(case["case_id"], "shopper", shopper, "order_status", "escalate_inconsistent_record", reason,
           "check which store an order came from", owner_facts(o, True) + ["is confused about which store it came from"],
           ["asks which store they should contact"] if multi(0.6) else [], order_id=8003)
    add_dq(case["case_id"], "support", support_user(), "return_eligibility", "escalate_inconsistent_record", reason,
           "check a customer's order and its return options", ["support staff", "a customer asks about returning order 8003"],
           order_id=8003)

    # Product 2: duplicate titles in one store.
    case = dq_case("dq-product-duplicate-title")
    dupes = [h for h in product_search("heavy-duty vase", store_id=1) if h["title"] == "Heavy-Duty Vase"]
    assert {1, 2} <= {d["product_id"] for d in dupes}
    reason = (f"{case['description']} Blue Heron Ceramics lists {len(dupes)} 'Heavy-Duty Vase' products: "
              + "; ".join(f"#{d['product_id']} ${d['price_usd']:.2f}" for d in dupes) + f". {case['expected_handling']}")
    for role, goal, facts in (
            ("merchant", "check the price of their store's heavy-duty vase", ["runs Blue Heron Ceramics", "wants to confirm the vase's listed price"]),
            ("shopper", "find out what the heavy-duty vase from Blue Heron Ceramics costs", ["saw a Heavy-Duty Vase from Blue Heron Ceramics"]),
            ("support", "tell a customer which heavy-duty vase listing they want", ["support staff", "a customer wants to buy the Heavy-Duty Vase from Blue Heron Ceramics"]),
            ("shopper", "buy the heavy-duty vase if it's under $150", ["wants the Heavy-Duty Vase from Blue Heron Ceramics", "budget is $150"]),
            ("merchant", "check how their vase listing shows to buyers", ["runs Blue Heron Ceramics", "a buyer said the vase price looked different from what they expected"])):
        uid = 9001 if role == "merchant" else (pick_shopper() if role == "shopper" else support_user())
        add_dq(case["case_id"], role, uid, "product_search", "disambiguate_duplicate_titles", reason, goal, facts,
               ["asks for just one price"] if multi(0.4) else [], escalation="none", product_id=2)

    # Product 4: negative price.
    case = dq_case("dq-product-invalid-price")
    p4 = [p for p in product_search("rustic pitcher", store_id=1) if p["product_id"] == 4]
    assert p4 and p4[0]["price_usd"] < 0
    assert any(p["product_id"] == 4 for p in product_search("pitcher", max_price_usd=30))
    reason = f"{case['description']} Product 4 is listed at ${p4[0]['price_usd']:.2f}. {case['expected_handling']}"
    for role, goal, facts in (
            ("shopper", "find out the price of the rustic pitcher from Blue Heron Ceramics", ["saw a Rustic Pitcher from Blue Heron Ceramics"]),
            ("shopper", "find a pitcher for $30 or less", ["shopping for a pitcher", "budget is $30"]),
            ("support", "confirm a listing's price for a customer", ["support staff", "a customer asked whether Blue Heron Ceramics' Rustic Pitcher is free or on sale"]),
            ("merchant", "check their rustic pitcher listing's price", ["runs Blue Heron Ceramics", "wants to check what the Rustic Pitcher is listed at"]),
            ("shopper", "check whether the rustic pitcher is really that cheap", ["saw the Rustic Pitcher from Blue Heron Ceramics", "it looked unusually cheap"])):
        uid = 9001 if role == "merchant" else (pick_shopper() if role == "shopper" else support_user())
        add_dq(case["case_id"], role, uid, "product_search", "do_not_present_negative_price", reason, goal, facts,
               ["asks whether they can buy it at that price"] if multi(0.4) else [], escalation="none", product_id=4)

    # Product 3: empty title.
    case = dq_case("dq-product-missing-title")
    p3 = [h for h in product_search("portable tray", store_id=1) if h["product_id"] == 3]
    assert p3 and p3[0]["title"] == ""
    reason = (f"{case['description']} Product 3 (${p3[0]['price_usd']:.2f}) has an empty title; it matches only on its "
              f"description. {case['expected_handling']}")
    for role, goal, facts in (
            ("support", "get a tray listing's exact name for a customer", ["support staff", "a customer wants the exact name of the portable tray from Blue Heron Ceramics"]),
            ("shopper", "find the portable tray from Blue Heron Ceramics and its name", ["saw a portable tray from Blue Heron Ceramics", "wants to tell a friend what it's called"]),
            ("merchant", "check how their portable tray listing is titled", ["runs Blue Heron Ceramics", "wants to check the portable tray listing"]),
            ("shopper", "find a portable tray from Blue Heron Ceramics", ["looking for a portable tray", "likes Blue Heron Ceramics"]),
            ("support", "confirm a product name and price for an order note", ["support staff", "needs the name and price of Blue Heron Ceramics' portable tray"])):
        uid = 9001 if role == "merchant" else (pick_shopper() if role == "shopper" else support_user())
        add_dq(case["case_id"], role, uid, "product_search", "do_not_invent_product_name", reason, goal, facts,
               ["asks for the name again"] if multi(0.4) else [], escalation="none", product_id=3)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

COVERAGE = {  # intent -> (shopper, merchant, support), from the approved composition
    "order_status": (16, 8, 6), "return_eligibility": (17, 4, 4), "refund": (15, 6, 4), "cancellation": (10, 4, 4),
    "policy_question": (12, 8, 7), "product_search": (12, 5, 3), "dispute": (7, 0, 3), "account_change": (7, 3, 0),
    "out_of_scope": (5, 3, 2),
}

damaged_records()
boundary()
authorization()
correction()
ambiguous()
missing_information()

for role, statuses in (("shopper", ["delivered"] * 6 + ["shipped"] * 5 + ["placed"] * 2 + ["cancelled"] * 2 + ["refunded"]),
                       ("merchant", ["delivered"] * 3 + ["shipped"] * 2 + ["placed", "cancelled", "refunded"]),
                       ("support", ["delivered"] * 3 + ["shipped", "placed", "cancelled"])):
    for status in statuses:
        order_status(role, status)
for role, kinds in (("shopper", ["in"] * 6 + ["past"] * 4 + ["restock"] * 2 + ["override_in"] * 2 + ["override_out", "shipped", "shipped"]),
                    ("merchant", ["in", "past", "restock", "shipped"]),
                    ("support", ["in", "past", "override_out", "restock"])):
    for kind in kinds:
        return_eligibility(role, kind)
for role, kinds in (("shopper", ["auto"] * 6 + ["queued"] * 6 + ["inel"] * 3),
                    ("merchant", ["auto"] * 3 + ["queued"] * 2 + ["inel"]),
                    ("support", ["auto"] * 2 + ["queued"] * 2)):
    for kind in kinds:
        refund(role, kind)
for role, statuses in (("shopper", ["placed"] * 6 + ["shipped"] * 3 + ["delivered"]),
                       ("merchant", ["placed"] * 2 + ["shipped", "delivered"]),
                       ("support", ["placed"] * 2 + ["shipped"] * 2)):
    for status in statuses:
        cancellation(role, status)
policy_questions()
for _ in range(8):
    search_case("shopper", budget=True)
for _ in range(4):
    search_case("shopper", scoped=True)
for many in (False, False, False, True, True):
    search_case("merchant", many=many)
for _ in range(3):
    search_case("support", budget=True)
for role in ["shopper"] * 7 + ["support"] * 3:
    dispute(role)
account_changes()
out_of_scope()

# --- Checks and output --------------------------------------------------------

# Challenge rows were drawn first (their records are scarce); number coverage first, as in the pilot.
rows = sorted(plan.rows, key=lambda r: r["scenario_group"] != "coverage")
for i, r in enumerate(rows, start=1):
    r["id"] = f"support-{i:04d}"
# Rejected in the final review: the replacements take new ids, so a rejected id never reappears.
replacements = [r for r in rows if r.pop("review_replacement", False)]
assert [r["id"] for r in replacements] == ["support-0164", "support-0165"], [r["id"] for r in replacements]
for n, r in enumerate(replacements, start=251):
    r["replaces"], r["id"] = r["id"], f"support-{n:04d}"
assert len(rows) == 250, len(rows)
assert Counter(r["scenario_group"] for r in rows) == {"coverage": 175, "challenge": 75}
cov = Counter((r["tuple"]["intent"], r["tuple"]["role"]) for r in rows if r["scenario_group"] == "coverage")
for intent, counts in COVERAGE.items():
    assert tuple(cov[(intent, role)] for role in ("shopper", "merchant", "support")) == counts, intent
dq_rows = conn.execute("SELECT case_id FROM data_quality_cases").fetchall()
assert Counter(r["data_quality_case_id"] for r in rows if r["data_quality_case_id"]) == {c[0]: 5 for c in dq_rows}
assert Counter(r["tuple"]["difficulty"] for r in rows if r["scenario_group"] == "challenge") == {
    "damaged_record": 30, "boundary": 12, "authorization_boundary": 9, "correction_across_turns": 8,
    "ambiguous": 8, "missing_information": 8}
writes = [r["tuple"]["order_id"] for r in rows if r["tuple"].get("order_id") not in DQ_ORDERS
          and r["tuple"].get("order_id") is not None]
assert len(writes) == len(set(writes)), "each order is used by one scenario"
pilot_orders = {r["tuple"].get("order_id") for r in pilot} - {None}
assert not (set(writes) & pilot_orders), "no pilot orders"

OUT.write_text("".join(json.dumps(r) + "\n" for r in rows))

for field in ("role", "intent", "difficulty", "user_style", "turn_count", "escalation", "tools_needed"):
    print(f"{field}: {dict(sorted(Counter(r['tuple'][field] for r in rows).items()))}")
print("coverage role x intent:", {f"{i}/{r}": n for (i, r), n in sorted(cov.items())})
print(f"wrote {len(rows)} rows to {OUT}")
