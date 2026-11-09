# HW4 review summary

Cartwheel support agent (gpt-4o-mini), final Module 1 run: 250 scenarios, 356 traces (one
trace per user turn). Pilot traces were excluded. The state files are in `analysis/state/`;
the decision log is `notes/hw4-progress.md`.

## Reviewed sample

117 distinct traces from 109 conversations, drawn in six batches. No trace counts toward
more than one batch. Seeds and selection reasons are in `sample_manifest.json`.

| Batch | Traces | How it was drawn |
|---|---|---|
| `b1-uniform` | 15 | Uniform random over the 356 traces (seed 20261103) |
| `b1-cluster` | 15 | k-means (k = 15) over behavior features only (tools called, call count, follow-up turn, reply length); the member nearest each centroid |
| `b2-role` | 30 | 10 per user role (shopper, merchant, support), uniform within each role |
| `b3-depth` | 25 | Depth searches for situations in which a candidate mode could occur (a search that hit its limit, a repeated title, each data-quality type, 2+ orders listed, refunds, denials, policy questions), not for the failure itself, so they return close negatives too |
| `b4-uniform` | 15 | Uniform random over the 271 traces not yet sampled; coded blind to the candidate modes as the stability check |
| `d-search` | 17 | Part D search for more `reply_contradicts_tool_result` instances; every returned trace reviewed |

By role: shopper 66, merchant 27, support 24. By scenario group: coverage 67, challenge 50.
Twenty-nine of the traces are follow-up turns. Only `b1-uniform` and `b4-uniform` are uniform draws,
so the counts below describe this sample, not the trace store.

## Stability: the final 15

Batch 4 (`b4-uniform`) produced 10 notes and 5 "no failure observed." Seven notes fit existing
modes. 0222 T2 fit only after `reply_contradicts_tool_result` was widened to tool results
from earlier turns. 0026 and 0229 T2 (with 0229 T1 recoded from batch 1) formed one new
pattern: volunteering "not eligible for a refund" when nobody asked. I judged it the least
consequential mode and dropped it in Part D.

**New consequential modes in the final 15: 0.** One minor pattern appeared and was rejected,
and one existing mode was widened. The taxonomy was close to saturated, so I skipped the
optional Workshop (Part C).

## Final taxonomy and sample fractions

Every mode was applied to every reviewed trace: 117 × 8 = 936 present/absent judgments, as
Langfuse scores and in `analysis/state/labels/<mode>.jsonl`. The fractions are of the 117 reviewed traces.

| Mode | Requirement | Fail | Sample fraction | Close negatives |
|---|---|---|---|---|
| `policy_claim_without_citation` | RESP-1 | 39 | 33.3% | 3 |
| `reply_contradicts_tool_result` | RESP-3 | 19 | 16.2% (13 from `d-search`) | 3 |
| `policy_answer_not_grounded` | SCOPE-1, PURPOSE-1 | 13 | 11.1% | 3 |
| `reply_omits_decision_basis` | RESP-5, RESP-4, RESP-3 | 11 | 9.4% | 3 |
| `required_action_not_taken` | ESC-1 to ESC-4, cw-refunds | 11 | 9.4% | 4 |
| `inconsistent_record_not_escalated` | ESC-4, RESP-3 | 10 | 8.5% | 4 |
| `truncated_search_presented_as_complete` | RESP-3 | 8 | 6.8% | 3 |
| `same_title_listing_not_distinguished` | RESP-6 | 4 | 3.4% | 2 |

Definitions, boundaries, examples, and open questions are in `patterns.json`. All eight are
judge modes. For several, the trigger is code-checkable: whether a search hit its limit,
whether duplicate titles came back, whether a policy id is present. Deciding whether the
reply failed still needs a judge.

`same_title_listing_not_distinguished` has 2 close negatives, not 3, because the data
permits no more: all 9 same-title searches in the 356 traces are in the sample, and the
only other candidate (0239 T1) is inconsistent with 0143 and 0238.
`truncated_search_presented_as_complete` has no negative that hit the limit and said the
list might be partial, because no reply in the corpus says that. Its close negatives are
lists below the limit, which are genuinely complete.

### How the 936 judgments were made

- **From my coding (317):** my positives, my close negatives, and traces I marked "no failure" (absent for every mode).
- **From code rules (357):** a mode is absent when its trigger cannot occur. For example, there is no search for the search modes, and no order or product tool call in the session for the contradiction mode. I checked that no positive misses its trigger.
- **From Claude's proposals, accepted by me (241):** the remaining pairs, mostly the non-coded modes of traces I had annotated for their first failure, each with a reason.
- **After the consistency recodes (21):** the other modes of the eight recoded traces (below), set absent.

Four rules settled groups of proposals:
- A bare refund-eligibility flag is a record fact and needs no citation. Stating the rule does need one.
- An ESC-4 bad record the agent never noticed counts only under `inconsistent_record_not_escalated`.
- A misquoted damaged record counts under both the contradiction and the bad-record mode.
- "Within 24 hours" without `cw-escalations`, and a policy refusal without an id, fail the citation mode.

## Taxonomy revision

**Merge: `asks_instead_of_acting` + `required_escalation_not_made` → `required_action_not_taken`.**
After batch 4 there were 11 candidates. The handout's product-change test merges two modes
when one fix covers both. Offering to escalate instead of escalating (0158, 0163, 0251 T2,
0180) and deciding not to escalate (0206 never queued its $547 ESC-1 refund) have the same
fix: tell the agent to call the required tool now, for any role, without asking permission,
and flag ESC cases that end without `escalate_to_human`. So they became one mode.

**A correction to that revision.** I first argued the merge from 0175 (support staff
relaying a legal threat), recorded as "opened no ticket." While deriving the Part E labels,
the trace showed the agent did escalate (ticket 154). Its real failure was that only the
narration said "I can't provide legal advice." The reply never did, and the clarified
SPEC section 5 says the reply must state both. 0175 moved to `reply_omits_decision_basis`.
The merge stands on 0206.

Other revisions:
- `policy_answer_wrong_or_incomplete` was renamed `policy_answer_not_grounded` after the AgentDebug comparison.
- `reply_contradicts_tool_result` was widened during the search from "contradicts" to "contradicts **or cannot show**". After that change, 0077 (stating a refund amount that only the caller had supplied) reversed from a rejected suggestion to a positive.
- Eight early "no failure" marks were recoded to the settled standards: citations in 0073, 0079, 0088, 0089 T3, 0098 T3, 0107 and 0156; the required action in 0156; the omitted basis in 0215. The original marks are kept in `annotations.json` (`reviewed[...].previous`).

## Search for additional instances

Target: `reply_contradicts_tool_result`, which had only 3 positives after batch 4.

- **Round 1** used a deterministic filter over the unreviewed traces (status words, eligibility, not-found claims, values absent from tool results). It flagged 26. Claude read each one and suggested 11; I accepted 7.
- **Round 2** came after the definition revision ("cannot show"). The filter found nothing new, so Claude read the 13 unreviewed turns that chose among 2+ order rows with no titles. It suggested 6, and I accepted 5.

The mode ended with 16 positives (19 after Part E labeling).

**A rejected suggestion: 0145.** A support caller asked for dry bags under $60. The agent
searched "dry bags," got 0 results, and said none were available. The catalog has 3 under
"dry bag." The reply agrees with its tool result, and this mode is about the reply against
the tool results, not the quality of the tool call. So it is outside the boundary: the
defect is the query. Other rejections: 0100 (the reply agreed with the tool; the real
failure was not answering the refund-timing question, `policy_answer_not_grounded`), 0237
(every stated fact matched the rows), and 0089 T1 (stated the tool's limitation instead of
asserting absence, which became the mode's close negative).

**What the search showed.** Most positives share one cause: `list_my_orders` and
`find_order` return product and store ids but no titles or store names. So the agent cannot
tell which row is the customer's item, and it guesses or claims the item is absent (0001,
0081, 0083, 0090, 0150, 0228, 0235 T2, 0236). 0228 refunded the wrong order ($272.25)
while telling the customer it was their Slim Pencil Set. The fix is either another tool
call or a tool that returns what the agent needs.

## Changes to SPEC.md

- **RESP-6 (2026-11-04):** name the store for each matching result, or ask which one; never present one listing as the only answer. The TOOL-3 `search_products` contract now includes the store name. Motivating annotation: **0239** (gave one store's $10.75 as the price; the same title is $218.50 at another store). In Part D I decided that when all matches come from one store, store plus price is enough (0192, 0194); a product id is not required.
- **Section 5 (2026-11-07):** escalation applies to every caller role, including support staff. When a case also includes a request the agent refuses under SCOPE-2, the agent declines that part, still escalates, and the reply states both. Motivating annotation: **0175**.

The SPEC edits do not change the running agent or its tools; `search_products` still returns only store ids.

## Comparison with AgentDebug

AgentDebug (Zhu et al. 2025, arXiv 2509.25370, Table 2) sorts failures into Memory,
Reflection, Planning, Action, and System modules.

- **Rename:** it splits hallucination (0121, 0199 T2, 0029 T2) from retrieval failure (0050, 0055). One fix covers both: answer only from the looked-up policies. But the comparison showed my old name, "wrong or incomplete," hid that shared cause, so I renamed the mode.
- **Omission considered and rejected:** Action / parameter error matches a mode I dropped, `store_id_passed_as_store_name`. A code check finds exactly 3 instances (0140 T1, 0191 T1, 0199 T1). Its fix is in the setup, not the agent's replies.
- **Disagreement:** AgentDebug would call a damaged record a System / environment error ("not the agent's fault"). SPEC.md (RESP-3, ESC-4) makes noticing and escalating it the agent's job, so `inconsistent_record_not_escalated` stays an agent failure.
- **No counterpart:** citation, omitted basis, and same-title modes have no AgentDebug equivalent. Its taxonomy has no communication-quality category.

## Observations that are not modes

- **Rejected modes:** `store_id_passed_as_store_name` (setup defect); `unrequested_refund_status_volunteered` (0026, 0229 T1/T2; low impact, loose RESP-5 fit). The original `required_escalation_not_made` was merged, as described above.
- **Defects for HW8:**
  - `list_my_orders` and `find_order` return no titles or store names. This is the root cause of most `reply_contradicts_tool_result` positives.
  - Merchants are given only a store id, which they pass where a store name is expected.
  - `check_return_eligibility` has no SPEC.md tool contract.
  - Two cited policy ids are not in the corpus (`cw-orders`, `cw-cancellation`).
- **Spec tension:** `cw-account-security` says account changes happen only through account settings, while ESC-2 and `cw-escalations` send them to a human. I coded against ESC-2 (escalate), and the answer keys agree.
- **For HW5:** every mode has at least 78 pass labels, but only the citation mode (39) has 30 or more failure labels; the others have 4 to 19. Judge validation will need synthetic scenarios targeting those modes.
