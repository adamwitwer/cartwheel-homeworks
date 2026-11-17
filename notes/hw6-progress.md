# HW6 progress (CI for agent evaluations)

Handout: `homework/module-3/hw6.md`. A new session should read this first, then pick up at
**Next step**.

## Ground rules

- Guided walkthrough, one part at a time: Claude explains each step and waits for my "go"
  before running commands, changing files, or spending money.
- Before any paid run, Claude shows the model, tasks, agent runs, and judge calls, and waits
  for my approval.
- The classifications (regression or capability, from five baseline runs) and the video are
  mine. Never change a classification to get the required mix; add cases instead.
- Use the supplied adapters: `scripts/export_harbor_tasks.py` generates `.harbor/tasks`. Never
  hand-write or commit `.harbor/tasks` or `.harbor/jobs`.
- Keep the Cartwheel case and judge formats. Code checks for exact facts; for language, only
  my accepted HW5 judge, with its frozen prompt, model, and parser unchanged.
- API keys stay in `.env` (local) and GitHub repository secrets (CI). Never print or commit
  them. The repo is public.
- Don't open `homework/module-3/hw6-reference.patch` (same rule as HW4's reference patch).
- Keep HW4 and HW5 files unchanged.

## Decisions

- **Agent model (2026-11-16):** `gpt-4o-mini`, the HW3 and HW4 model (`CARTWHEEL_MODEL` in
  `.env`). The same model for the baseline, CI, and Part E.
- **Accepted judge (2026-11-16):** `policy_claim_without_citation-v3` (the frozen v0 prompt on
  `claude-opus-4-7`; HW5 test 1.0 / 1.0). Not v0 (`gpt-4o-mini`), which I would not use. The
  adapter's `load_frozen_judge` picks the highest frozen version, which is v3. About $0.035 per
  judge call; needs `ANTHROPIC_API_KEY`.
- **Failure modes (2026-11-16):**
  - `required_action_not_taken` (11 HW4 Fails): code checks only (`refund_status`,
    `tool_called escalate_to_human`).
  - `policy_claim_without_citation` (39 HW4 Fails): a code check for the policy id where the
    reply must state a policy rule, plus the v3 judge.
- **Branching:** Parts A to C on `main`; Part D on a branch with one pull request for both CI
  runs.

## Current status

- **Step 0 done (2026-11-16, on the MacBook Air):** Docker Desktop started (29.9.1, 10 CPUs,
  about 8 GB for Docker). `uv sync`; `uv tool install 'harbor==0.23.0'` (`harbor` at
  `~/.local/bin/harbor`). No `git lfs pull` or reference patch (HW5 is done).
  - GitHub (`adamwitwer/cartwheel-homeworks`, public): no Actions secrets or variables yet.
    Part C needs the `CARTWHEEL_MODEL` variable and the `OPENAI_API_KEY` and
    `ANTHROPIC_API_KEY` secrets.
  - Offline suite (the workflow's offline job, keys unset): 83 passed, 2 failed. Expected:
    `test_m2_failure_report_matches_artifact_l_schema` (demo-mode check since HW4 Part D).
    Order-dependent: `test_m2_run_judge_persists_store_predictions_for_prevalence` passes alone
    and in `tests/test_hw_holes.py` alone, but fails in the full suite (397 store traces, my
    local Langfuse export, instead of 500). Not HW6; watch whether it fails in CI.
- **Watch:**
  - Judge input: the Harbor verifier formats the trace with `replay.rollout.judge_trace_text`:
    `tool_call: {args}` and `tool_result: {result}` without the tool name. My HW5 inputs kept the
    tool name inside each tool message. Same prompt, model, wrapper, and parser; the trace text
    differs slightly. The citation check concerns ids in the final reply, so the effect should
    be small. Kept as supplied (the handout says to use the supplied adapter).
  - Narration: in the Harbor transcript a turn's `reply` (and `final_reply`) is all of the
    agent's text in that turn, including pre-tool narration ("Let me look up your orders..."),
    so both `reply_contains` and the judge see it. My HW5 inputs left narration out (D3).

## Fix to the supplied adapter (2026-11-16)

Harbor 0.23.0 writes the job-level `result.json` without `trial_results` (it always passes
`exclude_trial_results=True`, `harbor/job.py:1103`), but `harbor_adapter/summary.py` and
`harbor_adapter/analysis.py` read only that list. The summary found no trials ("no baseline
trials matched a case"), and the Part E analyzer would have refused to run; the supplied tests
passed only because they write a `result.json` that includes the list. Fix: a shared
`load_trial_results` in `summary.py` uses `trial_results` when present (old behavior
unchanged) and otherwise reads each trial directory's `result.json`, ordered by `started_at`
then trial name; the Part E file records that order in `trial_order`. Two offline tests cover
the Harbor 0.23.0 layout. Checks, rewards, and classification rules are unchanged. Worth
reporting in the course Discord.

## Part A

- **Cases approved and committed (2026-11-16, 853f4c8):** 12 cases, none classified yet. The
  reseeded Harbor world is byte-identical to `data/cartwheel.db` (same dump hash), and the agent
  prompt version is unchanged since HW3 (`482b8f0da5c2`).

  | id | Mode | HW4 source | Check(s) |
  |---|---|---|---|
  | e-001 | required_action_not_taken | 0056 (Fail; follow-up dropped) | refund 5858 `auto_approved` |
  | e-002 | required_action_not_taken | 0243 T2 (Fail) | refund 1980 `auto_approved` |
  | e-003 | required_action_not_taken | 0156 (Fail) | `escalate_to_human` called |
  | e-004 | required_action_not_taken | 0180 (Fail) | `escalate_to_human`; no refund row 8001 |
  | e-005 | required_action_not_taken | 0072 (Pass) | refund 246 `auto_approved` |
  | e-006 | required_action_not_taken | 0079 (Pass) | refund 296 `queued_for_approval` |
  | e-007 | required_action_not_taken | 0252 (Pass) | `escalate_to_human` called |
  | e-008 | policy_claim_without_citation | 0121 (Fail) | reply contains `cw-escalations`; v3 judge Pass |
  | e-009 | policy_claim_without_citation | 0101 (Fail) | reply contains `cw-cancellations`; v3 judge Pass |
  | e-010 | policy_claim_without_citation | 0115 (Fail) | reply contains `cw-roles`; v3 judge Pass |
  | e-011 | policy_claim_without_citation | 0111 (Pass) | reply contains `cw-payouts`; v3 judge Pass |
  | e-012 | policy_claim_without_citation | 0117 (Pass) | reply contains `cw-cancellations`; v3 judge Pass |

- **Baselines (approved 2026-11-16):** 60 `gpt-4o-mini` runs and 25 judge calls (about $1), one
  Harbor job per case (`hw6-baseline-e-0XX`), `--yes` (no `--upload`; nothing goes to Harbor Hub).
  - e-001: 0/5, no exceptions. Two trials found 5858 and asked to confirm the amount or reason
    (the HW4 failure); three used `list_my_orders`, missed 5858, and said no order matched.

## Next step

Finish the e-002 to e-012 baselines, summarize them, and record each classification (mine).

## Deliverables checklist

- [ ] `eval_cases/cases.jsonl`: 10+ cases, 2+ HW4 modes, each classified from five baseline runs
- [ ] At least one regression and one capability case
- [ ] `tests/eval/passk.py`: `pass_at_k`, `pass_hat_k`, `case_passes` (3 focused tests pass)
- [ ] `.github/workflows/evals.yml`: Harbor job, summary and artifact with `if: always()`
- [ ] `ci-runs.json`: two runs from one pull request (regression, then revert)
- [ ] `eval_results/<case-id>-15.json`: one capability case, 15 runs
- [ ] Video (5 minutes or less; mine)
