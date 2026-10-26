"""Write user messages for a HW3 plan, then run an independent critic on each.

Reads a plan written by build_plan.py and writes scenario JSONL for the runner.
Following scenarios/skill/SKILL.md:
  - one model call per conversation, run concurrently in a bounded pool;
  - the writer and the critic see only each row's `generation` block (role, goal,
    user-visible facts, style, followup plan), never `expected` or `tuple`;
  - followups are written so they make sense whatever the agent replied.

These calls go straight to OpenAI and are not traced; they are not application runs.

Run from the repository root:
  uv run python notes/hw3/generate.py notes/hw3/pilot_plan.jsonl scenarios/pilot_scenarios.jsonl
Add --only ID [ID ...] to rewrite just those conversations and keep the rest of the output.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from observability.instrument import load_env

WRITER_MODEL = "gpt-4.1"
CRITIC_MODEL = "gpt-4.1"
WORKERS = 4

STYLES = {
    "neutral_conversational": "ordinary, polite chat; full sentences, nothing unusual",
    "terse_fragmentary": "very short fragments, little punctuation, no greetings",
    "typo_heavy": "types fast on a phone: several typos, missing apostrophes, lowercase",
    "confused_rambling": "unsure of the details, wanders and over-explains before getting to the point",
    "frustrated_impatient": "annoyed and in a hurry, blunt, may complain, but not abusive",
    "repetitive_pressuring": "repeats the request and pushes for a yes",
    "operational_shorthand": "staff-style shorthand, like a ticket note (\"#123 status?\", \"cx wants...\")",
    "requests_short_plain_answer": "explicitly asks for a short, plain answer",
}

# Final review, support-0182: shoppers copied the staff example ("cx wants...") and wrote
# about "the customer" instead of themselves.
SHOPPER_SHORTHAND = ("clipped shorthand, like a ticket note (\"#123 status?\", \"want refund\"), "
                     "but about their own order, in the first person")

ROLES = {
    "shopper": "a shopper who buys from stores on Cartwheel, an online marketplace",
    "merchant": "a merchant who runs a store on Cartwheel, an online marketplace",
    "support": "a member of Cartwheel's own support staff, using the assistant to help a customer",
}

WRITER_PROMPT = """You are simulating a real user typing into the Cartwheel support chat.
Write the user's messages for one conversation, as this person would type them.

Who: {role}
Goal: {goal}
What this person knows:
{facts}
Writing style: {style} ({style_desc})
Number of messages: {turns} (one opening message{followup_clause})
{plan}
Rules:
- Use only the facts above. Do not invent order numbers, prices, dates, or names.
- Do not state every fact; mention what a real person would.
- Never mention policy names or ids, rule numbers, tools, or the assistant's internals.
- Each later message must make sense no matter how the assistant replied. Do not
  answer questions the assistant may not have asked ("yes, go ahead", "thanks, that
  worked"); develop the same issue with a correction, a detail, or pushback instead.
- Keep the style in every message. Do not polish it.
- Keep each message short, like a chat message (usually one or two sentences).

Reply with JSON: {{"opening_message": "...", "followups": [...]}} with exactly {n_followups} followups."""

CRITIC_PROMPT = """You review one scripted user conversation for a support-chat simulation.
The user's messages were written in advance, before any assistant reply existed.

Who: {role}
Goal: {goal}
What this person knows:
{facts}
Writing style: {style} ({style_desc})
{plan}
Conversation (user messages only, in order):
{conversation}

Check for these problems:
1. Identifiers, amounts, dates, or names that are not in "What this person knows".
2. A later message that assumes a specific assistant reply (for example "yes, go ahead").
3. A stock or template opening ("Hi, I hope you can help...") or generic filler.
4. Language a real user would not write: policy names, rule numbers, internal terms.
5. Mentions of tools, traces, prompts, tests, or simulations.
6. The style is not followed, or a message is polished beyond the style.
7. A later message does not follow the plan above.

If there are problems, rewrite only the language to fix them. Keep the same goal, facts,
style, and number of messages. If there are none, return the messages unchanged.

Reply with JSON: {{"issues": ["..."], "opening_message": "...", "followups": [...]}}"""


def _context(gen: dict) -> dict:
    plan = gen["followup_plan"]
    return {
        "role": ROLES[gen["role"]],
        "goal": gen["goal"],
        "facts": "\n".join(f"- {fact}" for fact in gen["user_visible_facts"]),
        "style": gen["style"],
        "style_desc": SHOPPER_SHORTHAND if (gen["role"], gen["style"]) == ("shopper", "operational_shorthand")
        else STYLES[gen["style"]],
        "turns": 1 + len(plan),
        "n_followups": len(plan),
        "followup_clause": f", then {len(plan)} followup(s)" if plan else ", no followups",
        "plan": (
            "Plan for the followups:\n" + "\n".join(f"{i}. {step}" for i, step in enumerate(plan, start=1)) + "\n"
            if plan else ""
        ),
    }


def _ask(client: OpenAI, model: str, prompt: str, n_followups: int) -> dict:
    for _ in range(3):
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=1.0,
        )
        data = json.loads(response.choices[0].message.content)
        followups = data.get("followups")
        if (
            isinstance(data.get("opening_message"), str) and data["opening_message"].strip()
            and isinstance(followups, list) and len(followups) == n_followups
            and all(isinstance(f, str) and f.strip() for f in followups)
        ):
            return data
    raise RuntimeError(f"no well-formed reply after 3 tries: {data}")


def write(client: OpenAI, row: dict) -> dict:
    ctx = _context(row["generation"])
    return _ask(client, WRITER_MODEL, WRITER_PROMPT.format(**ctx), ctx["n_followups"])


def critique(client: OpenAI, row: dict, draft: dict) -> dict:
    ctx = _context(row["generation"])
    messages = [draft["opening_message"], *draft["followups"]]
    ctx["conversation"] = "\n".join(f"{i}. {m}" for i, m in enumerate(messages, start=1))
    return _ask(client, CRITIC_MODEL, CRITIC_PROMPT.format(**ctx), ctx["n_followups"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--only", nargs="+", default=None, help="rewrite only these scenario ids")
    args = parser.parse_args()

    load_env()
    client = OpenAI()
    rows = [json.loads(line) for line in args.plan.read_text().splitlines() if line.strip()]
    log_path = args.plan.with_name(args.plan.stem.replace("_plan", "") + "_generation_log.jsonl")
    kept, kept_log = {}, {}
    if args.only:
        kept = {s["id"]: s for s in map(json.loads, args.output.read_text().splitlines())}
        kept_log = {e["id"]: e for e in map(json.loads, log_path.read_text().splitlines())}
        rows = [row for row in rows if row["id"] in args.only]

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        drafts = list(pool.map(lambda row: write(client, row), rows))
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        reviews = list(pool.map(lambda pair: critique(client, *pair), zip(rows, drafts)))

    scenarios, log = [], []
    for row, draft, review in zip(rows, drafts, reviews):
        scenarios.append({
            "id": row["id"],
            "scenario_group": row["scenario_group"],
            "data_quality_case_id": row["data_quality_case_id"],
            "tuple": row["tuple"],
            "opening_message": review["opening_message"].strip(),
            "followups": [f.strip() for f in review["followups"]],
            "expected": row["expected"],
        })
        log.append({"id": row["id"], "draft": draft, "critic_issues": review.get("issues", [])})

    if args.only:
        kept.update({s["id"]: s for s in scenarios})
        kept_log.update({e["id"]: e for e in log})
        scenarios, log = list(kept.values()), list(kept_log.values())
    args.output.write_text("".join(json.dumps(s) + "\n" for s in scenarios))
    log_path.write_text("".join(json.dumps(entry) + "\n" for entry in log))

    openings = Counter(" ".join(s["opening_message"].lower().split()[:3]) for s in scenarios)
    shared = {k: v for k, v in openings.items() if v > 1}
    rewritten = sum(1 for entry in log if entry["critic_issues"])
    print(f"wrote {len(scenarios)} scenarios to {args.output} (generated {len(rows)})")
    print(f"critic flagged and rewrote {rewritten}; log in {log_path}")
    print(f"openings sharing their first three words: {shared or 'none'}")


if __name__ == "__main__":
    main()
