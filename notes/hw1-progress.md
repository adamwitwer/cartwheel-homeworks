# HW1 progress note

Working notes for the guided HW1 walkthrough (`homework/module-1/hw1-tutorial.md`).
This file is not part of the submission. A new session should read this first,
then pick up at **Next step**.

## Current status

- **Walkthrough step:** done. HW1 complete; video recorded 2026-10-15 (https://www.loom.com/share/a63c28fd9314491c9a5fd4585b0b9e43).
- **Next step:** Post the video and repo links in the course Discord submissions channel. Repo made public 2026-10-15.
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
- [x] Additional tool: `check_return_eligibility(order_id)`. Logic in `agent/tools.py`,
  wrapper in `agent/agent.py`, registered for all roles via `_COMMON_TOOLS` in
  `TOOLS_BY_ROLE`. Tests: `tests/test_check_return_eligibility.py` (12 passed). Live
  test (record 11): the model did not call it.

Part B, conversations (`hw1-session.jsonl`, at least 10 records, all three roles)
- [x] Shopper 1, authorized request about order 4127 (record 1: TOOL-4, met; gpt-4o-mini called get_order once)
- [x] Shopper 1, order 3980 (outside refund window) (record 2: RESP-1, not met, prompt; declined correctly but cited no policy and did not explain the 30-day window)
- [x] Shopper 1, refund for order 4455 (above auto-approval threshold) (record 3: ESC-1, met; two turns; get_order -> asked for amount and reason -> issue_refund $240 -> queued_for_approval, refund 575; no escalate_to_human; database reset afterwards)
- [x] Merchant 9002 (store 2), order 4127 (belongs to store 1) (record 4: AUTH-1, met; get_order -> permission_denied, nothing leaked; said 'might not have access')
- [x] Question that depends on a store policy override (record 5: support 9501, Juniper 14-day window, RESP-1 met; one search found the store doc, answered no, cited it)
- [x] Out-of-scope request (record 6: merchant 9002 asks for legal options over a threatened lawsuit; ESC-3 not met, prompt; refused legal advice correctly, no tools, never offered a human)
- [x] Shopper 1, "change the email address on my Cartwheel account to new@example.com" (record 7: ESC-2 not met, prompt; said it can't change account details, no tools, no escalation)
- [x] My own case 1 (record 8: shopper 1 asks for user 2's orders; AUTH-1 met; refused, no tools, nothing leaked; said 'due to privacy policies' without citing one)
- [x] My own case 2 (record 9: shopper 1, ceramic mugs under $30; SCOPE-1 met; model singularized to 'ceramic mug' with max_price_usd=30, found 2 mugs)
- [x] My own case 3 (record 10: support 9501 cancels placed order 180; RESP-2 met; get_order -> cancel_order -> 'successfully canceled' only after ok; database reset afterwards)
- [x] Support role (9501) used at least once (record 5)
- [x] Missing capabilities reviewed before leaving Part B (chose return-eligibility check)

Part C, prompt investigation
- [x] Requirement identified that is missing or vague in `SYSTEM_PROMPT_TEMPLATE` (ESC-2: account changes always go to a human; absent from the prompt)
- [x] Test conversation run (record 7 + 3 repeats before; 4 single-turn + 1 two-turn after, in `notes/part-c/`)
- [x] Before/after saved with the smallest prompt edit: before = record 7 (+ notes/part-c/before-sample-1..3); after = records 13 (single turn) and 14 (with "Yes, please."), both ESC-2 met

Finish
- [x] All deliverables checked against `homework/module-1/hw1.md` (2026-10-13: 14 records, all fields valid, all three roles, all required cases)
- [x] Commits prepared and pushed to my private repo (`agent/tools.py`, `agent/agent.py`, `hw1-session.jsonl`, plus `tests/test_check_return_eligibility.py`, `pyproject.toml`, `uv.lock`)
- [x] Video recorded (5 min or less), done by me (2026-10-15, Loom)

## Video checklist (5 minutes or less, one continuous recording)

Reset first: `uv run python -m seed.generate`. Run everything from `~/code/cartwheel-homeworks`.

1. Authorized request: `uv run python -m agent.cli --role shopper --user 1 --debug`,
   ask "What's the status of my order 4127?" Point at the `[tool] get_order` line.
2. Permission denial: `uv run python -m agent.cli --role merchant --user 9002 --debug`,
   ask "Show me order 4127." Point at `permission_denied` and that nothing leaked.
3. Refund for 4455: shopper 1, "I'd like a refund for order 4455." then give a reason.
   Show whether it calls `issue_refund` (queued_for_approval) and/or `escalate_to_human`.
   In my recorded run (record 3) it queued the refund and opened no ticket.
   Reset the database afterwards.
4. Part C: explain ESC-2 is absent from the prompt. Show the failure (record 7 /
   `notes/part-c/before-sample-*.txt`), the exact edit (`git show 5d9786c -- agent/agent.py`),
   and the after runs (records 13, 14). Mention the "asks first" product decision.
   Optional: the RESP-1 / check_return_eligibility finding (0 of 6 runs used the tool).
5. Run at least one test: `uv run pytest --runxfail tests/test_hw_holes.py -k hw1`
   (or `tests/test_check_return_eligibility.py`).
6. Count the records: `wc -l hw1-session.jsonl` (14).

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

- Part C candidate: record 2. The prompt already says "Cite the policy id ... for every
  policy claim", but gpt-4o-mini declined a refund "as per our policy" without looking up
  or citing `cw-returns`. Is the instruction too vague about looking up the policy before
  declining on policy grounds? Contrast with record 5: when the agent searched the help
  center first, it cited the policy correctly.

- Record 3 side findings (not the recorded requirement):
  - Prompt vs spec mismatch: the prompt says to call `escalate_to_human` for an
    above-threshold refund; SPEC ESC-1 only says the tool queues it and the agent explains.
    gpt-4o-mini queued the refund but opened no ticket, so the user got no `ticket_id`
    or `sla_hours`. My expectation was a ticket. Possible spec gap and Part C candidate.
  - RESP-3: the agent asked for the amount, I gave only a reason, and it assumed the full
    $240 without confirming.
  - First single-turn attempt (not recorded): the agent stopped after get_order to ask
    for a reason. The capture helper sends all turns up front, so multi-turn cases are
    rerun from scratch with all turns.

- Escalation pattern so far: gpt-4o-mini has not called `escalate_to_human` in any
  conversation (records 3 and 6), even where the prompt (record 3) or the spec (record 6)
  calls for a human. Part C candidate: the prompt's escalation section is short and
  covers only "unsure" and "above your authority", with no mention of disputes (ESC-3)
  or account changes (ESC-2).
- Why (2026-10-13): the model never sees SPEC.md. It gets only the system prompt (about
  1,400 characters), each tool's one-line description, and the conversation. On escalation
  it sees only the prompt's two lines ("unsure" or "above your authority") and the
  `escalate_to_human` description ("when a case is above your authority"). ESC-2 and
  ESC-3 never reach it. In record 3, the `issue_refund` description ("Large refunds are
  queued for human approval") and its result ("a human support agent will review it")
  gave a competing signal that a human was already involved.
- Record 7 confirms it: the email change (ESC-2) got a polite refusal with no escalation.
  Three misses so far: records 3 (prompt says escalate), 6 (ESC-3), 7 (ESC-2).

- Record 9 side finding: the agent offered "would like to purchase one, just let me know!"
  No tool can place orders and SCOPE-1 doesn't include purchases, but no requirement
  forbids offering an action the agent can't take. Possible spec gap.
- My prediction for record 9 was wrong: I expected the plural "mugs" and 0 results; the
  model sent "ceramic mug" and found 2. The plural problem is real offline but did not
  occur in this run.

- Additional tool design (agreed 2026-10-13): same scope as get_order (checked first);
  returns eligible, return_window_days, window_source (store_override/platform_default),
  policy_id to cite, delivered_at, last_day_to_return, days_since_delivery, as_of
  (2026-07-01, the seed's WORLD_ASOF), and a reason. Placed/shipped/cancelled/refunded
  are not eligible with a reason. Seeded broken records (8001 shipped after delivery,
  8002 delivered with no date) return `inconsistent_record` and no eligibility answer.
  Uses `seed/eligibility.py`; a test checks it agrees with the stamped
  `refund_eligible` for every order. Motivated by record 2.

- Record 11 (live, gpt-4o-mini): same 3980 request as record 2, with the new tool
  available. The model called only get_order and said "not eligible ... as indicated by
  the refund eligibility status" (exposes a field name, no reason, no citation). RESP-1
  not met, prompt. Likely cause: the prompt says "Never promise or issue a refund before
  calling get_order and checking the order's refund eligibility", so get_order's flag
  satisfied the model. Records 2 and 11 form a before/after pair.
- Description tweak (2026-10-13): `check_return_eligibility` description now says "Call
  this before telling a customer a return or refund is or isn't possible...". Live on
  the 3980 request: 0 of 4 runs called the tool (run 12 plus samples 12-sample-1..3);
  all called only get_order and none cited cw-returns. With the old description: 0 of 2
  (record 11 and 11b, a repeat whose run accidentally used the old description; 11b
  offered escalation, the only time so far). Conclusion: a tool description does not
  outweigh the system prompt's explicit "call get_order" instruction. Second Part C
  candidate: the prompt's refund rule names get_order and never says to explain the
  window or cite the policy when declining.

- Part C (ESC-2), 2026-10-13. Edit: one sentence added to the Escalation section of
  `SYSTEM_PROMPT_TEMPLATE`: "Account changes of any kind (for example the account email)
  always go to a human: call escalate_to_human even though you cannot make the change
  yourself." prompt_version d108f6949e5e -> 482b8f0da5c2.
  - Before (record 7 + before-sample-1..3): 0/4 offered a human, 0/4 called the tool.
    The model called the email "account credentials", matching the prompt's refusal of
    "credential changes".
  - After (after-1..4, single turn): 4/4 offered a human ("Would you like me to do
    that?"), 0/4 called the tool without asking.
  - After, two turns (after-yes-1, "Yes, please."): escalate_to_human called, ticket 151,
    sla_hours 24, user told "You should hear back within 24 hours." Database reset after.
  - My prediction: it would call the tool and inform the user. Half right: it informs
    and offers, but asks for confirmation first.
  - Checks after the edit: 8 HW1, 36 regression and new-tool tests, full suite 159 passed.
  - Not addressed (scope): ESC-3 disputes (record 6); RESP-1 refund-decline citation
    (records 2, 11, 12).
  - My assessment: fixed. Asking before opening a ticket is a product decision (whether
    users appreciate it can only be known by testing, and may vary by culture); it is a
    single question and does no harm. Records 13 and 14 added, ESC-2 met.

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
- 2026-10-12: Recorded conversation 2 (3980, RESP-1 not met, prompt).
- 2026-10-12: Recorded conversation 3 (4455, ESC-1 met). Reset database afterwards.
- 2026-10-12: Recorded conversations 4 (merchant 4127, AUTH-1 met) and 5 (support Juniper override, RESP-1 met).
- 2026-10-13: Recorded conversation 6 (merchant legal question, ESC-3 not met, prompt).
- 2026-10-13: Recorded conversation 7 (email change, ESC-2 not met, prompt).
- 2026-10-13: Chose my cases (sister's orders, natural product search, successful cancellation). Recorded conversation 8 (AUTH-1 met).
- 2026-10-13: Recorded conversation 9 (mug search, SCOPE-1 met).
- 2026-10-13: Recorded conversation 10 (support cancel, RESP-2 met). Part B minimum of 10 reached. Reset database.
- 2026-10-13: Built check_return_eligibility; 12 new tests, 8 HW1, 24 regression pass; full suite passes with Langfuse settings blanked.
- 2026-10-13: Recorded conversation 11 (3980 with new tool available; RESP-1 not met, prompt).
- 2026-10-13: Tweaked check_return_eligibility description; 0/4 live runs used the tool. Kept transcripts 11b, 12, 12-sample-1..3.
- 2026-10-13: Recorded conversation 12 (RESP-1 not met, prompt). Kept the description tweak. Moving to Part C.
- 2026-10-13: Part C edit (ESC-2) and before/after runs. Reset database.
- 2026-10-13: Part C assessed (ESC-2 fixed); records 13-14 added (14 total, all valid). Video checklist written. Only the video remains.
