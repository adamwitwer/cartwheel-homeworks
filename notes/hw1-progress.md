# HW1 progress note

Working notes for the guided HW1 walkthrough (`homework/module-1/hw1-tutorial.md`).
This file is not part of the submission. A new session should read this first,
then pick up at **Next step**.

## Current status

- **Walkthrough step:** 1, Get oriented (checkpoint pending)
- **Next step:** Confirm the repo/spec/agent relationship is clear, then Step 2:
  install `uv`, run `uv sync`, generate data, create `.env`, run the first
  conversation (shopper 1, order 4127).
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
- Python 3.12 is available from Homebrew. `uv` is not installed yet.
- `.env` does not exist yet. The model provider is not chosen yet.
- Pushing to `main` runs the offline-checks GitHub Action (no keys needed).

## Missing capabilities seen (candidates for the additional tool)

- (none yet)

## Log

- 2026-10-08: Created private repo, rewired remotes, started the walkthrough.
