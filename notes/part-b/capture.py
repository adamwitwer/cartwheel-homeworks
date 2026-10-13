"""Run one recorded HW1 conversation through the real CLI and capture it.

Usage (from the repository root):
    uv run python notes/part-b/capture.py NAME --role shopper --user 1 "turn 1" ["turn 2" ...]

Launches `agent.cli --debug` in a fresh session, feeds the turns on stdin,
saves the raw transcript to notes/part-b/NAME.txt, and writes the observed
fields (role, user_id, store_id, request, tool_calls, response) to
notes/part-b/NAME.json. Judgment fields are left for the student to fill in.
Nothing is invented: tool calls and results are parsed from the CLI's own
--debug lines.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEADER = re.compile(r"role=(\w+) user=(\d+) store=(\w+)")
TOOL = re.compile(r"^\s*(?:\w+> )?\s*\[tool\] (\w+)\((.*)\)\s*$")
RESULT = re.compile(r"^\s*-> (.*)$")


def parse(transcript: str) -> dict:
    header = HEADER.search(transcript)
    if header is None:
        raise SystemExit("could not find the CLI header line")
    role, user, store = header.groups()
    tool_calls: list[dict] = []
    responses: list[str] = []
    current: list[str] | None = None
    for line in transcript.splitlines():
        if (m := TOOL.match(line)):
            tool_calls.append({"name": m[1], "arguments": ast.literal_eval(m[2]), "result": None})
            current = None
        elif (m := RESULT.match(line)) and tool_calls and tool_calls[-1]["result"] is None:
            tool_calls[-1]["result"] = ast.literal_eval(m[1])
        elif line.startswith("agent> "):
            current = [line[len("agent> "):]]
            responses.append("")
        elif re.match(r"^\w+> ", line):
            current = None
        elif current is not None:
            current.append(line)
        if current is not None and responses:
            responses[-1] = "\n".join(current).strip()
    return {
        "role": role,
        "user_id": int(user),
        "store_id": None if store == "None" else int(store),
        "tool_calls": tool_calls,
        "response": "\n\n".join(responses),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--role", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("turns", nargs="+")
    args = parser.parse_args()

    stdin = "\n".join([*args.turns, "quit"]) + "\n"
    cmd = [sys.executable, "-m", "agent.cli", "--role", args.role, "--user", args.user, "--debug"]
    proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=600)
    transcript = proc.stdout + (f"\n[stderr]\n{proc.stderr}" if proc.stderr.strip() else "")
    (HERE / f"{args.name}.txt").write_text(transcript)
    if proc.returncode != 0:
        print(transcript)
        raise SystemExit(f"CLI exited with {proc.returncode}")

    record = parse(proc.stdout)
    record["request"] = args.turns[0] if len(args.turns) == 1 else args.turns
    ordered = {k: record[k] for k in ("role", "user_id", "store_id", "request", "tool_calls", "response")}
    (HERE / f"{args.name}.json").write_text(json.dumps(ordered, indent=2) + "\n")
    print(transcript)


if __name__ == "__main__":
    main()
