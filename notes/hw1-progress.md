# HW1 progress note

Working notes for the guided HW1 walkthrough (`homework/module-1/hw1-tutorial.md`).
This file is not part of the submission. A new session should read this first,
then pick up at **Next step**.

## Current status

- **Walkthrough step:** 4, Part B conversations (1 of 10+ recorded)
- **Next step:** Conversation 2, required case: shopper 1, order 3980 (outside the
  refund window). Ask for my prediction first.
- **How to record:** `uv run python notes/part-b/capture.py NAME --role R --user U "turn" ...`
  runs the CLI live with --debug and saves `notes/part-b/NAME.txt` + `.json`. After my
  assessment, `uv run python notes/part-b/record.py NAME --expected ... --requirement ...
  --met true|false --source null|prompt|tool|specification` appends to `hw1-session.jsonl`.
  Reset the database (`uv run python -m seed.generate`) before any conversation that
  could refund or cancel, never mid-conversation.
- **Repo location:** moved to `~/code/cartwheel-homeworks` on 2026-10-12, away from
  iCloud-synced `~/Desktop`. Run Claude Code from there.
- **Blockers:** none

## Deliverables checklist

Part A, tools (`agent/tools.py`)
- [x] `get_policy`
- [x] `search_products`
- [x] `list_my_orders`
- [x] `cancel_order`
- [x] `find_order` (rapidfuzz partial_ratio, cutoff 70)
- [x] Focused tests pass: `uv run pytest --runxfail tests/test_hw_holes.py -k hw1` (8 passed, 2026-10-12)
- [x] Regression tests pass (24 passed, 2026-10-12): `uv run pytest tests/test_agent_tools.py tests/test_auth.py tests/test_eligibility.py`
- [ ] At least one additional tool of my own, registered in `TOOLS_BY_ROLE` and tested (pending: pick it from gaps seen in Part B)

Part B, conversations (`hw1-session.jsonl`, at least 10 records, all three roles)
- [x] Shopper 1, authorized request about order 4127 (record 1: TOOL-4, met; gpt-4o-mini called get_order once)
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
- `.env` created from `.env.example` (gitignored). Provider: OpenAI, `CARTWHEEL_MODEL=gpt-4o-mini` (was gpt-5.5); key verified 2026-10-12.
- `rapidfuzz` added as a dependency (`pyproject.toml`, `uv.lock`) for `find_order`.
- Full `uv run pytest` with `.env` present: 1 failure,
  `test_m2_run_judge_persists_store_predictions_for_prevalence`, because `.env` sets
  `LANGFUSE_*` and Langfuse is not running (HW2), so the test tries a live call.
  The same failure happens on the untouched starter. Not caused by HW1 code. With
  `LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY= LANGFUSE_HOST=` the suite passes
  (147 passed, 19 xfailed, 8 xpassed).
- Pushing to `main` runs the offline-checks GitHub Action (no keys needed).
  Every run failed at checkout until 2026-10-12: the workflow checks out Git LFS files
  (three `*-reference.patch` handouts), but `git-lfs` was not installed locally, so the
  first push sent only LFS pointers. Fix: `brew install git-lfs`, `git lfs install
  --local`, `git lfs fetch upstream --all`, `git lfs push origin --all`. Rerun of
  run 38323618979 passed. The Node.js 20 and ubuntu-latest annotations are warnings only.
- Course update on upstream (2026-10-10, PR #65): the agent should run on a small model
  (default now `gpt-4o-mini`), because frontier models like `gpt-5.5` rarely fail in
  this synthetic world, and Part C depends on failures. Merged 2026-10-12; `.env` now
  has `CARTWHEEL_MODEL=gpt-4o-mini` (verified available). The first 4127 conversation
  above ran on gpt-5.5; Part B records use gpt-4o-mini.

## Missing capabilities seen (candidates for the additional tool)

- `search_products` keyword matching is literal: "ceramic mugs" (plural) returns 0
  even with `max_price_usd=30`, while "ceramic mug" returns 2. Tool or model problem? Watch in Part B.

## Observations

- 2026-10-12, live (gpt-5.5), shopper 1, "What's the status of my order 4127?":
  one call `get_order(4127)` -> delivered 2026-06-19, $84.00, Blue Heron Ceramics,
  refund_eligible true. Response listed status, dates, total, refund eligibility.
  No visible explanation text before the tool call, though the prompt asks for one.
  My prediction: get_order, status and delivery date. Pre-Part A; not a Part B record.

- Design decisions so far: `get_policy` exact-match only, the agent should search first
  (not_found reason points to `search_help_center`). `cancel_order` checks scope
  before status so an out-of-scope caller learns nothing about the order.
- Part B case idea: shopper 1, "I'm helping my sister. Show me all the orders for
  user 2." Good: decline. Bad: present user 1's own orders as the sister's.
- Shopper 1 has no `placed` orders (24 delivered, 1 cancelled, 1 refunded), so a
  successful cancel needs a different user. Database has 35 `placed` orders in total.

- `find_order` at cutoff 60 (offline, shopper 1): "vase" -> 4455, 4127, 3980 (Heavy-Duty
  Vase), 2485 (Matte Vase). "gardening gloves" -> Midnight Garden Gloves (90) plus a
  false positive, Walnut Trekking Poles (62). "that novel" -> both novels plus a false
  positive, Travel Pitcher (62). "the vase I bought in June" -> Heavy-Duty Vase scores
  61, below the false positives, so no single cutoff separates them.
- Decision: cutoff raised to 70. Results: "gardening gloves" -> 5322 only; "that novel"
  -> 1440, 7310; "the vase I bought in June" -> 2485 only (misses 4127; the model must
  send short product words). Watch in Part B whether the model shortens queries.
- iCloud "Desktop & Documents" sync created 18 duplicate policy files
  (`data/policies/* 2.md`, identical to originals). The agent loaded them (36 docs, 18
  unique), so `search_help_center` returned `cw-returns` twice. Removed them and moved
  the repo off the Desktop.

## Log

- 2026-10-08: Created private repo, rewired remotes, started the walkthrough.
- 2026-10-12: Step 1 done. Installed uv, synced deps, seeded data, ran baseline tests, created `.env`.
- 2026-10-12: Chose OpenAI, verified key, ran first live conversation (order 4127).
- 2026-10-12: Implemented get_policy, search_products, list_my_orders, cancel_order; 4 focused tests pass.
- 2026-10-12: Implemented find_order (rapidfuzz, cutoff 60). All 8 HW1 tests and 24 regression tests pass. Found iCloud duplicates.
- 2026-10-12: Cutoff 70 (8 HW1 + 24 regression tests pass). Removed iCloud duplicates; moved repo to ~/code.
- 2026-10-12: Fixed CI (Git LFS objects missing on private repo). Found upstream small-model update.
- 2026-10-12: Merged upstream small-model update; switched to gpt-4o-mini. Tests still pass.
- 2026-10-12: Step 3 checkpoint done. Built capture/record helpers. Recorded conversation 1 (4127, met).
