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
import hazards as hazards_mod
import mapdata
import routing
from geo import coords_for
from pipeline import bedrock_available, parse_pasted_text, process_messages

app = Flask(__name__, static_folder="static", static_url_path="")


@app.get("/")
@app.get("/map")
def map_view():
    # The disaster response map is the default landing view.
    return send_from_directory(app.static_folder, "map.html")


@app.get("/dashboard")
def dashboard():
    return send_from_directory(app.static_folder, "dashboard.html")


@app.get("/classic")
def classic():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/config.js")
def config_js():
    """Inject the Maps key from the environment so it is never committed."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    body = f"window.AURA_CONFIG = {{ googleMapsKey: {json.dumps(key)} }};"
    return app.response_class(body, mimetype="application/javascript")


@app.get("/api/demo")
def demo():
    return send_from_directory(app.static_folder, "demo_scenario.json")


@app.get("/api/hazards")
def api_hazards():
    prefer_live = request.args.get("live") == "1" or os.environ.get("AURA_LIVE_HAZARDS") == "1"
    return jsonify(hazards_mod.get_hazards(prefer_live))


@app.post("/api/map")
def api_map():
    payload = request.get_json(silent=True) or {}
    try:
        result = mapdata.build_map(
            payload.get("requests", ""), payload.get("offers", ""),
            payload.get("scenario"), payload.get("live_hazards"),
        )
        return app.response_class(json.dumps(result, default=str), mimetype="application/json")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.post("/api/route")
def api_route():
    payload = request.get_json(silent=True) or {}
    try:
        origin = tuple(payload["origin"])
        dest = payload.get("dest")
        if dest is None and payload.get("dest_org"):
            dest = list(coords_for(payload["dest_org"], payload.get("dest_city", "")))
        haz = hazards_mod.get_hazards(payload.get("live_hazards"))
        route = routing.safest_route(origin, tuple(dest), haz["zones"])
        route["hazards"] = haz
        return app.response_class(json.dumps(route, default=str), mimetype="application/json")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


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
