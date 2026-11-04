"""Load Cartwheel scenario traces and assemble them into conversations.

Langfuse stores one trace per user turn. The review app needs one record per
conversation, so this module groups traces by ``cartwheel.session_id``, orders
the turns by timestamp, and turns each trace's observations into readable
blocks: the customer's message, the agent's notes before tool calls, each tool
call with its result, and the final reply.

It also joins the material a reviewer needs beside the trace but that Langfuse
does not hold: the scenario's answer key (``scenarios/support_scenarios.jsonl``),
the policy corpus (``data/policies``), SPEC.md, and the tool definitions the
model saw.

Sources, in order of preference:

1. ``.cache/raw_traces.json``, written after the last live load.
2. Live Langfuse (``LANGFUSE_*`` env), which refreshes the cache.
3. The Module 1 export ``traces/support_traces.json``, used only when Langfuse
   is unavailable. The app shows a banner with the reason.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
RAW_CACHE = CACHE_DIR / "raw_traces.json"
EXPORT = REPO / "traces" / "support_traces.json"
SCENARIOS = REPO / "scenarios" / "support_scenarios.jsonl"
POLICY_DIR = REPO / "data" / "policies"
SPEC = REPO / "SPEC.md"
WORLD_DB = REPO / "data" / "cartwheel.db"


def load_names() -> dict[str, Any]:
    """Store and product names from the seeded world, for reviewer lookups.

    Several tools return only ``store_id`` / ``product_id``; the app shows these
    names beside the ids, marked as a reviewer lookup the agent did not see.
    The database is opened read-only. Names are fixed by the seed, so they
    match what the traced runs saw even if order statuses have changed since.
    """
    import sqlite3

    if not WORLD_DB.exists():
        return {"stores": {}, "products": {}}
    con = sqlite3.connect(f"file:{WORLD_DB}?mode=ro", uri=True)
    try:
        stores = {str(i): n for i, n in con.execute("SELECT id, name FROM stores")}
        products = {
            str(i): {"title": t, "store_id": s}
            for i, s, t in con.execute("SELECT id, store_id, title FROM products")
        }
    finally:
        con.close()
    return {"stores": stores, "products": products}

# Final-run scenarios only; the HW3 pilot used the "pilot-" prefix.
SCENARIO_PREFIX = "support-"

# The seeded world's "today" (seed/generate.py WORLD_ASOF). Tool results carry
# it as ``as_of``; the header shows it so date reasoning is checked against the
# world, not the calendar.
WORLD_ASOF = "2026-07-01"

POLICY_ID_RE = re.compile(r"\b(cw-[a-z]+(?:-[a-z]+)*|store-[a-z]+(?:-[a-z]+)*-policy)\b")

# Result fields that usually decide the agent's next move. The UI renders them
# in bold so the evidence for "eligible", "denied", or "failed" is easy to find.
DECISION_KEYS = {
    "ok", "error", "reason", "eligible", "refund_eligible", "status",
    "policy_id", "permission_denied", "last_day_to_return", "days_since_delivery",
    "return_window_days", "window_source", "as_of", "count",
}


# ---------------------------------------------------------------------------
# environment
# ---------------------------------------------------------------------------


def load_env() -> None:
    """Load ``.env`` into the process environment without overriding it.

    Values are never printed. Only variables not already set are added.
    """
    path = REPO / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def langfuse_configured() -> bool:
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY")
        and os.environ.get("LANGFUSE_SECRET_KEY")
        and os.environ.get("LANGFUSE_HOST")
    )


def langfuse_client() -> Any:
    from langfuse import Langfuse

    return Langfuse()


# ---------------------------------------------------------------------------
# raw trace loading
# ---------------------------------------------------------------------------


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if hasattr(value, "dict"):
        return value.dict(by_alias=True)
    return value


def _attrs(record: dict[str, Any]) -> dict[str, Any]:
    meta = record.get("metadata") or {}
    attrs = meta.get("attributes") if isinstance(meta, dict) else None
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs)
        except ValueError:
            attrs = None
    return attrs if isinstance(attrs, dict) else {}


def scenario_id_of(record: dict[str, Any]) -> str | None:
    return record.get("cartwheel_scenario_id") or _attrs(record).get("cartwheel.scenario_id")


def fetch_live_raw() -> list[dict[str, Any]]:
    """Fetch every final-run scenario trace from Langfuse (read-only)."""
    lf = langfuse_client()
    summaries: list[Any] = []
    page = 1
    while True:
        resp = lf.api.trace.list(page=page, limit=100)
        batch = list(resp.data or [])
        summaries.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    def get(trace_id: str) -> dict[str, Any]:
        return _dump(lf.api.trace.get(trace_id))

    with ThreadPoolExecutor(max_workers=8) as pool:
        full = list(pool.map(get, [str(s.id) for s in summaries]))
    keep = [r for r in full if (scenario_id_of(r) or "").startswith(SCENARIO_PREFIX)]
    keep.sort(key=lambda r: str(r.get("timestamp")))
    return keep


def load_raw(refresh: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return raw traces and a description of where they came from."""
    if RAW_CACHE.exists() and not refresh:
        cached = json.loads(RAW_CACHE.read_text())
        return cached["traces"], {
            "source": "langfuse-cache",
            "fetched_at": cached.get("fetched_at"),
            "note": "Cached from Langfuse. Restart with --refresh to reload.",
        }
    reason = None
    if langfuse_configured():
        try:
            traces = fetch_live_raw()
            CACHE_DIR.mkdir(exist_ok=True)
            fetched = datetime.now(timezone.utc).isoformat()
            RAW_CACHE.write_text(json.dumps({"fetched_at": fetched, "traces": traces}, default=str))
            return traces, {"source": "langfuse", "fetched_at": fetched, "note": "Loaded live from Langfuse."}
        except Exception as exc:  # network or auth failure: fall back, and say why
            reason = f"Langfuse load failed: {type(exc).__name__}: {exc}"
    else:
        reason = "LANGFUSE_* environment variables are not set."
    export = json.loads(EXPORT.read_text())
    traces = [t for t in export["traces"] if (scenario_id_of(t) or "").startswith(SCENARIO_PREFIX)]
    return traces, {
        "source": "offline-export",
        "fetched_at": export.get("exported_at"),
        "note": f"Offline export traces/support_traces.json. Reason: {reason}",
    }


# ---------------------------------------------------------------------------
# trace -> blocks
# ---------------------------------------------------------------------------


def _parts_text(messages: Any) -> str:
    out: list[str] = []
    for msg in messages if isinstance(messages, list) else []:
        for part in (msg or {}).get("parts") or []:
            if isinstance(part, dict) and part.get("type") == "text" and part.get("content"):
                out.append(str(part["content"]))
    return "\n".join(out)


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _turn_blocks(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert one trace into ordered display blocks plus per-turn extras."""
    trace_id = str(raw["id"])
    blocks: list[dict[str, Any]] = []

    def add(kind: str, **fields: Any) -> None:
        blocks.append({"key": f"{trace_id}:{len(blocks)}", "trace_id": trace_id, "kind": kind, **fields})

    user_text = _parts_text(raw.get("input"))
    add("user", text=user_text)

    observations = sorted(
        (o for o in raw.get("observations") or [] if isinstance(o, dict)),
        key=lambda o: str(o.get("startTime") or o.get("start_time") or ""),
    )
    system_prompt = None
    tool_schemas: list[dict[str, Any]] = []
    models: list[str] = []
    text_blocks: list[int] = []
    for obs in observations:
        kind = obs.get("type")
        if kind == "GENERATION":
            inp = obs.get("input") if isinstance(obs.get("input"), dict) else {}
            if system_prompt is None:
                for msg in inp.get("messages") or []:
                    if msg.get("role") == "system":
                        system_prompt = _parts_text([msg])
                        break
            if not tool_schemas and isinstance(inp.get("tools"), list):
                tool_schemas = inp["tools"]
            if obs.get("model") and obs["model"] not in models:
                models.append(obs["model"])
            out = obs.get("output") if isinstance(obs.get("output"), list) else []
            calls_tool = any(
                isinstance(p, dict) and p.get("type") == "tool_call"
                for m in out for p in (m or {}).get("parts") or []
            )
            text = _parts_text(out)
            if text.strip():
                add("note" if calls_tool else "reply", text=text)
                text_blocks.append(len(blocks) - 1)
        elif kind == "TOOL":
            attrs = _attrs(obs)
            result = _maybe_json(obs.get("output"))
            ok = result.get("ok") if isinstance(result, dict) else None
            add(
                "tool",
                name=obs.get("name") or attrs.get("gen_ai.tool.name") or "tool",
                arguments=_maybe_json(obs.get("input")),
                result=result,
                ok=ok,
                error=result.get("error") if isinstance(result, dict) else None,
                permission_denied=str(attrs.get("cartwheel.permission_denied", "")).lower() == "true",
            )

    # The trace output is the reply the customer received. Make sure exactly
    # that text is the turn's reply, even if a generation produced it oddly.
    final = _parts_text(raw.get("output"))
    replies = [i for i in text_blocks if blocks[i]["kind"] == "reply"]
    if final.strip():
        match = next((i for i in reversed(text_blocks) if blocks[i]["text"].strip() == final.strip()), None)
        if match is None:
            add("reply", text=final)
        else:
            blocks[match]["kind"] = "reply"
            for i in replies:
                if i != match:
                    blocks[i]["kind"] = "note"
    extras = {"system_prompt": system_prompt, "tool_schemas": tool_schemas, "models": models}
    return blocks, extras


def _policy_ids(value: Any) -> set[str]:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return set(POLICY_ID_RE.findall(text or ""))


def _langfuse_url(raw: dict[str, Any]) -> str | None:
    host = (os.environ.get("LANGFUSE_HOST") or "http://localhost:3000").rstrip("/")
    path = raw.get("htmlPath")
    if path:
        return host + path
    if raw.get("projectId"):
        return f"{host}/project/{raw['projectId']}/traces/{raw['id']}"
    return None


# ---------------------------------------------------------------------------
# context: scenarios, policies, spec, tools
# ---------------------------------------------------------------------------


def load_scenarios() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in SCENARIOS.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["id"]] = row
    return out


def load_policies() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(POLICY_DIR.glob("*.md")):
        text = path.read_text()
        meta: dict[str, str] = {}
        body = text
        if text.startswith("---"):
            _, front, body = text.split("---", 2)
            for line in front.strip().splitlines():
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
        pid = meta.get("policy_id") or path.stem
        out[pid] = {
            "policy_id": pid,
            "title": meta.get("title", pid),
            "audience": meta.get("audience"),
            "body": body.strip(),
        }
    return out


def spec_tool_contracts() -> dict[str, dict[str, str]]:
    """Parse SPEC.md's tool tables into {tool: {id, inputs, effects, risk, success, failure}}."""
    contracts: dict[str, dict[str, str]] = defaultdict(dict)
    for line in SPEC.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[0].startswith("TOOL-"):
            name = cells[1].strip("`")
            contracts[name].update(id=cells[0], inputs=cells[2], effects=cells[3], risk=cells[4])
        elif len(cells) == 3 and cells[0].startswith("`"):
            name = cells[0].strip("`")
            contracts[name].update(success=cells[1], failure=cells[2])
    return dict(contracts)


# ---------------------------------------------------------------------------
# conversations
# ---------------------------------------------------------------------------


def build_conversations(raw_traces: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Group traces by session and return (conversations, shared context)."""
    scenarios = load_scenarios()
    policies = load_policies()
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in raw_traces:
        attrs = _attrs(raw)
        session = attrs.get("cartwheel.session_id") or f"no-session:{raw['id']}"
        by_session[session].append(raw)

    tool_schemas: dict[str, dict[str, Any]] = {}
    prompt_template_versions: set[str] = set()
    conversations: list[dict[str, Any]] = []
    for session_id, group in by_session.items():
        group.sort(key=lambda r: str(r.get("timestamp")))
        first_attrs = _attrs(group[0])
        scenario_id = scenario_id_of(group[0])
        retrieved: set[str] = set()
        turns: list[dict[str, Any]] = []
        system_prompt = None
        models: list[str] = []
        available: list[str] = []
        for number, raw in enumerate(group, start=1):
            blocks, extras = _turn_blocks(raw)
            system_prompt = system_prompt or extras["system_prompt"]
            for schema in extras["tool_schemas"]:
                name = schema.get("name") or (schema.get("function") or {}).get("name")
                tool_schemas.setdefault(name, schema)
                if name not in available:
                    available.append(name)
            models += [m for m in extras["models"] if m not in models]
            tool_blocks = [b for b in blocks if b["kind"] == "tool"]
            for block in tool_blocks:
                retrieved |= _policy_ids(block.get("result"))
            cited = set()
            for block in blocks:
                if block["kind"] in {"note", "reply"}:
                    found = _policy_ids(block["text"])
                    block["citations"] = [
                        {
                            "policy_id": pid,
                            "retrieved": pid in retrieved,
                            "known": pid in policies,
                        }
                        for pid in sorted(found)
                    ]
                    cited |= found
            prompt_template_versions.add(str(_attrs(raw).get("cartwheel.prompt_version")))
            turns.append(
                {
                    "trace_id": str(raw["id"]),
                    "number": number,
                    "timestamp": str(raw.get("timestamp")),
                    "latency": raw.get("latency"),
                    "langfuse_url": _langfuse_url(raw),
                    "tool_names": [b["name"] for b in tool_blocks],
                    "cited_policies": sorted(cited),
                    "blocks": blocks,
                }
            )
        scenario = scenarios.get(scenario_id or "", {})
        all_tools = [name for t in turns for name in t["tool_names"]]
        cited_all = sorted({p for t in turns for p in t["cited_policies"]})
        conversations.append(
            {
                "session_id": session_id,
                "scenario_id": scenario_id,
                "role": first_attrs.get("cartwheel.user_role"),
                "user_id": first_attrs.get("cartwheel.user_id"),
                "store_id": first_attrs.get("cartwheel.store_id"),
                "prompt_version": first_attrs.get("cartwheel.prompt_version"),
                "models": models,
                "system_prompt": system_prompt,
                "available_tools": available,
                "turns": turns,
                "summary": {
                    "turn_count": len(turns),
                    "tool_call_count": len(all_tools),
                    "tools": sorted(set(all_tools)),
                    "retrieved_policies": sorted(retrieved),
                    "cited_policies": cited_all,
                    "no_policy_retrieved": not retrieved,
                    "no_tools": not all_tools,
                    "unretrieved_citations": sorted(p for p in cited_all if p not in retrieved),
                },
                "scenario": {
                    "group": scenario.get("scenario_group"),
                    "tuple": scenario.get("tuple"),
                    "data_quality_case_id": scenario.get("data_quality_case_id"),
                    "opening_message": scenario.get("opening_message"),
                    "followups": scenario.get("followups"),
                    "expected": scenario.get("expected"),
                },
            }
        )
    conversations.sort(key=lambda c: (c["scenario_id"] or "", c["turns"][0]["timestamp"]))
    contracts = spec_tool_contracts()
    tools = []
    for name, schema in tool_schemas.items():
        tools.append(
            {
                "name": name,
                "description": schema.get("description") or (schema.get("function") or {}).get("description"),
                "parameters": schema.get("parameters") or (schema.get("function") or {}).get("parameters"),
                "contract": contracts.get(name, {}),
            }
        )
    context = {
        "policies": policies,
        "spec": SPEC.read_text(),
        "tools": tools,
        "world_asof": WORLD_ASOF,
        "decision_keys": sorted(DECISION_KEYS),
        "prompt_versions": sorted(prompt_template_versions),
        "names": load_names(),
    }
    return conversations, context
