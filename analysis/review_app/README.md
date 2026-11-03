# HW4 review app

A review interface for the Cartwheel HW3 traces: one conversation per page
(turns grouped by `cartwheel.session_id`), with the answer key, policies,
system prompt, tool contracts, and SPEC.md one click away.

```bash
uv run python -m analysis.review_app.server            # http://localhost:8030
uv run python -m analysis.review_app.server --refresh  # reload traces from Langfuse
```

- Traces load live from Langfuse (final-run `support-` scenarios only) and are
  cached in `analysis/review_app/.cache/` (gitignored). If Langfuse is
  unavailable, the app falls back to `traces/support_traces.json` and shows a
  banner with the reason.
- Annotations, suggestions, the taxonomy, and the sample manifest are files
  under `analysis/state/` (see `store.py`).
- A present/absent judgment is written to Langfuse as a NUMERIC score named
  after the mode (1 = failure present), with a fixed score id per trace and
  mode, then appended to `analysis/state/labels/<mode>.jsonl`. If the Langfuse
  write fails, nothing is saved locally. `--local-labels` saves locally only
  (`langfuse_synced: false`) for offline work.
- Set `CARTWHEEL_ANALYSIS_STATE=<dir>` to use a scratch state directory.

Views: **Review** (select text to annotate; notes appear in the margin),
**Taxonomy**, **Labels** (trace × mode grid), **Progress** (batches,
incomplete judgments, AI suggestion queue). Keys: `[` and `]` move between
conversations, `Esc` closes the drawer.
