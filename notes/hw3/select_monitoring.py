"""Select the 50 monitoring scenarios that Homework 7 reruns after the agent changes.

Proportional to the final set: 35 coverage (each intent's share, then each role's share
within the intent, at least one per role the intent has) and 15 challenge (one per
damaged record, then each difficulty's share). Drawn with a fixed seed, so the selection
is reproducible.

Run from the repository root:  uv run python notes/hw3/select_monitoring.py
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

SCENARIOS = Path("scenarios/support_scenarios.jsonl")
OUT = Path("scenarios/monitoring_scenarios.jsonl")
ROLES = ("shopper", "merchant", "support")

rng = random.Random(20261026)
rows = [json.loads(line) for line in SCENARIOS.read_text().splitlines() if line.strip()]


def allocate(sizes: dict, total: int, minimum: int = 0) -> dict:
    """Largest-remainder shares of `total`, proportional to `sizes`. Each key first gets
    `minimum` when `total` allows it for every key; the rest is split by share."""
    floor = minimum if total >= minimum * len(sizes) else 0
    rest, n = total - floor * len(sizes), sum(sizes.values())
    exact = {k: rest * v / n for k, v in sizes.items()}
    share = {k: floor + int(x) for k, x in exact.items()}
    for k in sorted(exact, key=lambda k: exact[k] % 1, reverse=True)[: total - sum(share.values())]:
        share[k] += 1
    assert sum(share.values()) == total, (sizes, total, share)
    return share


picked: list[dict] = []

# Coverage: intent shares, then role shares within each intent.
coverage = [r for r in rows if r["scenario_group"] == "coverage"]
by_intent = defaultdict(list)
for r in coverage:
    by_intent[r["tuple"]["intent"]].append(r)
for intent, quota in allocate({i: len(v) for i, v in by_intent.items()}, 35).items():
    cells = defaultdict(list)
    for r in by_intent[intent]:
        cells[r["tuple"]["role"]].append(r)
    for role, k in allocate({role: len(v) for role, v in cells.items()}, quota, minimum=1).items():
        picked += rng.sample(cells[role], k)

# Challenge: one per damaged record, then the other difficulties by share.
challenge = [r for r in rows if r["scenario_group"] == "challenge"]
damaged = defaultdict(list)
for r in challenge:
    if r["data_quality_case_id"]:
        damaged[r["data_quality_case_id"]].append(r)
for case in sorted(damaged):
    picked.append(rng.choice(damaged[case]))
by_difficulty = defaultdict(list)
for r in challenge:
    if not r["data_quality_case_id"]:
        by_difficulty[r["tuple"]["difficulty"]].append(r)
for difficulty, k in allocate({d: len(v) for d, v in by_difficulty.items()}, 15 - len(damaged), minimum=1).items():
    picked += rng.sample(by_difficulty[difficulty], k)

order = {r["id"]: i for i, r in enumerate(rows)}
picked.sort(key=lambda r: order[r["id"]])
assert len(picked) == 50 and len({r["id"] for r in picked}) == 50
assert Counter(r["scenario_group"] for r in picked) == {"coverage": 35, "challenge": 15}
assert {r["tuple"]["role"] for r in picked} == set(ROLES)
assert {r["tuple"]["role"] for r in picked if r["scenario_group"] == "challenge"} == set(ROLES)
assert {r["tuple"]["intent"] for r in picked} == {r["tuple"]["intent"] for r in rows}

OUT.write_text("".join(json.dumps(r) + "\n" for r in picked))
for field in ("role", "intent", "difficulty", "turn_count"):
    print(f"{field}: {dict(sorted(Counter(r['tuple'][field] for r in picked).items()))}")
print("groups:", dict(Counter(r["scenario_group"] for r in picked)))
print("damaged records:", sorted(r["data_quality_case_id"] for r in picked if r["data_quality_case_id"]))
print("challenge roles:", dict(Counter(r["tuple"]["role"] for r in picked if r["scenario_group"] == "challenge")))
print(f"wrote {len(picked)} scenarios to {OUT}")
