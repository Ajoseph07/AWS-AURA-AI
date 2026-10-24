"""Safest-route logic for AURA AI.

Given a supplier origin and a destination food bank, the server asks Google
Directions for candidate routes and picks the SAFEST one — the route whose path
stays clearest of active danger zones — rather than simply the fastest.

If a Google Maps key is configured, real routes are requested
(alternatives=true) and scored. Without a key, the browser can still draw a
route client-side; this module then returns a straight-line advisory with a
danger assessment so the feature degrades gracefully.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from geo import haversine_km, point_in_circle


def _decode_polyline(poly: str) -> list[tuple[float, float]]:
    """Decode a Google encoded polyline into [(lat, lon), ...]."""
    points, index, lat, lng = [], 0, 0, 0
    while index < len(poly):
        for is_lng in (False, True):
            result, shift = 0, 0
            while True:
                b = ord(poly[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if is_lng:
                lng += delta
            else:
                lat += delta
        points.append((lat / 1e5, lng / 1e5))
    return points


def _danger_score(path: list[tuple[float, float]], zones: list[dict]) -> dict:
    """How exposed a path is to danger zones.

    Counts path samples that fall inside any zone, weighted by severity. Lower
    is safer. Also reports which zones the route intersects.
    """
    from hazards import SEVERITY_RANK

    hits, intersected = 0.0, {}
    for pt in path:
        for z in zones:
            if point_in_circle(pt, (z["lat"], z["lon"]), z["radius_km"]):
                w = SEVERITY_RANK.get(z["severity"], 1)
                hits += w
                intersected[z["id"]] = z["event"]
    return {
        "score": round(hits, 1),
        "zones_crossed": [{"id": k, "event": v} for k, v in intersected.items()],
        "clear": not intersected,
    }


def safest_route(origin: tuple[float, float], dest: tuple[float, float],
                 zones: list[dict], api_key: str | None = None) -> dict:
    """Return the safest route from origin to dest avoiding danger zones."""
    api_key = api_key or os.environ.get("GOOGLE_MAPS_API_KEY")
    if api_key:
        try:
            return _google_safest_route(origin, dest, zones, api_key)
        except Exception as exc:  # noqa: BLE001
            # Fall through to the straight-line advisory on any API error.
            advisory = _straight_line(origin, dest, zones)
            advisory["note"] = f"Live routing unavailable ({exc.__class__.__name__}); straight-line advisory."
            return advisory
    return _straight_line(origin, dest, zones)


def _google_safest_route(origin, dest, zones, api_key) -> dict:
    params = {
        "origin": f"{origin[0]},{origin[1]}",
        "destination": f"{dest[0]},{dest[1]}",
        "alternatives": "true",
        "mode": "driving",
        "key": api_key,
    }
    url = "https://maps.googleapis.com/maps/api/directions/json?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("status") != "OK" or not data.get("routes"):
        raise RuntimeError(data.get("status", "no routes"))

    scored = []
    for route in data["routes"]:
        path = _decode_polyline(route["overview_polyline"]["points"])
        leg = route["legs"][0]
        danger = _danger_score(path, zones)
        scored.append({
            "summary": route.get("summary", ""),
            "distance": leg["distance"]["text"],
            "duration": leg["duration"]["text"],
            "duration_s": leg["duration"]["value"],
            "polyline": route["overview_polyline"]["points"],
            "danger": danger,
        })
    # Safest first (lowest danger), then fastest among equally-safe routes.
    scored.sort(key=lambda r: (r["danger"]["score"], r["duration_s"]))
    best, alternatives = scored[0], scored[1:]
    return {
        "mode": "google",
        "chosen": best,
        "alternatives": alternatives,
        "avoided_danger": bool(alternatives) and alternatives[0]["danger"]["score"] > best["danger"]["score"],
        "note": "Route is clear of active danger zones." if best["danger"]["clear"]
                else "Safest available route; still crosses a hazard — advise caution.",
    }


def _straight_line(origin, dest, zones) -> dict:
    """Fallback advisory when no Google key is present: sample the direct line."""
    samples = [(origin[0] + (dest[0] - origin[0]) * t / 20,
                origin[1] + (dest[1] - origin[1]) * t / 20) for t in range(21)]
    danger = _danger_score(samples, zones)
    km = haversine_km(origin, dest)
    return {
        "mode": "advisory",
        "chosen": {
            "summary": "Direct path (straight-line estimate)",
            "distance": f"{km:.1f} km (as the crow flies)",
            "duration": "—",
            "duration_s": 0,
            "polyline": None,
            "path": samples,
            "danger": danger,
        },
        "alternatives": [],
        "avoided_danger": False,
        "note": "No Google Maps key set — showing a straight-line danger assessment. "
                "Add GOOGLE_MAPS_API_KEY for real safest-route driving directions.",
    }
