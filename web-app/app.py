"""AURA AI — production web application (Flask).

A deployable version of the AURA AI mutual-aid exchange UI. Paste partner
messages, and the app extracts structure with Amazon Bedrock, matches supply to
demand with deterministic logic, and returns a ranked transfer plan.

Extraction mode:
  * Live Bedrock when AWS credentials + model access are available (default).
  * Automatic offline keyword fallback if Bedrock is unreachable, so the service
    stays up even without permissions.

Run locally:
    pip install -r requirements.txt
    python app.py                       # http://localhost:8000

Run in production (as the container does):
    gunicorn --bind 0.0.0.0:8000 app:app
"""
from __future__ import annotations

import json
import os

from flask import Flask, jsonify, request, send_from_directory

import engine
from pipeline import bedrock_available, parse_pasted_text, process_messages

app = Flask(__name__, static_folder="static", static_url_path="")


@app.get("/")
@app.get("/dashboard")
def dashboard():
    return send_from_directory(app.static_folder, "dashboard.html")


@app.get("/classic")
def classic():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/demo")
def demo():
    return send_from_directory(app.static_folder, "demo_scenario.json")


@app.post("/api/dashboard")
def api_dashboard():
    payload = request.get_json(silent=True) or {}
    try:
        result = engine.run(
            payload.get("requests", ""), payload.get("offers", ""), payload.get("scenario")
        )
        return app.response_class(json.dumps(result, default=str), mimetype="application/json")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.get("/sample")
def sample():
    return send_from_directory(app.static_folder, "sample_messages.json")


@app.get("/health")
def health():
    """Health check endpoint for App Runner / load balancers."""
    return jsonify({"status": "ok", "bedrock": bedrock_available()})


@app.post("/api/process")
def api_process():
    payload = request.get_json(silent=True) or {}
    if "text" in payload:
        raw_messages = parse_pasted_text(payload["text"])
    else:
        raw_messages = payload.get("messages", [])

    try:
        result = process_messages(raw_messages)
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
