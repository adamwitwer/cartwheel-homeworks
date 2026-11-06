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
- Langfuse data lives on the MacBook Air since 2026-11-03 (see **Langfuse migration**
  below). Do all Langfuse work and labeling there; the Mac mini's copy is frozen.

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
- **Batch 1 drawn (2026-11-03, on the Air):** `analysis/review_app/sampling.py` wrote
  `b1-uniform` (15, `random.Random(20261103)` over the 356 sorted trace ids) and
  `b1-cluster` (15) to `analysis/state/sample_manifest.json`. Clustering: k-means, k=15,
  over standardized behavior features only (one yes/no per tool called, tool-call count,
  follow-up turn, log reply length); no role, scenario group, answer key, or citation
  flags. Best of 10 seeded starts by inertia (seed 20261107, 540.9; the single-start run
  at 690.0 merged `find_order` turns into a no-tools cluster). Representative = member
  nearest the centroid, excluding uniform picks. Part A traces stay in the pool (0192 T1
  is a cluster rep). Uniform picks: 0020 T2, 0042, 0046, 0048, 0050, 0054, 0079, 0088,
  0089 T3, 0129, 0132, 0156, 0185, 0202, 0215 (T1 unless noted). Cluster reps: 0186,
  0098 T3, 0125, 0229, 0192, 0190, 0239 T2, 0013, 0073, 0107, 0047, 0252, 0238, 0082,
  0126 T2.
- **Batch 2 dimension: user role** (chosen 2026-11-03, before reading any batch 1 trace).
- **Batch 1 open coding done (2026-11-04):** 30/30 reviewed; 10 notes, 20 "no failure
  observed". After Claude's check against SPEC.md, tool results, answer keys, and
  `data/cartwheel.db`, I revised: 0079 (pre-tool narration, final reply correctly says
  queued) → no failure; 0215 (denial was correct: 46 days vs Northwind's 45) → no failure;
  0185 (caller is support staff; agent reported the missing date) → no failure; 0126 T2
  reviewed (I had marked T1 by mistake).
- **App bug found and fixed (2026-11-04):** deleting a note erased it (and reset the trace
  to unreviewed), losing the original open code. Deletes now move the note to
  `withdrawn` in `annotations.json`. The three deleted notes (0079, 0185, 0215) were rebuilt
  from Claude's earlier printout into `withdrawn`, marked `restored`, without the original
  ids or character offsets.
- **SPEC.md revision (2026-11-04):** new **RESP-6** (name the store for each matching
  result or ask which one; never present one result as the only answer) and the TOOL-3
  `search_products` success contract now includes store name. Motivating annotation:
  0239 (gave one store's $10.75 as the price; the same title is $218.50 at another
  store). Note: `search_products` itself still returns only `store_id` until its code changes.
- **Reviewer name lookups added to the app (2026-11-04):** store and product names from
  `data/cartwheel.db` appear beside `store_id` / `product_id` in tool results, drawn by
  CSS and marked as a lookup the agent did not see. Interface-comparison candidate
  ("changed after inspecting traces": I couldn't map store ids to names on 0013/0046/0186).
- **Axial coding, batch 1 (2026-11-04):** groups accepted; recorded as `candidate` modes in
  `patterns.json` with definitions, boundaries, requirement ids, and open questions:
  `policy_claim_without_citation` (0048, 0125, 0252; RESP-1),
  `policy_answer_wrong_or_incomplete` (0020, 0050), `reply_contradicts_tool_result`
  (0013, 0046; RESP-3), `inconsistent_record_not_escalated` (0186; close negative 0185;
  ESC-4, RESP-3), `same_title_listing_not_distinguished` (0238, 0239; RESP-6). Dropped:
  the RESP-2 overclaim group (its only note, 0079, was withdrawn). Status stays
  `candidate`, so the course failure report and its schema test ignore them for now.
- **Batch 2 drawn (2026-11-05):** `sampling.py --batch 2` wrote `b2-role` to the manifest:
  10 per role (shopper / merchant / support), uniform within each role, seed 20261104,
  pools after excluding batch 1: 196 / 77 / 53. Equal rather than proportional (which
  would give support only 5). 60 distinct traces across batches 1 and 2. Picks:
  shopper 0002, 0015, 0035 T2, 0044 T2, 0056, 0069 T3, 0089 T2, 0101, 0158 T2, 0243 T2;
  merchant 0017 T2, 0024, 0072, 0076, 0115, 0142, 0163, 0183, 0191 T2, 0221;
  support 0028, 0055, 0078, 0121, 0174, 0176, 0198, 0241, 0247, 0250 (T1 unless noted).
  0089 T2 shares a conversation with batch 1's 0089 T3; 0101 and 0078 were Part A traces.
- **Batch 2 open coding done (2026-11-05/06):** 30/30 reviewed; 22 notes, 8 "no failure
  observed". After Claude's check I made a second pass, mostly holding the agent to the same
  standard as batch 1: added 0176 (reversed dates), 0158 / 0163 (offered escalation, never
  escalated; nothing in the spec says to confirm first), 0101 / 0115 / 0044 T2 / 0035 T2 /
  0089 T2 / 0069 T3 (uncited policy claims), 0250, 0076, 0221, 0183. Kept 0028 T1. Kept
  "potentially incomplete" on the capped searches: the trace shows only that 5 came back
  from a limit of 5. 0221 and 0183: the reason appeared only in the narration before a tool call,
  which the customer never sees.
- **App fix (2026-11-06):** the sample rail listed a conversation only under its earliest
  batch, so 0089 (T3 in b1-uniform, T2 in b2-role) was missing from b2-role. It now
  appears under every batch that holds one of its turns.
- **Axial coding, batch 2 (2026-11-06):** groups accepted; `patterns.json` now has 8
  `candidate` modes, every live note in one:
  `policy_claim_without_citation` 9, `policy_answer_wrong_or_incomplete` 5 (+0121, 0055,
  0250), `reply_contradicts_tool_result` 2 (no new), `inconsistent_record_not_escalated` 3
  (+0176, 0198; widened to product records; close negatives 0185, 0183),
  `same_title_listing_not_distinguished` 2 (0191 raises a RESP-6 wording question: same
  store, so the store name can't tell them apart). New: `truncated_search_presented_as_complete`
  (0142, 0191, 0241; RESP-3), `asks_instead_of_acting` (0056, 0243, 0158, 0163; close
  negatives 0072, 0078; ESC-2, cw-refunds), `reply_omits_decision_basis` (0076, 0221,
  0183, 0028; RESP-5, RESP-4, RESP-3).
  - By role: support 7/10 annotated, merchant 7/10, shopper 8/10. The refund split (shoppers
    asked to confirm, merchants and support got refunds) follows whether the message gave
    an amount and reason, not the role.
  - For `review_summary.md`: cw-account-security ("account changes happen only through
    account settings") conflicts with ESC-2 and cw-escalations (send to a human).
- **Next step:** batch 3, 25 traces from targeted searches for the thin modes
  (`reply_contradicts_tool_result`, `same_title_listing_not_distinguished`,
  `inconsistent_record_not_escalated` via the data-quality scenarios) and the follow-up turns
  that batch 1 and 2 left unsampled (for example 0028 T2/T3, 0158 T3). Claude proposes the
  search queries; I approve them before the draw.
- Restart the app after pulling code changes:
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

## Langfuse migration (Mac mini → MacBook Air, 2026-11-03)

Both Macs run `observability/docker-compose.yml`, which fixes the project id, API keys,
salt, and encryption key, so copied data works unchanged with the same `.env`.
Volumes (compose project `observability`): `langfuse_postgres_data` (projects, scores),
`langfuse_clickhouse_data` (traces, observations), `langfuse_minio_data` (raw events).
Redis and the ClickHouse logs are not copied.

1. Mini: `docker compose -f observability/docker-compose.yml stop` (never `down -v`);
   archive each volume with
   `docker run --rm -v observability_<vol>:/data -v <dir>:/backup alpine tar czf /backup/<vol>.tgz -C /data .`;
   start the stack again; confirm 397 traces.
2. Copy the archives to the Air over SSH.
3. Air: `git pull`; stop the stack; archive its own three volumes as a backup; clear each
   volume and untar the Mini's archive into it; start the stack.
4. Verify on the Air: 397 traces, 0 scores, review app loads 250 conversations.

The Mini's Langfuse copy stays untouched as a fallback until the Air checks pass.

**Done 2026-11-03 (Claude over SSH from the Mini, `adam@192.168.50.18`).** Checksums
matched after copy. Air before: 8 traces, 46 observations, 0 scores; those were backed up
to `~/langfuse-migration/air-backup/` on the Air. Air after: 397 traces, 2253
observations, 0 scores, the same as the Mini. The review app on the Air loads 356 traces
and 250 conversations live from Langfuse. **The Air is now the Langfuse machine for HW4**;
the Mini's copy is frozen as of the migration and should not receive scores. The git-lfs
warning on `git pull` over SSH is only a PATH issue (`/opt/homebrew/bin/git-lfs`
exists); LFS tracks only the reference patches.

## Setup facts

- Traces: one Langfuse trace per user turn; a multi-turn scenario has several traces,
  joined by `cartwheel.session_id` (and `cartwheel.scenario_id`).
- Final run: gpt-4o-mini, 250 scenarios (175 coverage, 75 challenge), 356 traces.
  Answer keys are in `scenarios/support_scenarios.jsonl` (`expected`), pilot verdicts in
  `scenarios/pilot_review.jsonl`.
- Offline copy: `traces/support_traces.json` (use only if Langfuse is unavailable, and
  record the reason in the interface comparison).
