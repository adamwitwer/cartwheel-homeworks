"""Append one captured conversation to hw1-session.jsonl with the student's assessment.

Usage (from the repository root):
    uv run python notes/part-b/record.py NAME --expected "..." --requirement AUTH-1 \
        --met true --source null

Reads notes/part-b/NAME.json (written by capture.py), adds the judgment
fields, and appends one line to hw1-session.jsonl. A record that is already
present for the same request and response is replaced instead of duplicated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SESSION = HERE.parent.parent / "hw1-session.jsonl"
SOURCES = {"prompt", "tool", "specification"}


def nullable(value: str) -> str | None:
    return None if value.lower() in {"null", "none", ""} else value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--expected", required=True)
    parser.add_argument("--requirement", required=True, type=nullable)
    parser.add_argument("--met", required=True, choices=["true", "false"])
    parser.add_argument("--source", required=True, type=nullable)
    args = parser.parse_args()

    met = args.met == "true"
    if met and args.source is not None:
        raise SystemExit("problem_source must be null when the requirement was met")
    if not met and args.source not in SOURCES:
        raise SystemExit(f"problem_source must be one of {sorted(SOURCES)} when not met")

    record = json.loads((HERE / f"{args.name}.json").read_text())
    record.update(
        expected=args.expected,
        requirement=args.requirement,
        met_requirement=met,
        problem_source=args.source,
    )

    lines = SESSION.read_text().splitlines() if SESSION.exists() else []
    kept = [
        line for line in lines
        if not (json.loads(line)["request"] == record["request"]
                and json.loads(line)["response"] == record["response"])
    ]
    kept.append(json.dumps(record, ensure_ascii=False))
    SESSION.write_text("\n".join(kept) + "\n")
    print(f"{SESSION.name}: {len(kept)} records")


if __name__ == "__main__":
    main()
