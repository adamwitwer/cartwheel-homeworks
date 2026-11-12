"""HW5: inputs, split, development runs, and the held-out test for one LLM judge.

Mode: ``policy_claim_without_citation`` (RESP-1). Labels live in
``analysis/state/hw5_labels/<mode>.jsonl`` (1 = Pass, 0 = Fail); only rows with
``eligible: true`` (one per conversation, one per data-quality variant group)
are used.

Usage, from the repository root:

    uv run python -m analysis.run_judges prepare      # write hw5_trace_inputs.json (no model calls)
    uv run python -m analysis.run_judges split        # write splits.json for the mode (run once)
    uv run python -m analysis.run_judges dev analysis/prompts/<mode>-v0.txt   # paid: dev split
    uv run python -m analysis.run_judges test <judge_id>                    # paid: freeze + test
    uv run python -m analysis.run_judges metrics <judge_id> [dev|test]      # free: recompute from saved predictions

Set ``CARTWHEEL_JUDGE_TRACE_SOURCE`` to the saved inputs before running dev or
test, so every prompt version sees exactly the same records:

    export CARTWHEEL_JUDGE_TRACE_SOURCE="$PWD/analysis/state/hw5_trace_inputs.json"
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

MODE = "policy_claim_without_citation"
ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "analysis" / "state"
LABELS = STATE / "hw5_labels" / f"{MODE}.jsonl"
INPUTS = STATE / "hw5_trace_inputs.json"
REPORT = ROOT / "analysis" / "report"


def _eligible_labels(mode: str = MODE) -> dict[str, dict[str, Any]]:
    path = STATE / "hw5_labels" / f"{mode}.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    live = {r["trace_id"]: r for r in rows if not r.get("superseded_by")}
    return {tid: r for tid, r in live.items() if r.get("eligible")}


def _result(value: Any) -> Any:
    """Tool results are stored as Python reprs in the review-app cache; return data."""
    if isinstance(value, str):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value
    return value


def _messages(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Messages for the judge: user text, tool calls and results, and replies.

    Pre-tool narration ("note" blocks) is left out (decision D3): the customer
    never sees it, and it sometimes contains a citation the reply lacks. The tool
    name is kept inside each tool message, because the shared flattening step
    keeps only a tool call's arguments.
    """
    out: list[dict[str, Any]] = []
    for turn in turns:
        for block in turn["blocks"]:
            kind = block["kind"]
            if kind == "user":
                out.append({"role": "user", "text": block["text"]})
            elif kind == "tool":
                out.append({"role": "tool_call", "name": block["name"],
                            "arguments": {"tool": block["name"], "arguments": block.get("arguments")}})
                out.append({"role": "tool_result", "name": block["name"],
                            "content": {"tool": block["name"], "result": _result(block.get("result"))}})
            elif kind == "reply":
                out.append({"role": "assistant", "text": block["text"]})
    return out


def prepare_inputs(mode: str = MODE, out_path: Path = INPUTS) -> list[dict[str, Any]]:
    """Write one judge input per eligible labeled conversation.

    Each record holds the judged turn's ``trace_id`` and ``trace``: every turn up
    to and including the judged one, so the last assistant message is the reply
    under evaluation. Labels, review notes, answer keys, and scenario metadata are
    never included.
    """
    sys.path.insert(0, str(ROOT))
    from analysis.review_app import data

    labels = _eligible_labels(mode)
    raw, _ = data.load_raw()
    convs, _ = data.build_conversations(raw)
    records = []
    for conv in convs:
        for turn in conv["turns"]:
            if turn["trace_id"] in labels:
                upto = conv["turns"][: turn["number"]]
                records.append({"trace_id": turn["trace_id"], "trace": _messages(upto)})
    got = {r["trace_id"] for r in records}
    if got != set(labels) or len(records) != len(got):
        raise ValueError(f"inputs do not match eligible labels: missing {sorted(set(labels) - got)[:5]}")
    for r in records:
        if r["trace"][-1]["role"] != "assistant":
            raise ValueError(f"{r['trace_id']}: the judged turn has no final reply")
    out_path.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return records


def split_data(mode: str = MODE) -> dict[str, list[str]]:
    """Split the eligible labels 20/40/40 (seed 7) with the course helper. Run once."""
    sys.path.insert(0, str(ROOT))
    from analysis.helpers import split_labels

    records = json.loads(INPUTS.read_text())
    return split_labels(
        mode,
        fractions=(0.20, 0.40, 0.40),
        seed=7,
        min_per_class=10,
        eligible_trace_ids=[record["trace_id"] for record in records],
    )


def run_development(mode: str, prompt_path: str | Path) -> dict[str, Any]:
    """Register a prompt version, run it on the dev split, and save its metrics. Paid."""
    sys.path.insert(0, str(ROOT))
    from analysis.helpers import judge_alignment, register_judge, run_judge

    record = register_judge(mode=mode, prompt_text=Path(prompt_path).read_text(), judge_model="gpt-4o-mini")
    judge_id = record["judge_id"]
    run_judge(judge_id, split="dev", batch_size=10)
    development = judge_alignment(judge_id, split="dev")
    out = {"judge_id": judge_id, "prompt_path": str(prompt_path), "split": "dev", **development}
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / f"dev-{judge_id}.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    return out


def run_test(judge_id: str) -> dict[str, Any]:
    """Freeze the chosen judge, run it once on the test split, and save its metrics. Paid."""
    sys.path.insert(0, str(ROOT))
    from analysis.helpers import freeze_judge, judge_alignment, run_judge

    freeze_judge(judge_id)
    run_judge(judge_id, split="test", batch_size=10)
    test = judge_alignment(judge_id, split="test")
    out = {"judge_id": judge_id, "split": "test", **test}
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / f"test-{judge_id}.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    return out


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for k successes out of n."""
    p = k / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / (1 + z * z / n)
    return round(center - half, 4), round(center + half, 4)


def recompute_metrics(judge_id: str, split: str = "test", mode: str = MODE) -> dict[str, Any]:
    """Recalculate TPR and TNR from saved predictions only (no model calls, writes nothing).

    Reads the split's trace ids from ``splits.json``, my labels from the HW5 labels
    file, and the judge's cached verdicts from its record. Pass (1) is the positive
    class: TPR is agreement on my Passes, TNR on my Fails.
    """
    judge = json.loads((STATE / "judges" / f"{judge_id}.json").read_text())
    if split == "test" and judge.get("status") != "frozen":
        raise SystemExit(f"{judge_id} is not frozen; test metrics are only available after freezing")
    ids = json.loads((STATE / "splits.json").read_text())[mode][split]
    labels = _eligible_labels(mode)
    preds = judge["predictions"][judge["prompt_hash"]]

    print(f"{judge_id} ({judge['status']}, {judge['model']}), {split} split, {len(ids)} traces")
    print(f"{'trace':<14}{'human':<7}{'judge':<7}")
    tp = fn = tn = fp = 0
    for tid in sorted(ids, key=lambda t: (labels[t]["scenario_id"], labels[t].get("turn", 0))):
        human, verdict = int(labels[tid]["label"]), int(preds[tid])
        tp += human == 1 and verdict == 1
        fn += human == 1 and verdict == 0
        tn += human == 0 and verdict == 0
        fp += human == 0 and verdict == 1
        name = f"{labels[tid]['scenario_id'].removeprefix('support-')} T{labels[tid].get('turn', 1)}"
        flag = "" if human == verdict else "  <- disagree"
        print(f"{name:<14}{'Pass' if human else 'Fail':<7}{'Pass' if verdict else 'Fail':<7}{flag}")

    tpr, tnr = tp / (tp + fn), tn / (tn + fp)
    tpr_ci, tnr_ci = _wilson(tp, tp + fn), _wilson(tn, tn + fp)
    print(f"\nTP {tp}  FN {fn}  TN {tn}  FP {fp}")
    print(f"TPR = TP / (TP + FN) = {tp}/{tp + fn} = {tpr:.4f}   95% Wilson {tpr_ci[0]:.4f} to {tpr_ci[1]:.4f}")
    print(f"TNR = TN / (TN + FP) = {tn}/{tn + fp} = {tnr:.4f}   95% Wilson {tnr_ci[0]:.4f} to {tnr_ci[1]:.4f}")

    sys.path.insert(0, str(ROOT))
    from analysis.helpers import judge_alignment

    helper = judge_alignment(judge_id, split=split)
    ours = {"tp": tp, "fn": fn, "tn": tn, "fp": fp, "tpr_interval": list(tpr_ci), "tnr_interval": list(tnr_ci)}
    agree = all(helper[k] == v for k, v in ours.items())
    print(f"Matches the course helper judge_alignment: {agree}")
    return {**ours, "tpr": round(tpr, 4), "tnr": round(tnr, 4), "matches_helper": agree}


def _live_env() -> None:
    """Load model keys from .env (values never printed) and pin the saved inputs."""
    import os

    sys.path.insert(0, str(ROOT))
    from analysis.review_app import data

    data.load_env()
    os.environ.setdefault("CARTWHEEL_JUDGE_TRACE_SOURCE", str(INPUTS))
    if Path(os.environ["CARTWHEEL_JUDGE_TRACE_SOURCE"]).resolve() != INPUTS.resolve():
        raise SystemExit("CARTWHEEL_JUDGE_TRACE_SOURCE must point at analysis/state/hw5_trace_inputs.json")


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else ""
    if cmd in ("dev", "test"):
        _live_env()
    if cmd == "prepare":
        print(len(prepare_inputs()), "inputs written to", INPUTS.relative_to(ROOT))
    elif cmd == "split":
        print({k: len(v) for k, v in split_data().items()})
    elif cmd == "dev" and len(argv) == 2:
        print(json.dumps(run_development(MODE, argv[1]), indent=2, default=str))
    elif cmd == "test" and len(argv) == 2:
        print(json.dumps(run_test(argv[1]), indent=2, default=str))
    elif cmd == "metrics" and len(argv) in (2, 3):
        recompute_metrics(argv[1], argv[2] if len(argv) == 3 else "test")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
