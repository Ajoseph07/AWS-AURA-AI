"""AURA AI web UI server.

A zero-dependency web server (Python standard library only) that serves a
single-page UI and exposes the AURA AI pipeline over HTTP.

Run:
    cd aura-ai/web
    python server.py                 # offline extraction, http://localhost:8000
    PYTHONPATH=../../app python server.py   # with live Bedrock extraction

Then open http://localhost:8000 in a browser, paste messages, and click Process.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Make the sibling pipeline modules importable (aura-ai/).
AURA_AI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AURA_AI_DIR)

import engine  # noqa: E402
from extractor import extract  # noqa: E402
from matcher import build_transfer_plan  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8000"))

# If PYTHONPATH includes ../../app (so bedrock_client imports), use Bedrock.
USE_BEDROCK = os.environ.get("USE_BEDROCK", "auto")


def _bedrock_available() -> bool:
    if USE_BEDROCK == "0":
        return False
    if USE_BEDROCK == "1":
        return True
    try:
        import bedrock_client  # noqa: F401
        import boto3  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def process_messages(raw_messages: list[dict]) -> dict:
    """Run the full pipeline and return a JSON-serializable result."""
    use_bedrock = _bedrock_available()
    parsed = []
    for i, m in enumerate(raw_messages, start=1):
        org = (m.get("org") or "Unknown Org").strip()
        text = (m.get("text") or "").strip()
        if not text:
            continue
        parsed.append(extract(f"msg-{i:03d}", org, text, use_bedrock=use_bedrock))

    transfers, alerts = build_transfer_plan(parsed)

    return {
        "mode": "bedrock" if use_bedrock else "offline",
        "counts": {
            "messages": len(parsed),
            "requests": sum(1 for m in parsed if m.kind == "request"),
            "offers": sum(1 for m in parsed if m.kind == "offer"),
            "transfers": len(transfers),
            "alerts": len(alerts),
        },
        "messages": [m.to_dict() for m in parsed],
        "transfers": [t.to_dict() for t in transfers],
        "alerts": alerts,
    }


def parse_pasted_text(blob: str) -> list[dict]:
    """Parse the textarea content into [{org, text}].

    Accepts two formats per line:
        Org Name | message text
        message text            (org defaults to "Unknown Org")
    Blank lines are ignored.
    """
    messages = []
    for line in blob.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            org, text = line.split("|", 1)
            messages.append({"org": org.strip(), "text": text.strip()})
        else:
            messages.append({"org": "Unknown Org", "text": line})
    return messages


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: str, content_type: str) -> None:
        with open(path, "rb") as f:
            self._send(200, f.read(), content_type)

    def do_GET(self):  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route in ("/", "/dashboard", "/dashboard.html"):
            self._file(os.path.join(HERE, "dashboard.html"), "text/html; charset=utf-8")
        elif route in ("/classic", "/index.html"):
            self._file(os.path.join(HERE, "index.html"), "text/html; charset=utf-8")
        elif route == "/api/demo":
            self._file(os.path.join(AURA_AI_DIR, "demo_scenario.json"), "application/json")
        elif route == "/sample":
            # Bundled sample messages for the classic view.
            self._file(os.path.join(AURA_AI_DIR, "sample_messages.json"), "application/json")
        else:
            self._send(404, b"Not found", "text/plain")

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")

        if self.path == "/api/dashboard":
            try:
                result = engine.run(
                    payload.get("requests", ""),
                    payload.get("offers", ""),
                    payload.get("scenario"),
                )
                self._send(200, json.dumps(result, default=str).encode("utf-8"), "application/json")
            except Exception as exc:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(exc)}).encode("utf-8"), "application/json")
            return

        if self.path != "/api/process":
            self._send(404, b"Not found", "text/plain")
            return

        if "text" in payload:
            raw_messages = parse_pasted_text(payload["text"])
        else:
            raw_messages = payload.get("messages", [])

        try:
            result = process_messages(raw_messages)
            self._send(200, json.dumps(result).encode("utf-8"), "application/json")
        except Exception as exc:  # noqa: BLE001
            self._send(
                500,
                json.dumps({"error": str(exc)}).encode("utf-8"),
                "application/json",
            )

    def log_message(self, *args):  # silence default noisy logging
        pass


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    mode = "Bedrock" if _bedrock_available() else "offline"
    print(f"AURA AI web UI running on http://localhost:{PORT}  (extraction: {mode})")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
