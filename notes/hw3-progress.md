# HW3 progress note

Working notes for the guided HW3 walkthrough (the prompt at the top of
`homework/module-1/hw3.md`). This file is not part of the submission. A new
session should read this first, then pick up at **Next step**.

Rules from `AGENTS.md` and `scenarios/skill/SKILL.md` that apply throughout:
- Extra metadata (the answer key) comes from the database, `facts.yaml`, the policy
  documents, or the data quality table, never from a model's answer.
- The model that writes user messages never sees the extra metadata.
- Keep scenario generation separate from running the application.
- Stop for my decisions at the three review points: dimension plan, pilot review,
  final review. I brainstorm dimensions before Claude proposes any.
- No prompt injection or malicious documents (that is HW8).

## Current status

- **Walkthrough step:** 5, pilot run done (2026-10-23): data reset, 30/30 completed on
  gpt-4o-mini, 41 turn traces in Langfuse (all 30 scenario ids). Review aid with every
  conversation, tool call, answer key, and trace link: `notes/hw3/pilot_review_aid.md`.
  Run changed: refunds 575-578, escalations 151-154, order 4385 cancelled, 5339 and 7941
  refunded (reset before the final run).
  Pilot review done (2026-10-26): I reviewed all 30; `scenarios/pilot_review.jsonl`
  written from my notes in the review aid. 30 valid, 12 confirmed failures (002, 008,
  011, 013, 015, 018, 019, 021, 022, 026, 027, 028), no scenario changes.
- **Part C step 1 done (2026-10-26):** data reset; `notes/hw3/build_final_plan.py` wrote
  `notes/hw3/final_plan.jsonl` (250 rows, `support-0001`-`0175` coverage, `0176`-`0250`
  challenge). Composition approved by me 2026-10-26 (see the plan script's docstring).
  Shared lookups moved to `notes/hw3/plan_lib.py`; the pilot plan rebuilds unchanged.
  Day-30 refund uses an order over $100 (the only day-30 order at or under $100 was
  pilot-021's). Multi-turn share is 36% (2-3 turns), a bit under the 40% proposed.
- **Part C step 2 done (2026-10-26):** `scenarios/support_scenarios.jsonl` generated (gpt-4.1
  writer + critic); `validate --final` passes. Claude's pre-review check found 16 conversations
  that didn't fit their keys, all from plan wording (shoppers claiming a delivered order never
  came; support staff answering the customer instead of asking; vague item corrections; a
  followup that presumed a question). Reworded those templates (generation blocks only; tuples
  and keys unchanged) and regenerated 0001-0006, 0119-0125, 0227-0229, 0246.
- **Final review done (2026-10-26):** I reviewed the 15 in `notes/hw3/final_review_aid.md`:
  8 accept, 6 revise (0004, 0050, 0079, 0182, 0228, 0249), 1 reject (0164).
  `scenarios/support_review.jsonl` written from my notes, with an `applied` field saying
  what was done. Each fix was made where the problem came from (plan or generator), so it
  covers every row with the same cause:
  - Ages: `plan_lib.ago` stops at "about six weeks"; `build_final_plan.when` now words longer
    ages (22 rows) and today/yesterday (11 rows). Pilot plan untouched.
  - 0249: purchase date taken from `ordered_at`, not the delivery date.
  - 0228: refund reasons fit the product category (12 rows). 0079 had the same problem; I
    changed it from accept to revise after Claude flagged it.
  - 0050: merchants state the condition; no "perfect condition" followup (3 turns to 2).
  - 0182: shoppers in shorthand style write in the first person (`generate.py`); 0081 too.
  - 0164 rejected, and 0165 (same template), replaced by shopper rows support-0251 and
    support-0252 (plan field `replaces`). Coverage account_change is now shopper 7,
    support 0; roles 144 / 60 / 46.
  Plan diff checked: no other tuple or key changed. 48 conversations regenerated and read;
  `validate --final` passes (250 records).
- **Monitoring set done (2026-10-26):** `notes/hw3/select_monitoring.py` (fixed seed) wrote
  `scenarios/monitoring_scenarios.jsonl`: 35 coverage (each intent's share, every role in
  each intent with 3+ slots) and 15 challenge (one per damaged record, then 2/2/2/2/1 across
  boundary, authorization, correction, ambiguous, missing information). Roles 25 / 15 / 10;
  all nine intents; 17 multi-turn. Validator passes.
- **Final run done (2026-10-26):** data reset (plan rebuilt byte-identical on the fresh
  data), server on 8010, 250/250 `completed` on gpt-4o-mini, no errors, no empty replies.
  - Coverage: 175 scenarios, 247 turns (59 multi-turn), median 3.9 s, 11.6 min total.
  - Challenge: 75 scenarios, 109 turns (32 multi-turn), median 4.3 s, 6.4 min total.
  - Run changed the data: 19 new refunds, 10 new escalations, 4 orders cancelled (reset
    before any rerun of a refund or cancel scenario).
- **Part E done by Claude (2026-10-26):** `reports/smoke-output.txt` written (it covers all
  Langfuse traces, so the 41 pilot traces are included: 397 = 356 final + 41 pilot).
  `traces/support_traces.json`: 356 traces, 250/250 scenarios, none missing. Server stopped
  after the export. Claude checked three traces in the export (each turn is its own trace):
  - support-0182 (challenge, damaged record 8002): eb9d05be76ceec6eb4f9176a33b61ae9
  - support-0228 (challenge, 2 turns): a58e096bb996c089806156b4b054528e, 2f79c973875fcf51ff93253e1f2559a5
  - support-0050 (coverage, merchant, 2 turns): 4d00b7cbe38519f7784a4ca2f6ac0212, 31f2953930de1b5b409631c2a399d297
  I opened and reviewed all three in Langfuse (2026-10-26).
- **Next step:** video (5 min or less) and the Discord post, both by me.
- **Review standard I used (apply the same in the final review):** policy questions
  (008, 013, 018) fail without a policy lookup and citation (RESP-1); where the key is
  about a decision (003, 017, 020, 023), a correct decision passes even without a
  citation; 019 failed because its key requires citing the store override.
- **Model for every run:** `gpt-4o-mini` (`CARTWHEEL_MODEL` in `.env`), unless the pilot
  shows fewer than five failures and I choose a smaller model.
- **Blockers:** none. Docker Desktop must be running before the pilot (Part B).

## Deliverables checklist

Part A, plan
- [x] Damaged records read (`data_quality_cases`, 6 cases)
- [x] Dimensions brainstormed by me, completed by Claude, approved by me. Required:
  role, intent, record involved, applicable policy, tools needed, difficulty
  (+ user style, which the validator requires)

Part B, pilot
- [x] `scenarios/pilot_scenarios.jsonl`: 30 scenarios, broad role and intent coverage
- [x] Conversation sample reviewed by me before the run (019 rewritten at my request)
- [x] `uv run python -m scenarios.validate scenarios/pilot_scenarios.jsonl` passes
- [x] Data reset, then pilot run: `scenarios/pilot-results.jsonl` (30/30 completed)
- [x] At least 10 results reviewed in Langfuse by me (all 30)
- [x] `scenarios/pilot_review.jsonl`: `scenario_id`, `scenario_valid`, `confirmed_failure`,
  `evidence`, `scenario_change`
- [x] At least 5 confirmed failures (12; no extra scenarios or model change needed)

Part C, final scenarios
- [x] `scenarios/support_scenarios.jsonl`: 175 coverage + 75 challenge (5 per damaged
  record = 30 of the 75); new IDs distinct from the pilot
- [x] 15 reviewed by me (both groups, all three roles, every intent):
  `scenarios/support_review.jsonl` with `scenario_id`, `decision`, `reason`, `change`;
  every revision applied, every rejection replaced
- [x] `scenarios/monitoring_scenarios.jsonl`: 50 final scenarios, both groups, all roles
- [x] `uv run python -m scenarios.validate scenarios/support_scenarios.jsonl --final` passes (re-run after any change)

Part D, final run
- [x] Data reset, then `scenarios/final-results.jsonl` with all 250 `completed`
- [x] Coverage and challenge summarized separately

Part E, report and export
- [x] `reports/smoke-output.txt` from `reports/smoke.sql`
- [x] `traces/support_traces.json` with all 250 scenario IDs
- [x] 3 exported traces checked (one challenge, one multi-turn): conversation, model,
  tools, `cartwheel_scenario_id`

Submission
- [ ] All 9 files committed and pushed
- [ ] Video recorded (5 min or less), done by me
- [ ] Posted to the course Discord submissions channel, done by me

## Approved dimension plan (2026-10-22)

My ideas: escalation (from the HW1 ESC-2 failure) and the refund threshold.
Claude's additions from SPEC.md, the policy docs, and the data; approved by me as is.

| # | Dimension (tuple field) | Values | Source |
|---|---|---|---|
| 1 | role | shopper, merchant, support | AUTH-1 |
| 2 | intent | order_status, return_eligibility, refund, cancellation, policy_question, product_search, dispute, account_change, out_of_scope | SPEC §2, §4 |
| 3 | record_state | order placed / shipped / delivered in window / delivered past window / already refunded or cancelled; refund above $100 (mine); order outside caller's scope; product; store policy page; damaged record; none | orders table, AUTH-1 |
| 4 | applicable_policy | platform rule (cw-returns, cw-refunds, cw-cancellations, cw-disputes, ...), store override, none | policy docs |
| 5 | tools_needed | none, one_lookup, several_calls | SPEC §4 |
| 6 | difficulty | well_specified, ambiguous, missing_information, boundary (mine: exactly $100 refund; also day 30, Juniper day 14), correction_across_turns, authorization_boundary, damaged_record | handout Part A, data |
| 7 | user_style | the 8 validator values | RESP-5, validator |
| 8 | escalation (mine) | none, ESC-1, ESC-2, ESC-3, ESC-4 | SPEC §5 |

Plus `turn_count` = 1 + followups (validator). Left out: prompt injection (HW8), language.

Key facts behind the plan:
- Refund threshold applies to the refund AMOUNT: at or below $100 auto-approves, above
  $100 is queued (`facts.yaml`). No order totals exactly $100; a $100 partial refund is
  the boundary case.
- Store overrides: Saltbox Pantry 7 days, Juniper Home Goods 14, Meridian Cycles 21,
  Northwind Books 45 (more lenient); Cascade Audio and Second Stitch Apparel charge up to
  15% restocking. Others follow the platform 30 days.
- Order statuses: delivered 8,915; refunded 573; cancelled 403; shipped 74; placed 35.
  14 orders delivered exactly 30 days before the world date; 1 Juniper order at exactly 14.
- Damaged records and who may access them: 8001 (shopper 174, store 16), 8002 (shopper
  392, store 20), 8003 (shopper 119, store 1); products 2, 3, 4 (search, any role).
  In final mode the validator requires `tuple.order_id` / `tuple.product_id` to match.

## Setup facts

- Course repo up to date as of 2026-10-22 (course HEAD a3aa8d5).
- The walkthrough prompt names `homework/module-1/AGENTS.md`, which does not exist in the
  course repo; the root `AGENTS.md` covers HW3.
- World date (`meta` as-of): 2026-07-01. Users: 500 shoppers, 20 merchants, 5 support.
- Policy numbers (`facts.yaml`): returns 30 days, auto-approve refunds up to $100,
  cancel before shipment, disputes 60 days after delivery.
- Langfuse and HW2 server setup: see `notes/hw2-progress.md`.
- 2026-10-23, moved to the larger-screen Mac. Docker Desktop installed there (first-run
  setup must finish before `docker compose` works). Langfuse 3.225.11 up and healthy,
  `.env` keys match, 0 traces. Langfuse data is per machine, so run the pilot, the
  final run, and the export all on this Mac. This note was uncommitted on the other Mac
  and was recreated here; commit it so it travels with the repo.

## Observations

- Store 1 (Blue Heron Ceramics) has four products titled "Heavy-Duty Vase" (ids 1, 2, 16,
  19), not only the two named by `dq-product-duplicate-title`. Pilot-028's answer key
  lists all four.
- Several shoppers have more than one order for similar products (e.g. shopper 277 has two
  rain shells). `build_plan.py` checks with the find_order matcher that each "no order
  number" scenario points at exactly one order.

- Pilot-022: `issue_refund` accepts any amount up to the order total and auto-approves
  at or below $100 (SPEC.md:89, cw-refunds), with no check of the reason or the amount.
  So any shopper can get up to $100 back on any eligible order without a human. Out of
  scope for HW3; worth raising in a later homework.
- HW2 run 3 (support, Juniper lamp, trace 2ae2344d…) is a store-override failure of the
  kind HW3 targets. Do not copy it; let the "store override" dimension produce such cases.
