"""HW4 Part B sampling.

Batch 1: 15 uniform random traces + 15 cluster representatives. Clustering uses
behavior features only (which tools a turn called, how many calls, first turn
or follow-up, reply length).

Batch 2: 10 traces per user role (shopper, merchant, support), uniform random
within each role, excluding traces already in another batch. The role was
chosen as the dimension before any batch 1 trace was read.

Neither batch reads outcomes, the answer key, the scenario group, modes, or
citation flags, so no trace is chosen because something predicts it fails.

    uv run python -m analysis.review_app.sampling                     # batch 1 dry run
    uv run python -m analysis.review_app.sampling --batch 2           # batch 2 dry run
    uv run python -m analysis.review_app.sampling --batch 2 --write   # save batch 2
"""

from __future__ import annotations

import argparse
import math
import random
from collections import Counter
from datetime import datetime, timezone

from analysis.helpers.selection import _kmeans, _standardize

from . import data, store

SEED = 20261103
N_UNIFORM = 15
N_CLUSTERS = 15
N_STARTS = 10  # k-means restarts from seeds SEED..SEED+9; the lowest-inertia fit wins
FIT: dict = {}
POOL = "final-run traces (support- scenarios), one trace per turn"

SEED_B2 = 20261104
ROLES = ("shopper", "merchant", "support")
N_PER_ROLE = 10


def turn_rows() -> tuple[list[dict], list[str]]:
    """One row per trace with its behavior features."""
    data.load_env()
    raw, _src = data.load_raw()
    convs, _ctx = data.build_conversations(raw)
    tools = sorted({n for c in convs for t in c["turns"] for n in t["tool_names"]})
    rows = []
    for c in convs:
        for t in c["turns"]:
            calls = [b for b in t["blocks"] if b["kind"] == "tool"]
            reply = " ".join(b.get("text", "") for b in t["blocks"] if b["kind"] == "reply")
            called = {b["name"] for b in calls}
            rows.append({
                "trace_id": t["trace_id"],
                "scenario_id": c["scenario_id"],
                "role": c["role"],
                "turn": t["number"],
                "tools": sorted(called),
                "n_calls": len(calls),
                "reply_chars": len(reply),
                "vector": [1.0 if n in called else 0.0 for n in tools]
                + [float(len(calls)), 1.0 if t["number"] > 1 else 0.0, math.log1p(len(reply))],
            })
    rows.sort(key=lambda r: r["trace_id"])
    return rows, tools


def describe(members: list[dict]) -> str:
    """Short behavior summary of a cluster: its most common tool set."""
    sets = Counter(" + ".join(r["tools"]) or "no tools" for r in members)
    top, k = sets.most_common(1)[0]
    calls = sorted(r["n_calls"] for r in members)
    followups = sum(r["turn"] > 1 for r in members)
    return (f"n={len(members)}; mostly {top} ({k}/{len(members)}); "
            f"calls median {calls[len(calls) // 2]}; {followups} follow-up turns")


def inertia(vectors: list[list[float]], assign: list[int]) -> float:
    """Total squared distance from each trace to its cluster centroid."""
    total = 0.0
    for c in set(assign):
        idx = [i for i, a in enumerate(assign) if a == c]
        cen = [sum(vectors[i][d] for i in idx) / len(idx) for d in range(len(vectors[0]))]
        total += sum(sum((a - b) ** 2 for a, b in zip(vectors[i], cen)) for i in idx)
    return total


def best_kmeans(vectors: list[list[float]]) -> list[int]:
    """Run k-means from N_STARTS seeded starts; keep the lowest-inertia fit."""
    global FIT
    runs = []
    for s in range(N_STARTS):
        assign = _kmeans(vectors, k=N_CLUSTERS, seed=SEED + s)
        runs.append((inertia(vectors, assign), SEED + s, assign))
    best = min(runs, key=lambda r: (r[0], r[1]))
    FIT = {"start_seeds": [r[1] for r in runs], "inertias": [round(r[0], 1) for r in runs],
           "chosen_seed": best[1], "chosen_inertia": round(best[0], 1)}
    return best[2]


def select(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    rng = random.Random(SEED)
    uniform = rng.sample(rows, N_UNIFORM)
    taken = {r["trace_id"] for r in uniform}

    vectors = _standardize([r["vector"] for r in rows])
    assign = best_kmeans(vectors)
    clusters = []
    for c in sorted(set(assign)):
        idx = [i for i, a in enumerate(assign) if a == c]
        centroid = [sum(vectors[i][d] for i in idx) / len(idx) for d in range(len(vectors[0]))]
        dist = lambda i: (sum((a - b) ** 2 for a, b in zip(vectors[i], centroid)), rows[i]["trace_id"])
        ordered = sorted(idx, key=dist)
        rep = next((rows[i] for i in ordered if rows[i]["trace_id"] not in taken), None)
        clusters.append({"cluster": c, "members": [rows[i] for i in idx], "rep": rep})
    reps = [cl for cl in clusters if cl["rep"]]
    return uniform, clusters, reps


def label(r: dict) -> str:
    return f"{r['scenario_id']} T{r['turn']}"


def manifest_batches(uniform, reps, tools) -> list[dict]:
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    common = {"part": "B", "batch": 1, "seed": SEED, "pool": POOL, "created": created}
    return [
        {"id": "b1-uniform", "method": "uniform random over traces", **common,
         "traces": [{"trace_id": r["trace_id"], "reason": "uniform random pick"} for r in uniform]},
        {"id": "b1-cluster",
         "method": f"k-means (k={N_CLUSTERS}) over standardized behavior features, best of "
                   f"{N_STARTS} seeded starts by inertia; representative = member nearest "
                   "the centroid, excluding b1-uniform",
         "features": [f"called:{n}" for n in tools] + ["tool_call_count", "is_followup_turn", "log_reply_chars"],
         "kmeans_fit": FIT,
         **common,
         "traces": [{"trace_id": cl["rep"]["trace_id"],
                     "reason": f"cluster {cl['cluster']} representative ({describe(cl['members'])})"}
                    for cl in reps]},
    ]


def select_by_role(rows: list[dict], exclude: set[str]) -> dict[str, list[dict]]:
    """N_PER_ROLE uniform picks per role from traces not in another batch.

    One generator seeded with SEED_B2 draws the roles in ROLES order, each from
    that role's remaining traces sorted by trace id, so the draw is repeatable.
    """
    rng = random.Random(SEED_B2)
    picks = {}
    for role in ROLES:
        pool = [r for r in rows if r["role"] == role and r["trace_id"] not in exclude]
        picks[role] = rng.sample(pool, min(N_PER_ROLE, len(pool)))
    return picks


def batch2(write: bool) -> None:
    rows, _tools = turn_rows()
    doc = store.read_doc("sample_manifest.json")
    others = [b for b in doc.get("batches", []) if b.get("batch") != 2]
    exclude = {t["trace_id"] for b in others for t in b.get("traces", [])}
    pool_counts = {role: sum(r["role"] == role and r["trace_id"] not in exclude for r in rows) for role in ROLES}
    picks = select_by_role(rows, exclude)
    print(f"pool after excluding {len(exclude)} traces in other batches: "
          + ", ".join(f"{k} {v}" for k, v in pool_counts.items()))
    for role in ROLES:
        print(f"\n{role.upper()} ({len(picks[role])}, seed {SEED_B2}):")
        for r in sorted(picks[role], key=label):
            print(f"  {label(r):<22} {' + '.join(r['tools']) or 'no tools'}")
    chosen = [r["trace_id"] for role in ROLES for r in picks[role]]
    print(f"\ntotal {len(chosen)}; distinct {len(set(chosen))}; overlap with other batches: {len(set(chosen) & exclude)}")
    if not write:
        print("\ndry run: nothing written (pass --write to save)")
        return
    entry = {
        "id": "b2-role", "part": "B", "batch": 2,
        "method": f"stratified by user role, {N_PER_ROLE} per role; uniform random within each "
                  "role over sorted trace ids, roles drawn in order " + ", ".join(ROLES)
                  + "; excludes traces in other batches",
        "dimension": "user_role", "dimension_chosen": "2026-11-03, before reading any batch 1 trace",
        "seed": SEED_B2, "pool": POOL, "pool_counts_after_exclusion": pool_counts,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "traces": [{"trace_id": r["trace_id"], "reason": f"user role: {role}"}
                   for role in ROLES for r in picks[role]],
    }
    with store.LOCK:
        doc = store.read_doc("sample_manifest.json")
        batches = doc.get("batches", [])
        idx = next((i for i, b in enumerate(batches) if b.get("batch") == 2), None)
        if idx is None:
            batches.append(entry)
        else:
            batches[idx] = entry
        doc["batches"] = batches
        store.write_doc("sample_manifest.json", doc)
    print("\nwrote b2-role to sample_manifest.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--batch", type=int, choices=(1, 2), default=1)
    ap.add_argument("--write", action="store_true", help="save the batch to sample_manifest.json")
    args = ap.parse_args()
    if args.batch == 2:
        return batch2(args.write)

    rows, tools = turn_rows()
    uniform, clusters, reps = select(rows)
    print(f"pool: {len(rows)} traces; tools seen: {', '.join(tools)}\n")
    print(f"UNIFORM ({len(uniform)}, seed {SEED}):")
    for r in sorted(uniform, key=label):
        print(f"  {label(r):<22} {' + '.join(r['tools']) or 'no tools'}")
    print(f"\nCLUSTERS ({len(clusters)}):")
    for cl in sorted(clusters, key=lambda c: -len(c["members"])):
        rep = label(cl["rep"]) if cl["rep"] else "(all members already uniform picks)"
        print(f"  c{cl['cluster']:<2} {describe(cl['members'])}\n       rep: {rep}")
    overlap = {r["trace_id"] for r in uniform} & {cl["rep"]["trace_id"] for cl in reps}
    print(f"\nrepresentatives: {len(reps)}; overlap with uniform: {len(overlap)}")

    if not args.write:
        print("\ndry run: nothing written (pass --write to save)")
        return
    doc = store.read_doc("sample_manifest.json")
    existing = [b for b in doc.get("batches", []) if b.get("batch") != 1]
    doc["batches"] = manifest_batches(uniform, reps, tools) + existing
    store.write_doc("sample_manifest.json", doc)
    print("\nwrote batch 1 to sample_manifest.json")


if __name__ == "__main__":
    main()
