"""Disaster / hazard alerts for AURA AI.

Pulls active alerts from the U.S. National Weather Service (NWS) API — a free,
keyless, authoritative government feed — for the counties the food bank network
covers. Each alert is reduced to a danger zone (center + radius + severity) that
the map overlays and the routing logic avoids.

The NWS feed can be unreachable from a sandboxed/offline environment, so a
deterministic simulated scenario is always available for demos.

NWS API docs: https://www.weather.gov/documentation/services-web-api
"""
from __future__ import annotations

import json
import os
import urllib.request

from geo import CITY_COORDS

# Counties covered by the network (NWS "area" codes are state-level; we filter
# by our own bounding region after fetching California alerts).
NWS_AREA = "CA"
USER_AGENT = "AURA-AI/1.0 (emergency-food-coordination; contact@example.org)"

# Rough bounding box for Santa Clara + San Mateo counties.
BBOX = {"min_lat": 36.9, "max_lat": 37.75, "min_lon": -122.55, "max_lon": -121.4}

SEVERITY_RANK = {"Extreme": 4, "Severe": 3, "Moderate": 2, "Minor": 1, "Unknown": 1}


def _within_bbox(lat: float, lon: float) -> bool:
    return (BBOX["min_lat"] <= lat <= BBOX["max_lat"]
            and BBOX["min_lon"] <= lon <= BBOX["max_lon"])


def fetch_live_alerts(timeout: float = 6.0) -> list[dict]:
    """Fetch active NWS alerts for California, filtered to our region.

    Returns a list of danger zones. Raises on network failure so the caller can
    fall back to the simulated set.
    """
    url = f"https://api.weather.gov/alerts/active?area={NWS_AREA}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    zones = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        center = _alert_center(feat)
        if not center or not _within_bbox(*center):
            continue
        zones.append({
            "id": props.get("id", "")[-12:] or f"nws-{len(zones)}",
            "event": props.get("event", "Weather Alert"),
            "severity": props.get("severity", "Unknown"),
            "headline": props.get("headline") or props.get("event", ""),
            "lat": center[0],
            "lon": center[1],
            "radius_km": _radius_for(props.get("severity", "Unknown")),
            "source": "nws",
        })
    return zones


def _alert_center(feature: dict) -> tuple[float, float] | None:
    """Approximate an alert's center from its geometry, if present."""
    geom = feature.get("geometry")
    if not geom:
        return None
    coords = geom.get("coordinates")
    try:
        pts = []
        def walk(c):
            if isinstance(c, (int, float)):
                return
            if len(c) == 2 and all(isinstance(x, (int, float)) for x in c):
                pts.append((c[1], c[0]))  # GeoJSON is [lon, lat]
            else:
                for sub in c:
                    walk(sub)
        walk(coords)
        if not pts:
            return None
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    except Exception:  # noqa: BLE001
        return None


def _radius_for(severity: str) -> float:
    return {"Extreme": 18.0, "Severe": 12.0, "Moderate": 8.0, "Minor": 5.0}.get(severity, 6.0)


def simulated_alerts() -> list[dict]:
    """A deterministic hazard scenario for demos, aligned with the demo disruption.

    Models a storm system causing a Highway 101 corridor flood risk near Campbell
    and a wind event near the coast — the kind of disruption AURA coordinates around.
    """
    return [
        {
            "id": "sim-flood-101",
            "event": "Flood Warning",
            "severity": "Severe",
            "headline": "Flood Warning — Highway 101 corridor near Campbell; low-lying roads impassable.",
            "lat": 37.2872, "lon": -121.9500, "radius_km": 11.0, "source": "simulated",
        },
        {
            "id": "sim-wind-coast",
            "event": "High Wind Warning",
            "severity": "Moderate",
            "headline": "High Wind Warning — coastal routes near Half Moon Bay / Pacifica; debris on roadways.",
            "lat": 37.5200, "lon": -122.4600, "radius_km": 16.0, "source": "simulated",
        },
        {
            "id": "sim-heat-sj",
            "event": "Excessive Heat Warning",
            "severity": "Moderate",
            "headline": "Excessive Heat Warning — San Jose metro; elevated demand for water and shelter.",
            "lat": 37.3382, "lon": -121.8863, "radius_km": 9.0, "source": "simulated",
        },
    ]


def get_hazards(prefer_live: bool | None = None) -> dict:
    """Return hazard zones plus metadata about the source used.

    prefer_live defaults to the AURA_LIVE_HAZARDS env var ("1" to try the NWS
    feed). Falls back to the simulated scenario on any failure so the map and
    routing always have data in a demo.
    """
    if prefer_live is None:
        prefer_live = os.environ.get("AURA_LIVE_HAZARDS", "0") == "1"

    if prefer_live:
        try:
            zones = fetch_live_alerts()
            return {"source": "nws-live", "zones": zones, "note": "Live NWS active alerts."}
        except Exception as exc:  # noqa: BLE001
            return {
                "source": "simulated",
                "zones": simulated_alerts(),
                "note": f"Live NWS feed unavailable ({exc.__class__.__name__}); showing simulated hazards.",
            }
    return {"source": "simulated", "zones": simulated_alerts(), "note": "Simulated hazard scenario."}
