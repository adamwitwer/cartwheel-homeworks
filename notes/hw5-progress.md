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
- **Next step:** Part A. Write the HW5 failure definition (question, Pass and Fail rules,
  evidence needed) from the HW4 definition and boundary; then plan the label set.

## Deliverables checklist

- [ ] HW5 labels and evidence: `analysis/state/hw5_labels/policy_claim_without_citation.jsonl`
- [ ] Split and inputs: `analysis/state/splits.json`, `analysis/state/hw5_trace_inputs.json`
- [ ] Every evaluated prompt: `analysis/prompts/`
- [ ] Judge versions, predictions, critiques: my mode's files in `analysis/state/judges/`
- [ ] Code: `analysis/run_judges.py` (`prepare_inputs`, `split_data`, `run_development`, `run_test`)
- [ ] Metrics: `analysis/report/dev-<judge_id>.json`, `analysis/report/test-<judge_id>.json`
- [ ] Judge verdict and critique shown beside my label in the HW4 interface; every
      development disagreement inspected
- [ ] At most two prompt revisions, with the reason I stopped
- [ ] Video (5 minutes or less; mine): failure mode, one development disagreement and my
      response, test TPR/TNR with intervals (recalculated live from saved predictions), and
      whether I'd use the judge
