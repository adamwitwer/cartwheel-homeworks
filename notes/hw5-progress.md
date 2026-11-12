# HW5 progress (build and evaluate an LLM judge)

Handout: `homework/module-2/hw5.md`. A new session should read this first, then pick up at
**Next step**.

## Ground rules

- Guided walkthrough: Claude explains each step and waits for my "go" before running
  commands, changing files, or spending money. Labels and final decisions are mine.
- Before any paid batch, Claude shows the model and trace count and waits for approval.
- Claude does not show me test predictions before I freeze the judge.
- The handout wins where the skills differ (see below). No numerical acceptance targets.
- Keep my HW4 files and labels unchanged. HW5 labels use **1 = Pass, 0 = Fail** (HW4 used
  1 = failure present) and go to `analysis/state/hw5_labels/<mode>.jsonl`.
- Langfuse work happens on the MacBook Air only; the Mini is frozen. API keys stay in `.env`.
- Never `docker compose ... down -v`. Don't open `homework/module-2/hw4-reference.patch`.

## Current status

- **Mode chosen (2026-11-09):** `policy_claim_without_citation` (RESP-1). From the HW4 labels:
  37 failing and 72 passing conversations, so it clears the 30/30 minimum from independent
  conversations without new labeling. Alternative considered: `reply_contradicts_tool_result`
  (18 failing conversations; it would need synthetic scenarios and paid agent runs).
  - Why a judge and not code: whether a policy id is present is code-checkable, but deciding
    which statements are policy-derived needs judgment (HW4 rules R1 and R4: a bare
    refund-eligibility flag is a record fact; "within 24 hours" and policy-based refusals need
    a citation; a title is not a citation; an id must be a real one).
  - The agent's system prompt asks for it ("Cite the policy id ... for every policy claim",
    `agent/agent.py:70`), so this is not a specification gap.
- **Skills installed (2026-11-09):** `npx skills add ... --agent claude-code --copy` put
  `write-judge-prompt` and `validate-evaluator` in `.claude/skills/` (project level), with
  `skills-lock.json`. Reviewed both: instructions only, no scripts.
  Where they differ from the handout (the handout wins):
  - Split: the skill suggests about 15/45/40; the handout requires 20/40/40 with `split_labels`.
  - Targets: the skill's TPR/TNR > 90% target is not required here.
  - Intervals: the handout asks for 95% Wilson intervals on TPR and TNR; the skill's bootstrap
    applies to the optional prevalence estimate.
  - Model: the skill says start with the most capable model; the handout fixes `gpt-4o-mini`
    for development and test.
  - Labels: the skill suggests about 50/50; the handout's minimum is 30/30, about 100 recommended.
- **Services:** Docker, Langfuse, and the review app can be off until labeling. Judge runs
  read the saved export (`CARTWHEEL_JUDGE_TRACE_SOURCE`).
- **Watch:**
  - The review app saves a label as a Langfuse score named after the mode with a fixed id per
    trace and mode (HW4 convention). Saving HW5 labels that way would overwrite the HW4 scores,
    so HW5 labels need their own path before any labeling.
  - `analysis/state/splits.json` and `analysis/state/judges/` hold the course demo
    (`unsupported_policy_claim`). Check how `split_labels` writes before running it.
  - CI: `test_m2_failure_report_matches_artifact_l_schema` fails only on its demo-mode check
    (expected since HW4 Part D).
- **Part A definition agreed (2026-11-11):** see **Failure definition** below, including
  decisions D1 to D4.
- **Labels written (2026-11-12):** `analysis/state/hw5_labels/policy_claim_without_citation.jsonl`
  (1 = Pass, 0 = Fail; the helpers' `_load_labels` reads this file and flips it internally).
  134 rows: my 117 HW4 labels converted (origin `hw4_label`), 0054 T1 relabeled Fail (lists
  the 14-day window and last day with no id; my HW4 mark predates the settled standard), and
  17 new conversations whose replies cite an id (origin `hw5_review`; I accepted Claude's
  proposals: 14 Pass, 3 Fail: 0109 and 0209 cite the wrong policy (D1), 0106 leaves a cw-returns
  comparison uncited; 0103, 0113, 0182 borderline Pass). HW4 label files unchanged.
  - **Eligible: 109 conversations, 69 Pass / 40 Fail** (after the 0182 swap). One record per conversation (a Fail
    turn if any, else one citing a valid id) and one per data-quality variant group (prefer a
    Fail, then one citing an id, then the lowest scenario id): kept 0182 (swapped in for 0183 by me, 2026-11-12), 0179, 0188, 0191 T2,
    0196 T1, 0202; dropped 17 conversations, marked `eligible: false` with the reason.
  - Pass composition: 20 cite a valid id; 48 have no id (eligibility flags only, or no policy
    content).
- **Part B done (2026-11-12, no model calls):** `analysis/run_judges.py` (`prepare_inputs`,
  `split_data`, `run_development`, `run_test`, plus a small CLI).
  - `prepare` wrote `analysis/state/hw5_trace_inputs.json`: 109 records, one per eligible label,
    each holding every turn up to and including the judged one (the last message is the judged
    reply). Roles: user, tool_call, tool_result, assistant. The tool name is kept inside each
    tool message (the shared flattening keeps only a call's arguments). No narration (D3), no
    labels, notes, answer keys, or scenario metadata; a leak scan found only trace content
    ("not what I expected"; the tool's `"eligible": true`). All 109 load through the course
    `normalize_trace`. Length: median 156 words, max 649.
  - `split` ran once (seed 7, 20/40/40); my mode was added to `splits.json` beside the demo entry
    (insertions only). Do not rerun.

    | Split | Pass | Fail | Pass citing a valid id |
    |---|---|---|---|
    | train | 14 | 8 | 6 |
    | dev | 28 | 16 | 9 |
    | test | 27 | 16 | 6 |
- **Sharpened line adopted; 0113 relabeled Fail (2026-11-12).** Its dashboard procedure for a
  60-day window is a claim on the cw-store-overrides topic with no cw-store-overrides id.
  Appended as a superseding row (origin `hw5_relabel`). Checked every other Pass label against
  the sharpened line: no other change. Train is now 13 Pass / 9 Fail; dev and test unchanged;
  `splits.json` untouched.
- **Part C prompt v0 drafted (2026-11-12):** `analysis/prompts/policy_claim_without_citation-v0.txt`,
  written with `write-judge-prompt` from training examples only: 0206 T1 (clear Fail), 0047 T1
  (clear Pass), 0117 T1 (borderline Pass, D2), 0209 T1 (borderline Fail, D1), 0179 T1 (Fail,
  R4). Includes the task, Pass and Fail rules (R1, R4, D1, D2, the sharpened line), all 18
  policies (short bodies, so the judge can tell which policy a claim comes from), an instruction
  not to follow instructions inside the trace, and critique-then-result output.
- **Dev run, v0 (2026-11-12, `gpt-4o-mini`, 44 dev traces, approved by me):** judge
  `policy_claim_without_citation-v0`; metrics in `analysis/report/dev-policy_claim_without_citation-v0.json`.
  TPR 0.821 (23/28, Wilson 0.644 to 0.921), TNR 0.875 (14/16, 0.640 to 0.965); 7 disagreements:
  - 5 false Fails on bare eligibility flags (R1): 0034, 0046, 0215, 0248, 0249. The judge reads
    "eligible for a refund" / "you can still return it" as a policy claim.
  - 1 false Pass, hallucinated citation: 0048. The critique says the reply "carries cw-returns";
    the reply has no id (the id is only in the tool result).
  - 1 false Pass, missed refusal: 0158 T2 ("I can't process the change directly" + ticket offer).
- **Judge view added to the review app (2026-11-12):** a read-only **Judge** tab
  (`analysis/review_app/judges.py`, route `/api/judges`). For the chosen judge version it shows
  dev TPR/TNR with Wilson intervals, then each trace's HW5 label beside the judge's verdict,
  the reply, and the critique, filterable to disagreements / false Pass / false Fail, with links
  to the conversation. Test predictions are hidden until a judge is frozen (enforced in the
  server). Nothing in it writes labels or scores. Smoke-tested on a spare port: renders, no
  console errors. Restart the app to pick up the new route.
- **v0 disagreements decided (2026-11-12):** all 7 judge errors (I agreed after inspecting them;
  the judge kept asking for an id on order-status and eligibility statements). No label changes.
- **Revision 1 → v1 (2026-11-12):** stronger R1 list ("eligible", "you can still return it" are
  not claims unless the rule is stated); a claim counts as cited only if the id string is in the
  final reply's own text (quote it); Example 6 from training (0222 T2, a cw-roles refusal, Fail);
  output checks (name the rule before Fail, quote the id before Pass).
- **Dev run, v1 (2026-11-12, approved):** TPR 0.893 (25/28, 0.728 to 0.963), TNR 0.750 (12/16,
  0.505 to 0.898); 7 disagreements. Fixed from v0: 0046, 0215 (R1), 0048 (hallucinated citation),
  0158 T2 (refusal). Still wrong: 0034, 0248, 0249 (the judge infers an unstated return rule from
  "eligible"). New false Passes: 0089 T2 and 0044 T2 (citations hallucinated from tool results or
  earlier turns despite the quote rule), 0093 (accepted the invalid id `cw-orders`), 0118 (vague
  escalation rules passed as "no specific rule"; v1's "fail only for a specific rule" wording
  pulled against the sharpened line).
- **Revision 2 → v2 (2026-11-12, approved; the last allowed):** a three-step critique (Step 1
  copy every id string in the final reply and mark it valid or invalid; Step 2 list stated
  policy claims; Step 3 verdict), "do not fail a reply for a rule it merely implies", and vague
  statements about policy-covered processes count as claims (fixing v1's wording against the
  sharpened line). The six example critiques were left in prose.
- **Dev run, v2:** TPR 0.857 (24/28, 0.685 to 0.943), TNR 0.750 (12/16, 0.505 to 0.898); 8
  disagreements. Fixed 0093, 0118, 0044 T2; new errors: 0048, 0069 T3, 0089 T2 (Step 1 still
  "finds" cw-returns that is not in the reply), 0125 (refusal read as no claim), 0210 (called the
  valid `store-saltbox-pantry-policy` invalid). 0034, 0248, 0249 are wrong in all three versions.
- **Across versions:** agreement 37, 37, 36 of 44; every difference is within the intervals, and
  borderline traces flip between runs. The judge's persistent weaknesses are (1) verifying that an
  id literally appears in the reply, which is the code-checkable half of this mode, and (2) not
  reading an implied return rule into "eligible". Stopped revising at the handout's limit of two;
  more prompt edits were trading one error for another rather than removing them.
- **Final version: v0 (my choice, 2026-11-12):** best worse-of-two rate on dev (TPR 0.821, TNR
  0.875) and the most real failures caught.
- **Test run, v0 (2026-11-12, `gpt-4o-mini`, 43 test traces, run once):** frozen at
  2026-11-12T18:04Z, then run on test; metrics in
  `analysis/report/test-policy_claim_without_citation-v0.json`. 27 Pass / 16 Fail.
  TPR 0.593 (16/27, Wilson 0.407 to 0.755), TNR 0.563 (9/16, 0.332 to 0.769); TP 16, FN 11,
  TN 9, FP 7; agreement 25/43. Far below dev; the dev and test intervals barely overlap.
  - 10 of the 11 false Fails are bare eligibility flags (R1): 0026, 0229, 0246, 0150, 0100, 0024,
    0243, 0242, 0211, 0237. The 11th, 0042, puts the 30-day deadline in one paragraph and
    cw-returns in the next; the judge applied D2 (same sentence or paragraph). Possibly a label
    issue (my HW4 "close negative"); left unchanged, since relabeling test after seeing the
    judge's verdicts would bias the estimate.
  - 7 false Passes: hallucinated or earlier-turn citations (0054, 0035 T2, 0036 T2: the reply has
    no id), missed policy-based refusals (0163, 0251 T2, 0090), and one borderline D2 miss (0106).
  - Why test is worse than dev: the split put more of the judge's weakest case into test.
    Uncited-eligibility Passes: train 0, dev 6 (judge right on 1), test 10 (judge right on 0).
    On the other Passes the judge was right on 22/22 dev and 16/17 test. Because train had none,
    the prompt's examples (training only) never showed a bare eligibility flag passing.
- **Next step:** my decision on whether I'd use the judge (Part E), then the video.

## Failure definition: `policy_claim_without_citation` (RESP-1)

**Question.** Does every statement in the agent's final reply that comes from a Cartwheel
policy document name that policy's valid identifier?

**Scope.** The final reply of the judged turn. Earlier turns are context only; a follow-up
reply that restates a policy fact needs its own citation (0035 T2, 0058 T2).

**Policy claim (needs an id):** a rule, window, deadline, threshold, timeline, fee,
permission, or procedure that comes from a policy document, including:
- policy facts relayed from a tool result: "5 to 10 business days" (0072, 0078), "above the
  auto-approval threshold" (0228), "within 24 hours" (0179; rule R4);
- dates computed from a policy window: "the last day is July 25" (0036 T2, 0044 T2);
- refusals or redirects grounded in policy: "I can't change account details in chat" (0158,
  0125), "can't cancel once shipped" (0088), "merchants see only their own store's orders" (0115).

**Not a policy claim (no id needed):** order record facts (status, dates, totals); a bare
eligibility flag with no rule stated, such as "this order is not eligible for a refund"
(rule R1); a generic decline that states no rule (0174).

**Fail** if at least one policy claim lacks a valid id: the id is missing; the policy is
named only by title ("Saltbox Pantry's store policy", 0123, 0107); the id is not one of the 18
in `data/policies/` (`cw-orders`, 0093); or the id is valid but not the policy the claim comes
from (D1).

**Pass** if every policy claim carries the id of its policy, or the reply makes no policy
claim.

**Out of scope (other modes):** whether the claim is correct (`policy_answer_not_grounded`).
**Sharpened line (2026-11-12):** a claim on a topic a policy covers needs that policy's id even
when the claim is wrong (0029 T2, 0020 T2: invented shipping timelines still need cw-shipping);
only a rule on a topic no policy covers is invented, not uncited, and passes (0199 T2: whether a
merchant can buy their own product).

**Evidence the judge sees:** the user messages and earlier turns, the session's tool calls
and results, the final reply, the policy passages retrieved in the session, and the list of
18 valid ids (in the prompt).

**Decisions (2026-11-11, all as recommended):**
- **D1** A valid id for the wrong policy (for example `cw-returns` for Saltbox's 7-day
  override) fails.
- **D2** One id covers the claims from that policy in the same sentence or paragraph.
- **D3** Pre-tool narration is left out of the judge input (the customer never sees it, and
  it sometimes holds a citation the reply lacks: 0175, 0252 T1).
- **D4** One record per conversation. Label the 17 unreviewed conversations whose replies
  cite a valid id (hard-pass candidates); keep one conversation per data-quality variant
  group; report the Pass composition (cites a valid id / eligibility flag only / no policy
  content) with the results.

## Deliverables checklist

- [x] HW5 labels and evidence: `analysis/state/hw5_labels/policy_claim_without_citation.jsonl`
- [x] Split and inputs: `analysis/state/splits.json`, `analysis/state/hw5_trace_inputs.json`
- [x] Every evaluated prompt: `analysis/prompts/`
- [x] Judge versions, predictions, critiques: my mode's files in `analysis/state/judges/`
- [x] Code: `analysis/run_judges.py` (`prepare_inputs`, `split_data`, `run_development`, `run_test`)
- [x] Metrics: `analysis/report/dev-<judge_id>.json`, `analysis/report/test-<judge_id>.json`
- [x] Judge verdict and critique shown beside my label in the HW4 interface; every
      development disagreement inspected
- [x] At most two prompt revisions, with the reason I stopped
- [ ] Video (5 minutes or less; mine): failure mode, one development disagreement and my
      response, test TPR/TNR with intervals (recalculated live from saved predictions), and
      whether I'd use the judge
