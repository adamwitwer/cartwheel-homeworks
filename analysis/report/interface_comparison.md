# Interface comparison

My review interface is `analysis/review_app/` (run `uv run python -m analysis.review_app.server`,
port 8030). The reference is `analysis/server.py` with `analysis/ui/index.html`. Before
planning the app, I reviewed traces in the standard Langfuse view; those notes are in
`notes/hw4-progress.md` under "Part A friction."

## Retained from the reference

**Margin notes beside the trace, with a tool call and its result shown as one step.**
The reference puts free-form notes in a margin column next to the highlighted text and
draws each tool call in one box with its result. I kept both. In Langfuse, the tool output
sits far from the reply that describes it, and nearly every failure I coded was a mismatch
between the two (a reply claiming an order was absent when `list_my_orders` returned it, or
quoting $5.00 for a −5 price). Seeing the call, the result, and my note side by side made
that comparison quick.

## Changed after inspecting the traces

**A context drawer and reviewer lookups beside the conversation.** In the Langfuse view, I
had to leave the trace several times. On 0101 I went outside three times – for the system
prompt, the answer key, and the policy text. On 0078 I had to hunt for the user's role. The
reference has no place for any of these. My app adds:

- a drawer with tabs for the answer key (collapsed by default, so I read the trace before comparing), the system prompt, the policies, SPEC.md, and the tool contracts;
- per conversation, each policy id the reply cited or the agent retrieved, marked "cited," with its text;
- a "no tools called" marker at the top of a turn;
- reviewer-only store and product names beside every `store_id` and `product_id`. I added these after 0013, 0046, and 0186, where I couldn't tell which store or item a row referred to. They are drawn differently and labeled as a lookup the agent did not see, and the agent's blindness to those names turned out to be the cause of most `reply_contradicts_tool_result` failures.

The app also groups the per-turn traces into conversations by `cartwheel.session_id`. The
reference shows one trace at a time, and in Langfuse a follow-up turn appears without the
tool results it depends on (my note on 0008).

## Remaining limitation

**The suggestion controls say "accept" and "reject" without saying what is being accepted.**
In search round 1, I accepted all 11 of Claude's suggestions, including 4 whose own notes
argued against them. I read "accept" as "I agree with this note," eventually coming to understand that it actually means "this trace is an instance of the mode." The four had to be re-decided as rejections, with their annotations withdrawn. A clearer control would name the decision – for example "is an
instance of `reply_contradicts_tool_result`" / "is not an instance" – and show the
definition beside it.

Smaller limitations:
- In a conversation with several turns, finding the turn that belongs to the current batch takes some scrolling. The rail lists conversations, not turns.
- Saving a label requires a running Langfuse (the score is written first, then the local file). Without it, the app saves only with `--local-labels`.
- The structured labeling view handles one trace and mode at a time. For Part E's 936 judgments, I decided the rules and borderline cases in chat. The accepted labels were then written in bulk through the app's own `store.set_label`, which writes to Langfuse and `labels/` exactly as the view does.
