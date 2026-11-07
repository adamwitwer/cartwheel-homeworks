"""HW4 Part B sampling.

Batch 1: 15 uniform random traces + 15 cluster representatives. Clustering uses
behavior features only (which tools a turn called, how many calls, first turn
or follow-up, reply length).

Batch 2: 10 traces per user role (shopper, merchant, support), uniform random
within each role, excluding traces already in another batch. The role was
chosen as the dimension before any batch 1 trace was read.

Neither batch reads outcomes, the answer key, the scenario group, modes, or
citation flags, so no trace is chosen because something predicts it fails.

Batch 3: 25 traces from depth searches for the candidate modes. Each query
matches the situation in which a mode could occur (for example a product
search that returned as many results as its limit), not the failure, so the
results include close negatives. See QUERIES_B3.

    uv run python -m analysis.review_app.sampling                     # batch 1 dry run
    uv run python -m analysis.review_app.sampling --batch 2           # batch 2 dry run
    uv run python -m analysis.review_app.sampling --batch 2 --write   # save batch 2
    uv run python -m analysis.review_app.sampling --batch 3           # batch 3 dry run
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


# ------------------------------------------------------------------ batch 3
# Depth searches. Each query matches the situation in which a candidate mode
# could occur (a trigger), never the failure itself, so a query returns both
# possible positives and close negatives. Queries run in order; each excludes
# traces already in a batch or picked by an earlier query.

SEED_B3 = 20261105
N_B3 = 25
DQ_TYPES = ("dq-order-reversed-dates", "dq-order-missing-delivery-date", "dq-order-store-mismatch",
            "dq-product-invalid-price", "dq-product-missing-title")


def _res(block: dict) -> dict:
    return block.get("result") if isinstance(block.get("result"), dict) else {}


def _searches(row: dict) -> list[dict]:
    return [b for b in row["calls"] if b["name"] == "search_products" and _res(b).get("ok")]


def q_search_at_limit(row: dict) -> bool:
    return any(_res(b).get("count") == ((b.get("arguments") or {}).get("limit") or 5) for b in _searches(row))


def q_repeated_title(row: dict) -> bool:
    for b in _searches(row):
        titles = [p.get("title") for p in _res(b).get("products", [])]
        if len(titles) != len(set(titles)):
            return True
    return False


def q_order_list(row: dict) -> bool:
    return any(b["name"] in ("list_my_orders", "find_order") and len(_res(b).get("orders", [])) >= 2
               for b in row["calls"])


def q_required_action(row: dict) -> bool:
    return row["tuple"].get("intent") in ("refund", "account_change")


def q_decision(row: dict) -> bool:
    return any(_res(b).get("error") in ("permission_denied", "not_eligible") or _res(b).get("eligible") is False
               or b["name"] == "escalate_to_human" for b in row["calls"])


def q_policy(row: dict) -> bool:
    pol = str(row["tuple"].get("applicable_policy") or "")
    return row["tuple"].get("intent") == "policy_question" or pol.startswith("store-") or pol == "cw-restocking-fees"


# (id, description, target mode, predicate or None for the per-type data-quality draw, quota)
QUERIES_B3 = [
    ("Q1", "search_products returned as many results as its limit", "truncated_search_presented_as_complete", q_search_at_limit, 6),
    ("Q2", "search result contains a repeated title", "same_title_listing_not_distinguished", q_repeated_title, 4),
    ("Q3", "data-quality scenario, one per case type", "inconsistent_record_not_escalated", None, len(DQ_TYPES)),
    ("Q4", "list_my_orders or find_order returned 2+ orders", "reply_contradicts_tool_result", q_order_list, 3),
    ("Q5", "refund or account-change request", "asks_instead_of_acting", q_required_action, 3),
    ("Q6", "tool returned permission_denied or not eligible, or the agent escalated", "reply_omits_decision_basis", q_decision, 2),
    ("Q7", "policy question or store-specific policy", "policy_claim_without_citation / policy_answer_wrong_or_incomplete", q_policy, 2),
]


def trigger_rows() -> list[dict]:
    """One row per trace with the fields the batch 3 triggers read: tool calls
    and results, plus the scenario's intent, applicable policy, and data-quality
    case (scenario design, not outcomes or answer keys)."""
    data.load_env()
    raw, _src = data.load_raw()
    convs, _ctx = data.build_conversations(raw)
    rows = []
    for c in convs:
        if not (c["scenario_id"] or "").startswith(data.SCENARIO_PREFIX):
            continue
        for t in c["turns"]:
            rows.append({
                "trace_id": t["trace_id"], "scenario_id": c["scenario_id"], "role": c["role"],
                "turn": t["number"], "tools": sorted(set(t["tool_names"])),
                "calls": [b for b in t["blocks"] if b["kind"] == "tool"],
                "tuple": c["scenario"]["tuple"] or {}, "dq": c["scenario"]["data_quality_case_id"],
            })
    rows.sort(key=lambda r: r["trace_id"])
    return rows


def select_b3(rows: list[dict], exclude: set[str]) -> tuple[list[tuple[str, dict, str]], dict[str, int]]:
    """Run the queries in order. Spare Q1/Q2 slots go to Q4 so the total is N_B3."""
    rng = random.Random(SEED_B3)
    taken = set(exclude)
    picks: list[tuple[str, dict, str]] = []
    pools: dict[str, int] = {}
    spare = 0
    for qid, desc, _mode, pred, quota in QUERIES_B3:
        if qid == "Q4":
            quota += spare
        if pred is None:
            for dq in DQ_TYPES:
                pool = [r for r in rows if r["dq"] == dq and r["trace_id"] not in taken]
                pools[f"{qid} {dq}"] = len(pool)
                for r in rng.sample(pool, min(1, len(pool))):
                    picks.append((qid, r, f"{desc} ({dq})"))
                    taken.add(r["trace_id"])
            continue
        pool = [r for r in rows if r["trace_id"] not in taken and pred(r)]
        pools[qid] = len(pool)
        chosen = rng.sample(pool, min(quota, len(pool)))
        if qid in ("Q1", "Q2"):
            spare += quota - len(chosen)
        for r in chosen:
            picks.append((qid, r, desc))
            taken.add(r["trace_id"])
    return picks, pools


def batch3(write: bool) -> None:
    rows = trigger_rows()
    doc = store.read_doc("sample_manifest.json")
    others = [b for b in doc.get("batches", []) if b.get("batch") != 3]
    exclude = {t["trace_id"] for b in others for t in b.get("traces", [])}
    picks, pools = select_b3(rows, exclude)
    print(f"pool after excluding {len(exclude)} traces in other batches: "
          f"{sum(r['trace_id'] not in exclude for r in rows)} (seed {SEED_B3})")
    print("pool per query (after earlier queries' picks): " + ", ".join(f"{k} {v}" for k, v in pools.items()))
    for qid, desc, mode, _pred, _quota in QUERIES_B3:
        mine = [(r, why) for q, r, why in picks if q == qid]
        print(f"\n{qid} ({len(mine)}) {desc}  [for {mode}]")
        for r, why in sorted(mine, key=lambda x: label(x[0])):
            extra = f"  {r['dq']}" if r["dq"] and qid == "Q3" else ""
            print(f"  {label(r):<22} {r['role']:<9} {' + '.join(r['tools']) or 'no tools'}{extra}")
    chosen = [r["trace_id"] for _q, r, _w in picks]
    print(f"\ntotal {len(chosen)}; distinct {len(set(chosen))}; overlap with other batches: {len(set(chosen) & exclude)}")
    print("roles: " + ", ".join(f"{k} {v}" for k, v in Counter(r["role"] for _q, r, _w in picks).items()))
    if not write:
        print("\ndry run: nothing written (pass --write to save)")
        return
    entry = {
        "id": "b3-depth", "part": "B", "batch": 3,
        "method": "depth searches for candidate modes and close negatives: each query matches the situation in "
                  "which a mode could occur (tool results, scenario intent, applicable policy, or data-quality "
                  "case), not the failure; queries run in order, each excluding earlier picks; uniform random "
                  "within a query's pool when it exceeds the quota",
        "queries": [{"id": q, "trigger": d, "target_mode": m, "quota": n} for q, d, m, _p, n in QUERIES_B3],
        "seed": SEED_B3, "pool": POOL, "pool_counts": pools,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "traces": [{"trace_id": r["trace_id"], "reason": f"depth search {q}: {why}"} for q, r, why in picks],
    }
    with store.LOCK:
        doc = store.read_doc("sample_manifest.json")
        batches = [b for b in doc.get("batches", []) if b.get("batch") != 3]
        doc["batches"] = batches + [entry]
        store.write_doc("sample_manifest.json", doc)
    print("\nwrote b3-depth to sample_manifest.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--batch", type=int, choices=(1, 2, 3), default=1)
    ap.add_argument("--write", action="store_true", help="save the batch to sample_manifest.json")
    args = ap.parse_args()
    if args.batch == 2:
        return batch2(args.write)
    if args.batch == 3:
        return batch3(args.write)

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
