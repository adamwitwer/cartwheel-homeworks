"""Review state under ``analysis/state/`` and label scores in Langfuse.

Files (paths follow the HW4 handout; the root honors
``CARTWHEEL_ANALYSIS_STATE`` through ``analysis.helpers._state``):

- ``annotations.json``: ``{"annotations": [...], "reviewed": {trace_id: {...}}}``.
  Free-form open codes written by the reviewer, plus which traces have been
  read and whether the reviewer recorded "no failure observed".
- ``suggestions.json``: ``{"suggestions": [...]}``. AI suggestions. They are
  never deleted: accepting or rejecting sets ``status`` so rejected
  suggestions stay on file.
- ``patterns.json``: ``{"modes": [...]}``. The taxonomy the coding agent
  maintains from the reviewer's notes. The app only reads it.
- ``sample_manifest.json``: ``{"batches": [...]}``. Which traces are in which
  review batch and why.
- ``labels/<mode>.jsonl``: one present/absent judgment per trace and mode
  (``label`` 1 = failure present, the convention of ``analysis.helpers``). A
  change appends a record and marks the previous one ``superseded_by``.

A judgment is written to Langfuse first, as a NUMERIC score named after the
mode with a deterministic score id, so re-saving a judgment overwrites the
same score instead of adding a duplicate. The local file is written only after
Langfuse accepts the score, so the two stores agree.
"""

from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from analysis.helpers import _state

MODE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
LOCK = threading.RLock()


class LabelError(RuntimeError):
    """A judgment could not be saved; nothing was written locally."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# plain documents
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "annotations.json": {"annotations": [], "reviewed": {}},
    "suggestions.json": {"suggestions": []},
    "patterns.json": {"modes": []},
    "sample_manifest.json": {"batches": []},
}


def read_doc(name: str) -> Any:
    doc = _state.read_json(_state.state_path(name), default=None)
    default = DEFAULTS[name]
    if doc is None:
        return {k: (v.copy() if hasattr(v, "copy") else v) for k, v in default.items()}
    if isinstance(doc, list):  # the reference app stored bare lists
        key = next(iter(default))
        doc = {key: doc}
    for key, value in default.items():
        doc.setdefault(key, value.copy() if hasattr(value, "copy") else value)
    return doc


def write_doc(name: str, doc: Any) -> None:
    if name not in DEFAULTS:
        raise KeyError(name)
    _state.write_json(_state.state_path(name), doc)


# ---------------------------------------------------------------------------
# annotations
# ---------------------------------------------------------------------------

ANNOTATION_FIELDS = {
    "trace_id", "session_id", "scenario_id", "block_key", "quote", "start", "end", "note",
}


def annotation_op(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply one change to annotations.json and return the new document.

    ops: ``add`` (fields above), ``update`` (id, note), ``delete`` (id),
    ``reviewed`` (trace_id, status: "no_failure" | "read" | None).
    """
    op = payload.get("op")
    with LOCK:
        doc = read_doc("annotations.json")
        anns = doc["annotations"]
        if op == "add":
            note = str(payload.get("note") or "").strip()
            if not note or not payload.get("trace_id"):
                raise ValueError("an annotation needs a trace_id and a note")
            ann = {k: payload.get(k) for k in ANNOTATION_FIELDS}
            ann.update(
                id=new_id("ann"),
                note=note,
                author="human",
                source=payload.get("source") or "reviewer",
                created_at=now(),
                updated_at=now(),
            )
            if payload.get("suggestion_id"):
                ann["suggestion_id"] = payload["suggestion_id"]
            anns.append(ann)
            # An annotated trace has been read; recording a note clears an
            # earlier "no failure observed".
            doc["reviewed"][ann["trace_id"]] = {"status": "annotated", "at": now()}
        elif op == "update":
            ann = next((a for a in anns if a.get("id") == payload.get("id")), None)
            if ann is None:
                raise KeyError(payload.get("id"))
            history = ann.setdefault("history", [])
            history.append({"note": ann["note"], "at": ann.get("updated_at")})
            ann["note"] = str(payload.get("note") or "").strip() or ann["note"]
            ann["updated_at"] = now()
        elif op == "delete":
            doc["annotations"] = [a for a in anns if a.get("id") != payload.get("id")]
            tid = payload.get("trace_id")
            if tid and not any(a["trace_id"] == tid for a in doc["annotations"]):
                doc["reviewed"].pop(tid, None)
        elif op == "reviewed":
            tid = payload.get("trace_id")
            status = payload.get("status")
            if not tid:
                raise ValueError("reviewed needs a trace_id")
            if status is None:
                doc["reviewed"].pop(tid, None)
            else:
                if status not in {"no_failure", "read"}:
                    raise ValueError(f"unknown review status {status!r}")
                doc["reviewed"][tid] = {"status": status, "at": now()}
        else:
            raise ValueError(f"unknown annotation op {op!r}")
        write_doc("annotations.json", doc)
        return doc


# ---------------------------------------------------------------------------
# labels and Langfuse scores
# ---------------------------------------------------------------------------


def score_id(trace_id: str, mode: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"cartwheel-hw4/{mode}/{trace_id}"))


def _labels_path(mode: str):
    return _state.state_path("labels", f"{mode}.jsonl")


def live_labels(mode: str) -> dict[str, dict[str, Any]]:
    live: dict[str, dict[str, Any]] = {}
    for row in _state.read_jsonl(_labels_path(mode)):
        if row.get("superseded_by"):
            continue
        live[row["trace_id"]] = row
    return live


def all_live_labels(modes: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    return {mode: live_labels(mode) for mode in modes if MODE_RE.match(mode)}


def set_label(
    trace_id: str,
    mode: str,
    label: int | None,
    *,
    note: str | None = None,
    origin: str = "reviewer",
    context: dict[str, Any] | None = None,
    client: Any = None,
    local_only: bool = False,
) -> dict[str, Any] | None:
    """Save one present (1) / absent (0) judgment, or clear it (None).

    Langfuse is written first; on failure a LabelError is raised and the
    local label file is left unchanged.
    """
    if not MODE_RE.match(mode or ""):
        raise ValueError(f"mode names are snake_case, got {mode!r}")
    if label not in (0, 1, None):
        raise ValueError("label must be 0, 1, or null")
    with LOCK:
        path = _labels_path(mode)
        rows = _state.read_jsonl(path)
        live = next(
            (r for r in reversed(rows) if r["trace_id"] == trace_id and not r.get("superseded_by")),
            None,
        )
        if live and label is not None and live["label"] == label and (note or None) == live.get("note"):
            return live
        if live is None and label is None:
            return None

        sid = score_id(trace_id, mode)
        synced = False
        if not local_only:
            if client is None:
                raise LabelError("Langfuse is not configured, so the judgment was not saved.")
            try:
                if label is None:
                    client.api.score.delete(sid)
                else:
                    client.create_score(
                        score_id=sid,
                        name=mode,
                        value=int(label),
                        trace_id=trace_id,
                        data_type="NUMERIC",
                        comment=note or None,
                        metadata={"source": "human", "origin": origin, "app": "analysis/review_app"},
                    )
                    client.flush()
                synced = True
            except Exception as exc:
                raise LabelError(f"Langfuse score write failed: {type(exc).__name__}: {exc}") from exc

        n = sum(1 for r in rows if r["trace_id"] == trace_id)
        if label is None:
            live["superseded_by"] = f"cleared@{now()}"
            _state.write_jsonl(path, rows)
            return None
        record = {
            "trace_id": trace_id,
            "label": int(label),
            "source": "human",
            "origin": origin,
            "ts": now(),
            "label_id": f"{trace_id}#{n}",
            "langfuse_score_id": sid,
            "langfuse_synced": synced,
        }
        if note:
            record["note"] = note
        for key in ("session_id", "scenario_id"):
            if context and context.get(key):
                record[key] = context[key]
        if live:
            live["superseded_by"] = record["label_id"]
        rows.append(record)
        _state.write_jsonl(path, rows)
        return record


# ---------------------------------------------------------------------------
# suggestions
# ---------------------------------------------------------------------------


def decide_suggestion(
    suggestion_id: str,
    decision: str,
    *,
    note: str | None = None,
    client: Any = None,
    local_only: bool = False,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Accept or reject one AI suggestion. Rejected suggestions stay on file.

    Accepting a ``span`` suggestion adds a reviewer annotation (the reviewer's
    edited note if given). Accepting a ``label`` suggestion saves the
    judgment through :func:`set_label`.
    """
    if decision not in {"accepted", "rejected", "pending"}:
        raise ValueError("decision must be accepted, rejected, or pending")
    with LOCK:
        doc = read_doc("suggestions.json")
        sugg = next((s for s in doc["suggestions"] if s.get("id") == suggestion_id), None)
        if sugg is None:
            raise KeyError(suggestion_id)
        if decision == "accepted" and sugg.get("status") != "accepted":
            if sugg.get("kind", "span") == "label":
                set_label(
                    sugg["trace_id"], sugg["mode"], int(sugg["label"]),
                    note=note or sugg.get("note"), origin="accepted_suggestion",
                    context=context, client=client, local_only=local_only,
                )
            else:
                text = note or sugg.get("note") or f"[{sugg.get('mode')}]"
                ann = annotation_op(
                    {
                        "op": "add",
                        **{k: sugg.get(k) for k in ANNOTATION_FIELDS},
                        "note": text,
                        "source": "accepted_suggestion",
                        "suggestion_id": suggestion_id,
                    }
                )["annotations"][-1]
                sugg["annotation_id"] = ann["id"]
        sugg["status"] = decision
        sugg["decided_at"] = now()
        if note:
            sugg["reviewer_note"] = note
        write_doc("suggestions.json", doc)
        return doc
