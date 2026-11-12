"""Read-only HW5 judge view: human labels beside judge verdicts and critiques.

Human labels come from ``analysis/state/hw5_labels/<mode>.jsonl`` (1 = Pass,
0 = Fail; only live, eligible rows). Judge records come from
``analysis/state/judges/<judge_id>.json`` (``label_convention: pass_positive``,
so a cached prediction of 1 is Pass). Splits come from ``splits.json``.

Test-split predictions are shown only for a frozen judge, so the view never
exposes test results while the prompt can still change. Nothing here writes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analysis.helpers import _state


def _jsonl(path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _human_labels(mode: str) -> dict[str, int]:
    live: dict[str, dict[str, Any]] = {}
    for row in _jsonl(_state.state_path("hw5_labels", f"{mode}.jsonl")):
        if not row.get("superseded_by"):
            live[row["trace_id"]] = row
    return {tid: int(r["label"]) for tid, r in live.items() if r.get("eligible", True)}


def _report(kind: str, judge_id: str) -> dict[str, Any] | None:
    path = Path(__file__).resolve().parents[1] / "report" / f"{kind}-{judge_id}.json"
    return json.loads(path.read_text()) if path.exists() else None


def judge_view() -> dict[str, Any]:
    labels_dir = _state.state_path("hw5_labels")
    modes = sorted(p.stem for p in labels_dir.glob("*.jsonl")) if labels_dir.exists() else []
    splits = _state.read_json(_state.state_path("splits.json"), default={})
    judges_dir = _state.state_path("judges")
    out = []
    for mode in modes:
        human = _human_labels(mode)
        split_of = {tid: name for name in ("train", "dev", "test") for tid in splits.get(mode, {}).get(name, [])}
        judges = []
        for path in sorted(judges_dir.glob(f"{mode}-v*.json")):
            judge = _state.read_json(path)
            frozen = judge.get("status") == "frozen"
            if judge.get("label_convention") != "pass_positive":
                continue  # only HW5-convention judges; the course demo judge uses the old one
            preds = judge.get("predictions", {}).get(judge["prompt_hash"], {})
            crits = judge.get("critiques", {}).get(judge["prompt_hash"], {})
            visible = {"train", "dev"} | ({"test"} if frozen else set())
            rows = [
                {"trace_id": tid, "split": split_of.get(tid), "human": human.get(tid),
                 "judge": int(pred), "critique": crits.get(tid, "")}
                for tid, pred in preds.items() if split_of.get(tid) in visible
            ]
            judges.append({
                "judge_id": judge["judge_id"], "version": judge.get("version"), "status": judge.get("status"),
                "model": judge.get("model"), "created_at": judge.get("created_at"),
                "frozen_at": judge.get("frozen_at"),
                "dev": _report("dev", judge["judge_id"]),
                "test": _report("test", judge["judge_id"]) if frozen else None,
                "rows": rows,
                "hidden_test_predictions": 0 if frozen else sum(split_of.get(t) == "test" for t in preds),
            })
        out.append({"mode": mode, "counts": {s: len(splits.get(mode, {}).get(s, [])) for s in ("train", "dev", "test")},
                    "judges": judges})
    return {"modes": out}
