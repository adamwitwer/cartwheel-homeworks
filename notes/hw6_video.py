"""Read-only views of the HW6 results for the video.

Every command is free: no model calls, no network, and nothing is written.

    uv run python notes/hw6_video.py cases
    uv run python notes/hw6_video.py baseline e-005
    uv run python notes/hw6_video.py passk
    uv run python notes/hw6_video.py trial .harbor/ci-run2/e-005__PjhEtYv
    uv run python notes/hw6_video.py part-e

`baseline` reads the local job in .harbor/jobs/hw6-baseline-<case>; `trial`
reads one downloaded trial directory (run 2's job artifact is in
.harbor/ci-run2). Both directories are gitignored and exist only on the
machine that ran them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def cases() -> None:
    """One line per case: id, mode, classification, and HW4 source trace."""
    rows = [json.loads(line) for line in (ROOT / "eval_cases/cases.jsonl").open() if line.strip()]
    for case in rows:
        rate = case.get("baseline_pass_rate", "")
        source = case["initial_state"]["assumes"].split(".")[0].replace("Based on HW4 trace ", "")
        checks = ", ".join(check["check"] for check in case["expected"].get("checks", []))
        judges = ", ".join(case["expected"].get("judges", {}))
        evaluator = checks + (f" + judge {judges}" if judges else "")
        print(f"{case['id']}  {case['mode']:<30} {case['kind']:<10} {str(rate):<4} {source}  {evaluator}")
    modes = sorted({case["mode"] for case in rows})
    kinds = [case["kind"] for case in rows]
    print(f"\n{len(rows)} cases, {len(modes)} modes; "
          f"{kinds.count('regression')} regression, {kinds.count('capability')} capability")


def _tools(transcript: dict) -> list[list[str]]:
    return [[call["name"] for call in turn["tool_calls"]] for turn in transcript["turns"]]


def baseline(case_id: str) -> None:
    """Each baseline trial's result and the tools it called, turn by turn."""
    job = ROOT / ".harbor/jobs" / f"hw6-baseline-{case_id}"
    passes = 0
    trials = sorted(job.glob(f"{case_id}__*/"))
    for trial in trials:
        reward = json.loads((trial / "result.json").read_text())["verifier_result"]["rewards"]["reward"]
        transcript = json.loads((trial / "agent/cartwheel-result.json").read_text())["transcript"]
        passes += reward >= 1
        print(f"{trial.name}  {'PASS' if reward >= 1 else 'FAIL'}  tools per turn: {_tools(transcript)}")
    kind = "regression" if passes == len(trials) == 5 else f"capability, baseline_pass_rate {passes / len(trials):.1f}"
    print(f"\n{case_id}: passed {passes} of {len(trials)} -> {kind}")


def passk() -> None:
    """pass@k and pass^k on three of the baselines (n = 5)."""
    from tests.eval.passk import case_passes, pass_at_k, pass_hat_k

    for case_id, kind, c in (("e-005", "regression", 5), ("e-006", "capability", 4), ("e-004", "capability", 2)):
        print(f"{case_id} {c}/5  pass@1 {pass_at_k(5, c, 1):.2f}  pass@3 {pass_at_k(5, c, 3):.2f}  "
              f"pass^3 {pass_hat_k(5, c, 3):.2f}  pass^5 {pass_hat_k(5, c, 5):.2f}")
    print()
    print("case_passes('regression', 4, 5):", case_passes("regression", 4, 5))
    print("case_passes('capability', 2, 5, 0.4):", case_passes("capability", 2, 5, 0.4))


def trial(path: str) -> None:
    """One trial's reward, tools, and final reply."""
    directory = ROOT / path
    reward = json.loads((directory / "result.json").read_text())["verifier_result"]["rewards"]["reward"]
    transcript = json.loads((directory / "agent/cartwheel-result.json").read_text())["transcript"]
    print(f"{directory.name}  reward {reward}  tools per turn: {_tools(transcript)}\n")
    print(transcript["final_reply"])


def part_e() -> None:
    """The 15-run analysis of e-004 at n = 5, 10, and 15."""
    analysis = json.loads((ROOT / "eval_results/e-004-15.json").read_text())
    print(f"{analysis['case_id']}  model {analysis['model']}  order: {analysis['trial_order']}")
    print("rewards in order:", " ".join(str(r) for r in analysis["rewards"]), "\n")
    for row in analysis["comparisons"]:
        metrics = "  ".join(f"pass@{k} {v:.3f}" for k, v in row["pass_at_k"].items())
        print(f"n={row['n']:>2}  passes={row['successes']:>2}  {metrics}")


COMMANDS = {"cases": cases, "baseline": baseline, "passk": passk, "trial": trial, "part-e": part_e}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit(__doc__)
    COMMANDS[sys.argv[1]](*sys.argv[2:])
