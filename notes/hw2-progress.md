# HW2 progress note

Working notes for the guided HW2 walkthrough (the prompt at the top of
`homework/module-1/hw2.md`). This file is not part of the submission. A new
session should read this first, then pick up at **Next step**.

## Current status

- **Walkthrough step:** 5, Parts A to D done and committed.
- **Next step:** Part E: install Docker Desktop (`brew install --cask docker`, chosen
  2026-10-20; waiting until I'm on my home network), open it once, then start Langfuse.
- **Blockers:** Docker is not installed on this machine (needed for Part E only).

## Deliverables checklist

Part A, tool span attributes (`observability/instrument.py`)
- [x] `record_tool_result`: `cartwheel.user_role`, `cartwheel.user_id` (string),
  `cartwheel.store_id` (string, merchants only)
- [x] `_set_permission_denied_attributes`: `cartwheel.permission_denied` (bool),
  `cartwheel.permission_denied.reason` when denied

Part B, session creation (`server/app.py`)
- [x] `create_session`: 400 unknown role, 404 unknown user, 403 role mismatch,
  AuthContext from the database, stored in `_SESSIONS`, signed token with
  `session_id`, `user_id`, `role`, `store_id`, `issued_at`
- [x] `uv run pytest --runxfail -vv tests/test_hw_holes.py -k "create_session_binds"` passes

Part C, traced message endpoint (`server/app.py`)
- [x] `post_message`: authorize, recover session, prompt version from the template hash
- [x] Root span `cartwheel.session_message` with `cartwheel.user_role`, `cartwheel.user_id`,
  `cartwheel.prompt_version`, `cartwheel.scenario_id` (when nonempty),
  `gen_ai.input.messages`, `gen_ai.output.messages`
- [x] Returns session id, reply, prompt version
- [x] Decided (2026-10-19, with me): also record `cartwheel.session_id` (Module 2's
  `analysis/helpers/normalization.py` reads it) and record the two message attributes
  only when `TRACELOOP_TRACE_CONTENT=true`, as the docstring says. Response key `reply`
  (HW3 `scenarios/runner.py` reads it).

Part D, authentication tests (`tests/test_observability.py`)
- [x] Test: role mismatch rejected at session creation
- [x] Test: token for one session cannot authorize another
- [x] No Langfuse, Docker, or model key needed by the tests
- [x] `uv run pytest --runxfail tests/test_hw_holes.py -k hw2` passes
- [x] `uv run pytest tests/test_observability.py` passes
- [x] `uv run pytest` (full suite) passes with `LANGFUSE_*` blanked (161 passed, 4 skipped,
  18 xfailed, 9 xpassed); with `.env` as is, 1 known failure (m2 prevalence test needs
  Langfuse running), same as HW1

Part E, live traces (Docker + Langfuse at http://localhost:3000)
- [ ] Docker installed and the stack running
- [ ] At least 5 requests drawn from `hw1-session.jsonl`, each with a session
  for the matching user
- [ ] Root span and tool span attributes checked in Langfuse
- [ ] Allowed tool call: `permission_denied = false`, no reason

Part F, prompt version comparison
- [ ] Same request, same user, same model, fresh session, same database state
- [ ] Current prompt vs the HW1 pre-revision prompt (before commit 5d9786c)
- [ ] The two `cartwheel.prompt_version` values differ
- [ ] Saved prompt restored and server restarted

Trace record and submission
- [ ] `hw2-traces.json`: exactly two objects with `trace_id`, `permalink`,
  `prompt_version`, `user_role`, `user_id`, `tool_order`, `final_status`
- [ ] Files committed: `observability/instrument.py`, `server/app.py`,
  `tests/test_observability.py`, `hw2-traces.json`
- [ ] Video recorded (5 min or less), done by me
- [ ] Posted to the course Discord submissions channel, done by me

## Setup facts (this machine)

- Repo at `~/code/cartwheel-homeworks`, up to date with the course repo as of
  2026-10-19 (course HEAD a3aa8d5 is in local history). No `upstream` remote on this
  machine; the course repo is `https://github.com/ai-evals-course/cartwheel-homeworks`.
- `uv` 0.13.1, `jq`, `git-lfs` from Homebrew; `uv sync` done; Python 3.12.14.
- `.env` from `.env.example`: `CARTWHEEL_MODEL=gpt-4o-mini`, the three `LANGFUSE_*`
  values, `TRACELOOP_TRACE_CONTENT=true`. OpenAI key added by me.
- Repo is public (since 2026-10-15).

## Observations

- 2026-10-19, Part A, offline check (in-memory spans, no Langfuse, no model):
  shopper 1 success -> role/user_id set, permission_denied False, no reason;
  merchant 9002 denial -> store_id "2", permission_denied True, reason recorded;
  non-dict result -> False, no crash; call outside a span -> silent no-op.
  HW1 tests still pass (8 focused, 36 regression incl. check_return_eligibility).
  The course repo has no supplied test for Part A; live check is in Part E.
- 2026-10-19, Part B: supplied test passes (offline). Offline TestClient check:
  user 1 shopper -> 200 (token: user 1, shopper, store None); role "admin" -> 400;
  user 999999 -> 404; user 1 claiming support -> 403.
- The HW3 scenario runner (`scenarios/runner.py`) reads `session_id` and `token` from
  POST /sessions and `reply` from the message endpoint, so keep those key names.
- Copied-over `__pycache__` dirs made pytest show an old ~/Desktop path; deleted them
  (gitignored, regenerated). Imports always came from ~/code/cartwheel-homeworks.
- 2026-10-19, Part C offline check (model keys hidden, in-memory spans): no token ->
  401; tampered token -> 401; session A's token on session B -> 403; A's token on A
  reached the agent and failed with openai OpenAIError "Missing credentials" (500), as
  expected without a key. Root span had session_id, user_role shopper, user_id "1",
  prompt_version, scenario_id, input message; no output message because the run failed.
- Current prompt version (HW1 ESC-2 prompt): `482b8f0da5c2`. The pre-ESC-2 agent.py
  (5d9786c^) is saved in the Claude scratchpad for Part F; it can be regenerated with
  `git show 5d9786c^:agent/agent.py`.
- 2026-10-20, Part D: `tests/test_observability.py` (2 tests) passes offline.
  Mutation check: with the session-match check removed from `_authorize` (in memory
  only, via a scratch pytest plugin), the token test fails because the shopper's token
  runs the agent in the merchant's session. The role test does not depend on that check.
