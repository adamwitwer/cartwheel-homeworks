# HW1 progress note

Working notes for the guided HW1 walkthrough (`homework/module-1/hw1-tutorial.md`).
This file is not part of the submission. A new session should read this first,
then pick up at **Next step**.

## Current status

- **Walkthrough step:** 2, Get one conversation working
- **Next step:** Discuss the first conversation result (checkpoint), then
  Step 3: implement the five tools.
- **Blockers:** none

## Deliverables checklist

Part A, tools (`agent/tools.py`)
- [ ] `get_policy`
- [ ] `search_products`
- [ ] `list_my_orders`
- [ ] `cancel_order`
- [ ] `find_order`
- [ ] Focused tests pass: `uv run pytest --runxfail tests/test_hw_holes.py -k hw1`
- [ ] Regression tests pass: `uv run pytest tests/test_agent_tools.py tests/test_auth.py tests/test_eligibility.py`
- [ ] At least one additional tool of my own, registered in `TOOLS_BY_ROLE` and tested (pending: pick it from gaps seen in Part B)

Part B, conversations (`hw1-session.jsonl`, at least 10 records, all three roles)
- [ ] Shopper 1, authorized request about order 4127
- [ ] Shopper 1, order 3980 (outside refund window)
- [ ] Shopper 1, refund for order 4455 (above auto-approval threshold)
- [ ] Merchant 9002 (store 2), order 4127 (belongs to store 1)
- [ ] Question that depends on a store policy override
- [ ] Out-of-scope request
- [ ] Shopper 1, "change the email address on my Cartwheel account to new@example.com"
- [ ] My own case 1
- [ ] My own case 2
- [ ] My own case 3
- [ ] Support role (9501) used at least once
- [ ] Missing capabilities reviewed before leaving Part B

Part C, prompt investigation
- [ ] Requirement identified that is missing or vague in `SYSTEM_PROMPT_TEMPLATE`
- [ ] Test conversation run
- [ ] Either: before/after responses saved with the smallest prompt edit, or a written explanation of the omissions tested and why no edit was justified

Finish
- [ ] All deliverables checked against `homework/module-1/hw1.md`
- [ ] Commits prepared (`agent/tools.py`, `agent/agent.py` if revised, `hw1-session.jsonl`)
- [ ] Video recorded (5 min or less), done by me

## Setup facts

- Repo remotes: `origin` = my private repo `adamwitwer/cartwheel-homeworks`;
  `upstream` = course repo `ai-evals-course/cartwheel-homeworks`. Pull new
  assignments with `git pull upstream main`. Never push to upstream.
- Python 3.12 from Homebrew; `uv` 0.13.0 installed with Homebrew; `uv sync` done.
- `data/cartwheel.db` generated (dev scale, as of 2026-07-01; demo orders 4127, 3980, 4455 owned by user 1, store 1).
- Baseline: `uv run pytest` gives 147 passed, 4 skipped, 27 xfailed (xfails are unfinished homework).
  `--runxfail -k hw1` gives 8 failed, all `NotImplementedError` (expected before Part A).
- `.env` created from `.env.example` (gitignored). Provider: OpenAI, `CARTWHEEL_MODEL=gpt-5.5`; key verified 2026-10-12.
- Pushing to `main` runs the offline-checks GitHub Action (no keys needed).

## Missing capabilities seen (candidates for the additional tool)

- (none yet)

## Observations

- 2026-10-12, live (gpt-5.5), shopper 1, "What's the status of my order 4127?":
  one call `get_order(4127)` -> delivered 2026-06-19, $84.00, Blue Heron Ceramics,
  refund_eligible true. Response listed status, dates, total, refund eligibility.
  No visible explanation text before the tool call, though the prompt asks for one.
  My prediction: get_order, status and delivery date. Pre-Part A; not a Part B record.

## Log

- 2026-10-08: Created private repo, rewired remotes, started the walkthrough.
- 2026-10-12: Step 1 done. Installed uv, synced deps, seeded data, ran baseline tests, created `.env`.
- 2026-10-12: Chose OpenAI, verified key, ran first live conversation (order 4127).
