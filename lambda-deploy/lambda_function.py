"""AWS Lambda handler for AURA AI — serves the map, dashboard, classic UI,
and the full JSON API through a Lambda Function URL (public HTTPS, no servers).

This adapts the routes from aura-ai/web/server.py to the Lambda Function URL
event format. All the AURA AI pipeline modules (engine, mapdata, routing,
hazards, extractor, matcher, catalog, etc.) are bundled alongside this file at
the package root, so they import directly.

Routes (GET):   /  /map  /dashboard  /classic  /api/demo  /api/hazards  /sample
Routes (POST):  /api/dashboard  /api/map  /api/route  /api/process
"""
from __future__ import annotations

import base64
import json
import os

import engine
import hazards as hazards_mod
import mapdata
import routing
from extractor import extract
from geo import coords_for
from matcher import build_transfer_plan

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")  # bundled HTML pages
DATA = HERE                      # bundled JSON data files

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


# --------------------------------------------------------------------------- #
# Response helpers
# --------------------------------------------------------------------------- #
def _resp(status: int, body, content_type: str, is_file: bool = False):
    if is_file:
        text = body
    else:
        text = body if isinstance(body, str) else json.dumps(body, default=str)
    return {
        "statusCode": status,
        "headers": {"Content-Type": content_type},
        "body": text,
    }


def _html_file(name: str):
    with open(os.path.join(WEB, name), encoding="utf-8") as f:
        return _resp(200, f.read(), "text/html; charset=utf-8", is_file=True)


def _json_file(name: str):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return _resp(200, f.read(), "application/json", is_file=True)


# --------------------------------------------------------------------------- #
# Pipeline (process endpoint — mirrors server.py)
# --------------------------------------------------------------------------- #
def _parse_pasted_text(blob: str) -> list[dict]:
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


def _process_messages(raw_messages: list[dict]) -> dict:
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


# --------------------------------------------------------------------------- #
# Lambda entry point
# --------------------------------------------------------------------------- #
def handler(event, context=None):
    # Lambda Function URL (payload format 2.0) carries method + path here.
    rc = event.get("requestContext", {}).get("http", {})
    method = rc.get("method", "GET")
    raw_path = rc.get("path") or event.get("rawPath") or "/"
    path = raw_path.split("?", 1)[0].rstrip("/") or "/"

    try:
        if method == "GET":
            return _handle_get(path, event)
        if method == "POST":
            return _handle_post(path, event)
        return _resp(405, {"error": "method not allowed"}, "application/json")
    except FileNotFoundError:
        return _resp(404, {"error": "not found"}, "application/json")
    except Exception as exc:  # noqa: BLE001
        return _resp(500, {"error": str(exc)}, "application/json")


def _handle_get(path, event):
    if path in ("/", "/map", "/map.html"):
        return _html_file("map.html")
    if path in ("/dashboard", "/dashboard.html"):
        return _html_file("dashboard.html")
    if path in ("/classic", "/index.html"):
        return _html_file("index.html")
    if path == "/api/demo":
        return _json_file("demo_scenario.json")
    if path == "/sample":
        return _json_file("sample_messages.json")
    if path == "/api/hazards":
        q = event.get("rawQueryString", "")
        prefer_live = "live=1" in q or os.environ.get("AURA_LIVE_HAZARDS") == "1"
        return _resp(200, hazards_mod.get_hazards(prefer_live), "application/json")
    return _resp(404, {"error": "not found"}, "application/json")


def _body(event) -> dict:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    return json.loads(raw or "{}")


def _handle_post(path, event):
    payload = _body(event)

    if path == "/api/dashboard":
        result = engine.run(payload.get("requests", ""), payload.get("offers", ""), payload.get("scenario"))
        return _resp(200, result, "application/json")

    if path == "/api/map":
        result = mapdata.build_map(
            payload.get("requests", ""), payload.get("offers", ""),
            payload.get("scenario"), payload.get("live_hazards"),
        )
        return _resp(200, result, "application/json")

    if path == "/api/route":
        origin = tuple(payload["origin"])
        dest = payload.get("dest")
        if dest is None and payload.get("dest_org"):
            dest = list(coords_for(payload["dest_org"], payload.get("dest_city", "")))
        haz = hazards_mod.get_hazards(payload.get("live_hazards"))
        route = routing.safest_route(origin, tuple(dest), haz["zones"])
        route["hazards"] = haz
        return _resp(200, route, "application/json")

    if path == "/api/process":
        if "text" in payload:
            raw_messages = _parse_pasted_text(payload["text"])
        else:
            raw_messages = payload.get("messages", [])
        return _resp(200, _process_messages(raw_messages), "application/json")

    return _resp(404, {"error": "not found"}, "application/json")
