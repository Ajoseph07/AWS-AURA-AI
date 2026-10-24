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
    """Return the safest driving route from origin to dest.

    Uses the free, keyless OSRM public routing service (alternatives=true) and
    picks the route that stays clearest of active danger zones. Falls back to a
    straight-line danger assessment if OSRM is unreachable (e.g. offline demo).
    """
    try:
        return _osrm_safest_route(origin, dest, zones)
    except Exception as exc:  # noqa: BLE001
        advisory = _straight_line(origin, dest, zones)
        advisory["note"] = (f"Live routing unavailable ({exc.__class__.__name__}); "
                            "showing a straight-line danger assessment.")
        return advisory


# Public OSRM demo server. Override with OSRM_URL for a self-hosted instance.
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org")


def _osrm_safest_route(origin, dest, zones) -> dict:
    """Query OSRM for driving routes (lon,lat order) and score them by danger."""
    coords = f"{origin[1]},{origin[0]};{dest[1]},{dest[0]}"
    url = (f"{OSRM_URL}/route/v1/driving/{coords}"
           "?alternatives=true&overview=full&geometries=geojson")
    req = urllib.request.Request(url, headers={"User-Agent": "AURA-AI/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(data.get("code", "no routes"))

    scored = []
    for route in data["routes"]:
        # GeoJSON geometry is [lon, lat]; convert to (lat, lon) for scoring + Leaflet.
        path = [(c[1], c[0]) for c in route["geometry"]["coordinates"]]
        km = route["distance"] / 1000.0
        mins = route["duration"] / 60.0
        danger = _danger_score(path, zones)
        scored.append({
            "summary": "",
            "distance": f"{km:.1f} km",
            "duration": f"{round(mins)} min",
            "duration_s": int(route["duration"]),
            "path": path,            # [[lat, lon], ...] for Leaflet polyline
            "danger": danger,
        })
    # Safest first (lowest danger), then fastest among equally-safe routes.
    scored.sort(key=lambda r: (r["danger"]["score"], r["duration_s"]))
    best, alternatives = scored[0], scored[1:]
    rerouted = bool(alternatives) and alternatives[0]["danger"]["score"] > best["danger"]["score"]
    return {
        "mode": "osrm",
        "chosen": best,
        "alternatives": alternatives,
        "avoided_danger": rerouted,
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
            "path": samples,
            "danger": danger,
        },
        "alternatives": [],
        "avoided_danger": False,
        "note": "Routing service unreachable — showing a straight-line danger "
                "assessment between the two points.",
    }
