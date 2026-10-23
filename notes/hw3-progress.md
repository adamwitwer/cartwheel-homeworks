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

- **Walkthrough step:** 2, Part A done (dimensions approved 2026-10-22).
- **Next step:** Part B, build the 30-row pilot plan grounded in the database.
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
- [ ] `scenarios/pilot_scenarios.jsonl`: 30 scenarios, broad role and intent coverage
- [ ] Conversation sample reviewed by me before the run
- [ ] `uv run python -m scenarios.validate scenarios/pilot_scenarios.jsonl` passes
- [ ] Data reset, then pilot run: `scenarios/pilot-results.jsonl`
- [ ] At least 10 results reviewed in Langfuse by me
- [ ] `scenarios/pilot_review.jsonl`: `scenario_id`, `scenario_valid`, `confirmed_failure`,
  `evidence`, `scenario_change`
- [ ] At least 5 confirmed failures (else 20 more challenge scenarios, or a smaller model)

Part C, final scenarios
- [ ] `scenarios/support_scenarios.jsonl`: 175 coverage + 75 challenge (5 per damaged
  record = 30 of the 75); new IDs distinct from the pilot
- [ ] 15 reviewed by me (both groups, all three roles, every intent):
  `scenarios/support_review.jsonl` with `scenario_id`, `decision`, `reason`, `change`;
  every revision applied, every rejection replaced
- [ ] `scenarios/monitoring_scenarios.jsonl`: 50 final scenarios, both groups, all roles
- [ ] `uv run python -m scenarios.validate scenarios/support_scenarios.jsonl --final` passes

Part D, final run
- [ ] Data reset, then `scenarios/final-results.jsonl` with all 250 `completed`
- [ ] Coverage and challenge summarized separately

Part E, report and export
- [ ] `reports/smoke-output.txt` from `reports/smoke.sql`
- [ ] `traces/support_traces.json` with all 250 scenario IDs
- [ ] 3 exported traces checked (one challenge, one multi-turn): conversation, model,
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

- HW2 run 3 (support, Juniper lamp, trace 2ae2344d…) is a store-override failure of the
  kind HW3 targets. Do not copy it; let the "store override" dimension produce such cases.
