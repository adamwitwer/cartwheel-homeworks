# HW2 progress note

Working notes for the guided HW2 walkthrough (the prompt at the top of
`homework/module-1/hw2.md`). This file is not part of the submission. A new
session should read this first, then pick up at **Next step**.

## Current status

- **Walkthrough step:** done. HW2 complete; video recorded 2026-10-21
  (https://www.loom.com/share/fc8f18250378475eafb142546b64f58d).
- **Next step:** post the video and repo links in the course Discord submissions channel.
- **Start/stop Langfuse:** `docker compose -f observability/docker-compose.yml up -d` / `down`
  (Docker Desktop must be running). UI at http://localhost:3000,
  `student@example.com` / `cartwheel-dev-pass`. Traces persist across restarts.
- **Blockers:** none

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
- [x] Docker installed and the stack running (Docker Desktop 4.96.0, Langfuse 3.225.11)
- [x] At least 5 requests drawn from `hw1-session.jsonl`, each with a session
  for the matching user
- [x] Root span and tool span attributes checked in Langfuse (API by Claude; UI by me, run 2)
- [x] Allowed tool call: `permission_denied = false`, no reason
- [x] Denied tool call: `permission_denied = true` with reason (run 2)

Part F, prompt version comparison
- [x] Same request, same user, same model, fresh session, same database state
- [x] Current prompt vs the HW1 pre-revision prompt (before commit 5d9786c)
- [x] The two `cartwheel.prompt_version` values differ
- [x] Saved prompt restored and server restarted

Trace record and submission
- [x] `hw2-traces.json`: exactly two objects with `trace_id`, `permalink`,
  `prompt_version`, `user_role`, `user_id`, `tool_order`, `final_status` (chosen by me:
  run 2 merchant denial `b2a95bff…` and run 5b refund turn 2 `b99456c5…`; 6 spans each;
  `user_id` as a string, matching the trace)
- [x] Files committed: `observability/instrument.py`, `server/app.py`,
  `tests/test_observability.py`, `hw2-traces.json`
- [x] Video recorded (5 min or less), done by me (2026-10-21, Loom)
- [ ] Posted to the course Discord submissions channel, done by me

## Video checklist (5 minutes or less, one continuous recording)

Before recording: Docker Desktop running; `docker compose -f observability/docker-compose.yml up -d`;
sign in at http://localhost:3000; server in a second terminal:
`uv run uvicorn server.app:app --port 8010`. Do NOT run `docker compose ... down -v`.

Same order and wording as the handout's Video section.

1. **Run one authentication test.**
   `uv run pytest tests/test_observability.py -v` (2 passed).
2. **Read both selected traces from the root span to the final response.**
   Open each permalink in `hw2-traces.json`. Shape of both (6 spans):
   `cartwheel.session_message` (root: role, user_id, session_id, prompt_version, input
   message) -> Agent Workflow -> `cartwheel-support.agent` -> model call -> tool -> model
   call -> final reply (root output).
   - Trace 1, run 2, merchant 9002, "Show me order 4127." (`b2a95bff…`)
   - Trace 2, run 5b, shopper 1, "I ordered a different color" (`b99456c5…`)
3. **Explain how the endpoint established the authenticated identity.**
   `create_session` in `server/app.py`: looks the user up in the database (400 unknown
   role, 404 unknown user, 403 role mismatch), stores the AuthContext on the server in
   `_SESSIONS`, returns a signed token. On each message `_authorize` checks the token's
   signature and session before the agent runs; tools get the stored context, never
   anything typed in the chat. Point at the root span's `cartwheel.user_role` /
   `cartwheel.user_id` in the traces as the result. Optional live demo:
   `curl -s -X POST http://localhost:8010/sessions -H 'Content-Type: application/json' -d '{"user_id":1,"role":"support"}'` -> 403.
4. **Explain the tool calls and their results in the selected traces.**
   - Trace 1: `get_order(4127)` -> `permission_denied`, reason "role 'merchant' (user 9002)
     may not view order #4127"; tool span has `cartwheel.permission_denied = true`, the
     reason, and `store_id = 2`. No order data returned, so none could leak; the reply
     says the merchant lacks permission.
   - Trace 2: `issue_refund(order_id 4455, amount_usd 240, reason "Ordered a different
     color")` (the model reworded the user's reason) -> `status: queued_for_approval`,
     refund 575, note "amount is above the $100 auto-approval threshold; a human support
     agent will review it"; `permission_denied = false`.
     Turn 1 (trace 5a, `6a2f7d50…`) already called `get_order`; the session remembered it.
5. **Show the two prompt version hashes produced by the controlled comparison.**
   Show them in Langfuse: open each Part F trace (tabs ready before recording), click the
   root span `cartwheel.session_message`, point at `cartwheel.prompt_version`.
   - Run A, current prompt, `482b8f0da5c2`:
     http://localhost:3000/project/cartwheel-dev/traces/1ec21e6974fd759fad313933ecaa87ce
   - Run B, HW1 original prompt, `d108f6949e5e`:
     http://localhost:3000/project/cartwheel-dev/traces/4cd02e32efec280ba850837cf1e69077
   "Controlled": same request, user, model, new session, reset database; only the prompt
   changed. Optional one line: A offers a human, B does not (the ESC-2 edit).
   Terminal backup (prints both hashes from Langfuse):
   `for id in 1ec21e6974fd759fad313933ecaa87ce 4cd02e32efec280ba850837cf1e69077; do curl -s -u pk-lf-cartwheel-dev:sk-lf-cartwheel-dev http://localhost:3000/api/public/traces/$id | jq -r '"\(.id)  \(.metadata.attributes["cartwheel.prompt_version"])"'; done`
6. **Regenerate the span count for one selected trace.**
   `curl -s -u pk-lf-cartwheel-dev:sk-lf-cartwheel-dev http://localhost:3000/api/public/traces/b2a95bffeb4f90f52c1a55169a0f7626 | jq '.observations | length'` -> 6.

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
- 2026-10-20, Docker Desktop installed by me (Homebrew needs a password, so it must be
  run in a real terminal). Langfuse stack up; health OK; `.env` keys match the compose
  file's `pk-lf-cartwheel-dev` project. With Langfuse running, the known m2 test now
  fails differently: "Langfuse returned no traces for the Module 2 slice" (it passes
  alone). It needs Module 2 traces that do not exist yet; not caused by HW2 code.

### Part E runs, 2026-10-20 (live, gpt-4o-mini, prompt_version 482b8f0da5c2)

Database reset before run 1 and after run 5. Server: `uv run uvicorn server.app:app --port 8010`.

| Run | HW1 rec | Caller | Trace ID | Spans | Tools (in order) |
|---|---|---|---|---|---|
| 1 | 1 | shopper 1 | 667c9a99ec063246bd270fd27d5bb1a6 | 6 | get_order (allowed) |
| 2 | 4 | merchant 9002 | b2a95bffeb4f90f52c1a55169a0f7626 | 6 | get_order (DENIED: "role 'merchant' (user 9002) may not view order #4127") |
| 3 | 5 | support 9501 | 2ae2344da9ffc300a4e70aaaad33839a | 8 | find_order, check_return_eligibility |
| 4 | 9 | shopper 1 | 18220b81e3646a6de60e52c8db83a894 | 6 | search_products |
| 5a | 3 turn 1 | shopper 1 | 6a2f7d50a249b833628da45121711db1 | 6 | get_order |
| 5b | 3 turn 2 | shopper 1 | b99456c5b20a925b3005503bf2754f5d | 6 | issue_refund ($240, queued for approval) |

Run 5 used one session for both turns (session d35e93d4…); turn 2 relied on turn 1's history.
Each trace = one message. Simple trace shape (6 spans): cartwheel.session_message ->
Agent Workflow -> cartwheel-support.agent -> openai.response, tool, openai.response.

Observation (run 3, failure, candidate for HW4): support asked a hypothetical Juniper
lamp question. In HW1 (record 5) the agent searched the help center and correctly
cited Juniper's 14-day window. Here it called find_order("lamp"), picked order 8566
from Clover Field Naturals (a different store), and check_return_eligibility correctly
returned that store's platform-default 30 days. The agent answered "yes, 30 days" about
Juniper. Tools behaved correctly; the model grounded on an unrelated order (prompt
problem). It is the first time the model called check_return_eligibility unprompted.

### Part F, 2026-10-20 (live, gpt-4o-mini)

Request: HW1 record 7, shopper 1, "Can you change the email address on my Cartwheel
account to new@example.com?" New session per run, database reset before each run.
Prompts saved in `notes/hw2-part-f/` (`prompt-current.txt`, `prompt-hw1-original.txt`).
Swap: `git show 5d9786c -- agent/agent.py | git apply -R`; restore: `git checkout agent/agent.py`.

| Run | Prompt | prompt_version | Trace ID | Spans | Reply |
|---|---|---|---|---|---|
| A | current (with ESC-2 lines) | 482b8f0da5c2 | 1ec21e6974fd759fad313933ecaa87ce | 4 | offers to escalate to a human |
| B | HW1 original (5d9786c^) | d108f6949e5e | 4cd02e32efec280ba850837cf1e69077 | 4 | refuses, no human offered |

The old prompt's hash was predicted offline (`prompt_version()` on the swapped file)
before run B and matched. Restored afterwards: `agent/agent.py` matches the commit,
version 482b8f0da5c2, server restarted. No tools were called (4 spans: root, Agent
Workflow, agent, one model call).

Lesson: the first attempt at A and B (sessions c2903481…, a35d0013…) produced no traces.
The server exports spans in batches, and it was stopped seconds after each run, so the
pending batch was lost. Wait until the trace appears in Langfuse before stopping the
server (in the video too).
- `.sessions.db-shm` and `.sessions.db-wal` (SQLite side files of `.sessions.db`) show up
  as untracked; `.gitignore` covers only `.sessions.db`. Do not commit them.
- 2026-10-20, final checks before commit: supplied hw2 test 1 passed; test_observability
  2 passed; full suite with `LANGFUSE_*` blanked 161 passed, 4 skipped, 18 xfailed, 9 xpassed.
