# HW4 progress note

Working notes for the guided HW4 walkthrough (the prompt at the top of
`homework/module-2/hw4.md`). This file is not part of the submission. A new
session should read this first, then pick up at **Next step**.

Rules from the walkthrough prompt, `AGENTS.md`, and the handout that apply throughout:
- One step at a time, in the handout's order. No commands, file changes, or generated
  content without my go. Explain error-analysis concepts in depth; infrastructure is a
  checklist. The video is mine.
- I do the noticing: open codes, accept/reject decisions, final labels. Claude organizes,
  proposes groupings and searches, and records. AI suggestions stay separate from my
  annotations until I accept them.
- Open coding: read each trace (conversation + retrieval + tool calls/results) until the
  first failure, write a free-form note with its evidence, stop. No formal mode names
  during the initial reading. "No failure observed" when there is none.
- Check `SPEC.md` before calling something a failure; record the requirement id in every
  mode derived from one. A desirable behavior SPEC.md doesn't require: record the gap,
  decide the behavior, revise SPEC.md, before labeling.
- Don't select traces only because a model or heuristic predicts a failure. No trace
  counts toward more than one batch.
- Don't open `homework/module-2/hw4-reference.patch` (likely a reference solution; it
  would bias my taxonomy).
- Langfuse data lives only on the larger-screen Mac. Do all Langfuse work there.

## Current status

- **Step 0 done (2026-11-02):** repo at 65ff649, Docker and Langfuse up. Langfuse has 397
  traces: 356 final (250 scenarios) + 41 pilot (30 scenarios); 0 scores. The supplied
  loader (`analysis/helpers/langfuse_io.fetch_traces`) keeps every trace with
  `cartwheel.scenario_id`, so it would include the pilot traces unless filtered.
- **Part A friction recorded (2026-11-02)**, see below. Claude inspected the same 11 traces
  (6 conversations); I approved the proposed layout.
- **Decisions (2026-11-02):**
  - Review pool: final traces only (`support-` scenarios, 356 traces); pilot excluded.
  - Answer key collapsed by default, one click to reveal (read first, then compare).
  - Labels per trace (per turn), displayed grouped by conversation. "100 distinct traces"
    counts turns.
  - No map view; cluster samples for batch 1 are chosen by a script.
  - Theme: "Ocean Drive at sunset" (Miami palette, cream reading surface, no game branding).
- **Review app built and committed (2026-11-02); I clicked through it, works well.**
  Night-mode highlight contrast fixed after my check. `analysis/review_app/` (server.py,
  data.py, store.py, static/). Smoke-tested against a scratch state directory with
  `--local-labels`: live load of 356 traces / 250 conversations, annotate by selection,
  edit, no-failure marking, label set/flip, accept/reject suggestions (rejected kept),
  drawer tabs, all four views, night theme, no console errors. Afterwards: 0 Langfuse
  scores, `analysis/state/` unchanged, tests same as baseline.
- **Demo files: resolved, nothing moved.** The demo `annotations.json`,
  `patterns.json`, and `suggestions.json` are empty, so my files take those paths. The
  files the course tests need (`labels/unsupported_policy_claim.jsonl`, `judges/`,
  `splits.json`, `store_traces.json`) have names that don't collide with mine.
  Watch: `test_m2_failure_report_matches_artifact_l_schema` skips while
  `patterns.json` has no modes and expects the demo mode once it has modes, so it may
  start failing in Part D.
- **Facts for later (from building the app, not yet reviewed by me):**
  `check_return_eligibility` has no SPEC.md tool contract; 5 conversations cite a policy
  never retrieved in them; two cited ids aren't in the corpus (`cw-orders`,
  `cw-cancellation`).
- **Next step:** Part B batch 1. Claude proposes the 15 uniform + 15
  cluster-representative selection (features, clustering, seed) and waits for my go
  before writing `analysis/state/sample_manifest.json`. Run the app with
  `uv run python -m analysis.review_app.server` (port 8030).
- **Still to write later:** `analysis/report/interface_comparison.md` (candidates: kept
  the reference's margin notes and tool call/result grouping; changed to session grouping
  plus the context drawer; limitation: labels need Langfuse unless `--local-labels`).
- **Open decisions:**
  - Part C (Raindrop Workshop) is optional: decide after Part B.
- **Baseline tests (2026-11-02, before any HW4 code):** 160 passed, 1 failed, 4 skipped,
  18 xfailed, 9 xpassed. The failure,
  `test_m2_run_judge_persists_store_predictions_for_prevalence`, passes alone and fails
  only in the full run (order-dependent, pre-existing).
- **Blockers:** none.

## Part A friction (my notes from the standard Langfuse view, 2026-11-02)

Final traces only (pilot excluded). Copied verbatim from my notes:

> I value seeing the exchange between agent and customer in plain English, without having to parse JSON files. I value being able easily find and view the prompt. I value being easily to view the spec, policies, and tools. Output from tool calls is invaluable.
>
> 0101 – Had to go outside Langfuse three times: for the system prompt, the answer key and the policy text. A review view could put these beside the trace:
>
> - the scenario's expected outcome and source
> - a clear "no tools called / no retrieval" marker at the top of the trace
> - for each policy id the response cites, whether it was retrieved in this trace, plus the policy text
>
> 0111 - Had to look outside of Langfuse to confirm the policy the agent cited.
>
> 0078 - Had to hunt for user role.
>
> 0008 - It's difficult to look at different traces for each turn. Can they be consolidated into a single view?
>
> 0040 - In the first turn, I struggled to find how the agent determined the item is not eligible to be returned.
>
> 0192 - Seems straightforward. Easy to see what the agent got as a response from the tool call, which is always helpful.

## Deliverables checklist

Part A, review interface
- [ ] 5-10 traces reviewed in the standard Langfuse view; friction recorded (me)
- [ ] Claude inspects 5-10 traces, describes the fields, proposes a visual organization;
  approved by me before any code
- [ ] Interface built under `analysis/review_app/`, with:
  - [ ] conversations grouped by `cartwheel.session_id`, turns in order, with retrieval
    results, tool calls, and tool results
  - [ ] free-form annotations beside the trace content
  - [ ] taxonomy view with supporting annotations
  - [ ] structured labeling view (present/absent per trace and final mode)
  - [ ] progress view (reviewed traces, incomplete judgments)
  - [ ] AI suggestions shown separately, with accept/reject
  - [ ] accepted judgments saved as Langfuse scores and under `analysis/state/`
- [ ] `analysis/report/interface_comparison.md`: one design kept from the reference, one
  changed after inspecting traces, one remaining limitation

Part B, review at least 100 distinct traces (no trace in two batches)
- [ ] Batch 1: 15 uniform random + 15 cluster representatives
- [ ] Batch 2: one product dimension chosen before looking at outcomes; 30 traces across
  its values
- [ ] Batch 3: 25 traces from depth searches for candidate modes and close negatives
- [ ] Batch 4 (after drafting the taxonomy): 15 more uniform random
- [ ] Axial coding after each batch; original open codes kept in the history

Part C, Raindrop Workshop (optional)
- [ ] Decide whether to do it
- [ ] If yes: 5-10 runs inspected; `analysis/report/workshop_notes.md` with run ids,
  candidate failures, one uncertain case; accept/revise/reject for each suggestion used

Part D, taxonomy
- [ ] 5-8 binary modes, each with: snake_case name, binary definition, 3+ positives,
  3+ close negatives (when the data permits), originating annotations, boundary vs the
  nearest mode, evaluator type (code check or LLM judge), requirement source
  (SPEC.md id or a recorded SPEC revision)
- [ ] Compared with the AgentDebug taxonomy (arXiv 2509.25370)
- [ ] Search for more instances of one mode; every result reviewed by me;
  accept/reject recorded; repeated after revising the definition; at least one rejected
  suggestion saved
- [ ] One taxonomy revision documented

Part E, apply the taxonomy
- [ ] Every reviewed trace judged present/absent for every final mode
- [ ] Judgments written to Langfuse as scores, matching `analysis/state/labels/<mode>`
- [ ] Count and sample fraction per mode (sample fractions, not prevalence)
- [ ] New consequential modes in the final 15 traces counted (another batch if several)
- [ ] Note which modes have fewer than 30 Pass or 30 Fail labels (HW5 needs both)

Files to commit
- [ ] Review interface code (`analysis/review_app/`)
- [ ] `analysis/state/sample_manifest.json`
- [ ] `analysis/state/annotations.json`
- [ ] `analysis/state/patterns.json`
- [ ] `analysis/state/suggestions.json`
- [ ] One label file per final mode under `analysis/state/labels/`
- [ ] `analysis/report/review_summary.md`: sample size and composition, new modes in the
  final 15, one taxonomy revision, the annotation behind any SPEC.md revision
- [ ] `analysis/report/workshop_notes.md` (only if Part C)
- [ ] `analysis/report/interface_comparison.md`
- [ ] Any `SPEC.md` revision

Submission
- [ ] All files committed and pushed
- [ ] Video (5 min or less), done by me
- [ ] Posted to the course Discord submissions channel, done by me

## Setup facts

- Traces: one Langfuse trace per user turn; a multi-turn scenario has several traces,
  joined by `cartwheel.session_id` (and `cartwheel.scenario_id`).
- Final run: gpt-4o-mini, 250 scenarios (175 coverage, 75 challenge), 356 traces.
  Answer keys are in `scenarios/support_scenarios.jsonl` (`expected`), pilot verdicts in
  `scenarios/pilot_review.jsonl`.
- Offline copy: `traces/support_traces.json` (use only if Langfuse is unavailable, and
  record the reason in the interface comparison).
