"""Cartwheel HW4 review app: a standard-library HTTP server.

Run from the repository root:

    uv run python -m analysis.review_app.server            # http://localhost:8030
    uv run python -m analysis.review_app.server --refresh  # reload traces from Langfuse
    uv run python -m analysis.review_app.server --local-labels  # no Langfuse writes

API (JSON):

    GET  /api/status             data source, Langfuse write status, counts
    GET  /api/conversations      every final-run conversation, turns in order
    GET  /api/context            policies, SPEC.md, tool definitions, world date
    GET  /api/annotations        annotations.json
    POST /api/annotations        one op: add | update | delete | reviewed
    GET  /api/suggestions        suggestions.json
    POST /api/suggestions        replace the document (the coding agent pushes)
    POST /api/suggestions/decide {id, decision, note?}: accept or reject one
    GET  /api/patterns           patterns.json (the taxonomy)
    POST /api/patterns           replace the document (the coding agent pushes)
    GET  /api/samples            sample_manifest.json
    POST /api/samples            replace the document (the coding agent pushes)
    GET  /api/labels             live judgments for every mode in patterns.json
    POST /api/labels             {trace_id, mode, label: 1|0|null, note?}
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from analysis.review_app import data, store

STATIC = Path(__file__).resolve().parent / "static"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}

STATE: dict[str, Any] = {}


def _trace_context(trace_id: str) -> dict[str, Any]:
    conv = STATE["trace_index"].get(trace_id)
    return {"session_id": conv["session_id"], "scenario_id": conv["scenario_id"]} if conv else {}


def _client() -> Any:
    if STATE["local_labels"] or not data.langfuse_configured():
        return None
    if STATE.get("client") is None:
        STATE["client"] = data.langfuse_client()
    return STATE["client"]


class Handler(BaseHTTPRequestHandler):
    server_version = "CartwheelReview/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A002
        if not self.path.startswith("/api/") or self.command == "POST":
            super().log_message(fmt, *args)

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw or b"null")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in {"/", "/index.html"}:
            path = "/index.html"
        if not path.startswith("/api/"):
            target = (STATIC / path.lstrip("/")).resolve()
            if STATIC in target.parents and target.is_file():
                body = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json({"error": "not found"}, 404)
            return
        if path == "/api/status":
            self._json(
                {
                    **STATE["source"],
                    "conversations": len(STATE["conversations"]),
                    "traces": len(STATE["trace_index"]),
                    "langfuse_writes": "off (--local-labels)" if STATE["local_labels"]
                    else ("on" if data.langfuse_configured() else "unavailable: LANGFUSE_* not set"),
                }
            )
        elif path == "/api/conversations":
            self._json(STATE["conversations"])
        elif path == "/api/context":
            self._json(STATE["context"])
        elif path == "/api/annotations":
            self._json(store.read_doc("annotations.json"))
        elif path == "/api/suggestions":
            self._json(store.read_doc("suggestions.json"))
        elif path == "/api/patterns":
            self._json(store.read_doc("patterns.json"))
        elif path == "/api/samples":
            self._json(store.read_doc("sample_manifest.json"))
        elif path == "/api/labels":
            modes = [m.get("name") for m in store.read_doc("patterns.json")["modes"] if m.get("name")]
            self._json(store.all_live_labels(modes))
        else:
            self._json({"error": f"unknown endpoint {path}"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            body = self._body()
        except ValueError:
            self._json({"error": "expected a JSON body"}, 400)
            return
        try:
            if path == "/api/annotations":
                self._json(store.annotation_op(body or {}))
            elif path in {"/api/suggestions", "/api/patterns", "/api/samples"}:
                name = {
                    "/api/suggestions": "suggestions.json",
                    "/api/patterns": "patterns.json",
                    "/api/samples": "sample_manifest.json",
                }[path]
                if not isinstance(body, dict):
                    raise ValueError("expected a JSON object")
                store.write_doc(name, body)
                self._json({"ok": True})
            elif path == "/api/suggestions/decide":
                sugg = next(
                    (s for s in store.read_doc("suggestions.json")["suggestions"] if s.get("id") == body.get("id")),
                    {},
                )
                doc = store.decide_suggestion(
                    body.get("id"), body.get("decision"), note=body.get("note"),
                    client=_client(), local_only=STATE["local_labels"],
                    context=_trace_context(sugg.get("trace_id", "")),
                )
                self._json(doc)
            elif path == "/api/labels":
                trace_id = body.get("trace_id")
                if trace_id not in STATE["trace_index"]:
                    raise ValueError(f"unknown trace {trace_id!r}")
                record = store.set_label(
                    trace_id, body.get("mode"), body.get("label"), note=body.get("note"),
                    origin=body.get("origin") or "reviewer", context=_trace_context(trace_id),
                    client=_client(), local_only=STATE["local_labels"],
                )
                self._json({"ok": True, "record": record})
            else:
                self._json({"error": f"cannot POST to {path}"}, 404)
        except store.LabelError as exc:
            self._json({"error": str(exc), "saved": False}, 502)
        except (KeyError, ValueError) as exc:
            self._json({"error": str(exc)}, 400)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8030)
    parser.add_argument("--refresh", action="store_true", help="reload traces from Langfuse")
    parser.add_argument(
        "--local-labels", action="store_true",
        help="save judgments locally only (langfuse_synced: false); for offline use",
    )
    args = parser.parse_args()

    data.load_env()
    raw, source = data.load_raw(refresh=args.refresh)
    conversations, context = data.build_conversations(raw)
    STATE.update(
        source=source,
        conversations=conversations,
        context=context,
        local_labels=args.local_labels,
        trace_index={t["trace_id"]: c for c in conversations for t in c["turns"]},
    )
    print(f"{source['source']}: {len(raw)} traces, {len(conversations)} conversations")
    print(source["note"])
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"review app on http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
