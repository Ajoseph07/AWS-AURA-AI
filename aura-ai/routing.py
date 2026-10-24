"""Safest-route logic for AURA AI.

Given a supplier origin and a destination food bank, pick the SAFEST driving
route rather than simply the fastest.

Hazards come in two tiers (see hazards.must_avoid):

  * must-avoid -- active tornadoes and severe/extreme flooding. A route through
    one is treated as unacceptable. If none of the routing service's suggested
    routes avoid it, we BUILD a detour: add a waypoint just outside the zone
    and ask for a route through that point, so the truck goes around it.
  * caution    -- wind, heat, minor flooding, tornado watches, etc. These only
    lower a route's ranking; we don't force detours for them.

Routes come from the free, keyless OSRM public routing service. If it's
unreachable, a straight-line danger assessment is returned instead.
"""
from __future__ import annotations

import json
import math
import os
import urllib.request

from geo import haversine_km, point_in_circle
from hazards import SEVERITY_RANK, must_avoid

# Public OSRM demo server. Override with OSRM_URL for a self-hosted instance.
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org")

# Detour tuning.
MUST_AVOID_WEIGHT = 100   # one sample inside a must-avoid zone outweighs any caution exposure
# Detour waypoints sit this many radii from the zone center (plus a pad), tried
# tightest first: a detour that hugs the zone edge adds the least time.
DETOUR_MARGINS = (1.1, 1.35, 1.75)
DETOUR_PAD_KM = 1.0
MAX_OSRM_CALLS = 13       # cap requests to the shared public OSRM server per route lookup
# Seconds of extra driving we'd accept to skip one caution sample (~0.4 km of road)
# per severity point. ~10 km through a Moderate zone is worth about an 8 min detour.
CAUTION_SECONDS = 10
MAX_DETOUR_ROUNDS = 3     # how many separate must-avoid zones we'll detour around
SAMPLE_STEP_KM = 0.4      # densify paths so long straight segments can't skip over a zone


# --- Geometry helpers -------------------------------------------------------

def _offset(point: tuple[float, float], bearing_deg: float, dist_km: float) -> tuple[float, float]:
    """Point dist_km from `point` along a compass bearing (fine at city scale)."""
    lat, lon = point
    b = math.radians(bearing_deg)
    dlat = dist_km * math.cos(b) / 111.0
    dlon = dist_km * math.sin(b) / (111.0 * math.cos(math.radians(lat)))
    return (lat + dlat, lon + dlon)


def _bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Approximate compass bearing from a to b, in degrees."""
    dy = b[0] - a[0]
    dx = (b[1] - a[1]) * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(dx, dy)) % 360


def _progress(origin, dest, point) -> float:
    """How far along the origin->dest line a point projects (0 = origin, 1 = dest)."""
    ox, oy = origin[1], origin[0]
    vx, vy = dest[1] - ox, dest[0] - oy
    denom = vx * vx + vy * vy or 1e-12
    return ((point[1] - ox) * vx + (point[0] - oy) * vy) / denom


def _densify(path: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Add interpolated points so no segment is longer than SAMPLE_STEP_KM."""
    if len(path) < 2:
        return list(path)
    out = [path[0]]
    for a, b in zip(path, path[1:]):
        steps = int(haversine_km(a, b) // SAMPLE_STEP_KM)
        for i in range(1, steps + 1):
            t = i / (steps + 1)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        out.append(b)
    return out


# --- Danger scoring ---------------------------------------------------------

def _danger_score(path: list[tuple[float, float]], zones: list[dict],
                  unavoidable: set[str] | None = None) -> dict:
    """How exposed a path is to danger zones. Lower is safer.

    Samples inside a must-avoid zone (tornado, severe flood) count
    MUST_AVOID_WEIGHT each, so any route that avoids them ranks above any route
    that doesn't. `unavoidable` lists zones that contain the origin or the
    destination; they can't be detoured around, so they are scored as caution.
    """
    unavoidable = unavoidable or set()
    blocking_hits, caution_hits, crossed = 0.0, 0.0, {}
    for pt in _densify(path):
        for z in zones:
            if point_in_circle(pt, (z["lat"], z["lon"]), z["radius_km"]):
                blocking = must_avoid(z) and z["id"] not in unavoidable
                if blocking:
                    blocking_hits += MUST_AVOID_WEIGHT
                else:
                    caution_hits += SEVERITY_RANK.get(z["severity"], 1)
                crossed[z["id"]] = {"id": z["id"], "event": z["event"],
                                    "severity": z["severity"], "must_avoid": blocking}
    blocking_zones = [c for c in crossed.values() if c["must_avoid"]]
    return {
        "score": round(blocking_hits + caution_hits, 1),
        "blocking_score": round(blocking_hits, 1),
        "caution_score": round(caution_hits, 1),
        "zones_crossed": list(crossed.values()),
        "blocking": blocking_zones,     # must-avoid zones this route still enters
        "clear": not crossed,
    }


# --- OSRM -------------------------------------------------------------------

class _Budget:
    """Counts OSRM requests so one lookup can't hammer the shared public server."""

    def __init__(self, limit: int):
        self.left = limit

    def take(self) -> bool:
        if self.left <= 0:
            return False
        self.left -= 1
        return True


def _osrm(points: list[tuple[float, float]], alternatives: bool) -> list[dict]:
    """Query OSRM for driving routes through `points` (lat, lon). Returns raw routes."""
    coords = ";".join(f"{p[1]},{p[0]}" for p in points)  # OSRM wants lon,lat
    url = (f"{OSRM_URL}/route/v1/driving/{coords}"
           f"?alternatives={'true' if alternatives else 'false'}"
           "&overview=full&geometries=geojson")
    req = urllib.request.Request(url, headers={"User-Agent": "AURA-AI/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(data.get("code", "no routes"))
    return data["routes"]


def _to_candidate(route: dict, zones: list[dict], unavoidable: set[str],
                  via: list[tuple[float, float]], detour_around: list[str]) -> dict:
    # GeoJSON geometry is [lon, lat]; convert to (lat, lon) for scoring + Leaflet.
    path = [(c[1], c[0]) for c in route["geometry"]["coordinates"]]
    return {
        "summary": ("Detour around " + ", ".join(detour_around)) if detour_around else "",
        "distance": f"{route['distance'] / 1000.0:.1f} km",
        "duration": f"{round(route['duration'] / 60.0)} min",
        "duration_s": int(route["duration"]),
        "path": path,            # [[lat, lon], ...] for Leaflet polyline
        "via": via,              # detour waypoints used, if any
        "danger": _danger_score(path, zones, unavoidable),
    }


def _rank(c: dict) -> tuple:
    """Lower is better.

    First: least time inside must-avoid zones (tornado / severe flood). Then the
    fastest route, where each bit of caution-zone exposure counts as a small
    time penalty, so we never take a long detour just to dodge wind or heat.
    """
    d = c["danger"]
    return (d["blocking_score"], c["duration_s"] + d["caution_score"] * CAUTION_SECONDS)


def _detour_arcs(origin, dest, zone: dict, zones: list[dict]) -> list[list[tuple[float, float]]]:
    """Candidate detours around `zone`, each a short chain of waypoints.

    Each detour is an arc of points just outside the zone on one side of the
    travel direction (before, beside, and after the zone), so the route is
    held outside the whole way around rather than just at one point. Tries both
    sides at a tight margin, then both sides at a wider one. Points behind the
    origin or past the destination, or inside another must-avoid zone, are
    dropped.
    """
    center = (zone["lat"], zone["lon"])
    heading = _bearing(origin, dest)

    def usable(p):
        if not 0.02 < _progress(origin, dest, p) < 0.98:
            return False
        return not any(must_avoid(z) and z["id"] != zone["id"]
                       and point_in_circle(p, (z["lat"], z["lon"]), z["radius_km"])
                       for z in zones)

    # Shortest options first: one point beside the zone, then a full arc that
    # holds the route outside it. Both sides of the zone, tightest margin first.
    shapes = ((90,), (135, 90, 45))
    arcs, seen = [], set()
    for tier, margin in enumerate(DETOUR_MARGINS):
        dist = zone["radius_km"] * margin + DETOUR_PAD_KM
        for turns in shapes:
            for side in (1, -1):
                arc = [p for t in turns
                       if usable(p := _offset(center, heading + side * t, dist))]
                key = tuple(arc)
                if arc and key not in seen:
                    seen.add(key)
                    arcs.append((tier, arc))
    return arcs


def _osrm_safest_route(origin, dest, zones) -> dict:
    zone_by_id = {z["id"]: z for z in zones}
    # Zones the trip starts or ends inside can't be avoided; score them as caution.
    unavoidable = {
        z["id"] for z in zones
        if point_in_circle(origin, (z["lat"], z["lon"]), z["radius_km"])
        or point_in_circle(dest, (z["lat"], z["lon"]), z["radius_km"])
    }
    budget = _Budget(MAX_OSRM_CALLS)
    budget.take()
    candidates = [_to_candidate(r, zones, unavoidable, [], [])
                  for r in _osrm([origin, dest], alternatives=True)]
    fastest = min(candidates, key=lambda c: c["duration_s"])
    best = min(candidates, key=_rank)

    # Build detours while the best route still enters a must-avoid zone.
    detoured_around: list[str] = []
    for _ in range(MAX_DETOUR_ROUNDS):
        if not best["danger"]["blocking"]:
            break
        # Worst hazard first: tornado before flood, then by severity.
        target = max(
            (zone_by_id[b["id"]] for b in best["danger"]["blocking"]),
            key=lambda z: ("tornado" in z["event"].lower(), SEVERITY_RANK.get(z["severity"], 1)),
        )
        improved = False
        base_via = list(best["via"])  # detour points kept from earlier rounds
        cleared_tier = None
        # Try every detour shape on both sides and keep the fastest safe one,
        # rather than the first that works. Once a margin gets around the zone,
        # skip the wider margins, since they only add distance.
        for tier, arc in _detour_arcs(origin, dest, target, zones):
            if cleared_tier is not None and tier > cleared_tier:
                break
            if not budget.take():
                break
            # Keep earlier detour points and insert these in travel order.
            via = sorted(base_via + arc, key=lambda p: _progress(origin, dest, p))
            try:
                routes = _osrm([origin, *via, dest], alternatives=False)
            except Exception:  # noqa: BLE001 - one bad waypoint shouldn't sink the lookup
                continue
            cand = _to_candidate(routes[0], zones, unavoidable, via,
                                 detoured_around + [target["event"]])
            candidates.append(cand)
            if cleared_tier is None and not any(b["id"] == target["id"]
                                                for b in cand["danger"]["blocking"]):
                cleared_tier = tier
            if _rank(cand) < _rank(best):
                best, improved = cand, True
        if improved:
            detoured_around.append(target["event"])
        if not improved or budget.left <= 0:
            break

    alternatives = [c for c in candidates if c is not best]
    alternatives.sort(key=_rank)
    return {
        "mode": "osrm",
        "chosen": best,
        "alternatives": alternatives[:3],
        "avoided_danger": best is not fastest
                          and fastest["danger"]["score"] > best["danger"]["score"],
        "detoured": bool(best["via"]),
        "blocked": bool(best["danger"]["blocking"]),
        "unavoidable": [zone_by_id[i]["event"] for i in unavoidable],
        "note": _note(best, fastest, unavoidable, zone_by_id),
    }


def _note(best: dict, fastest: dict, unavoidable: set[str], zone_by_id: dict) -> str:
    d = best["danger"]
    if d["blocking"]:
        events = ", ".join(sorted({b["event"] for b in d["blocking"]}))
        return (f"DANGER: no route found that avoids the {events}. "
                "Hold this delivery until the alert clears, or confirm roads are open first.")
    parts = []
    if best["via"]:
        extra = round((best["duration_s"] - fastest["duration_s"]) / 60)
        parts.append(f"{best['summary']} (about {extra} min longer than the direct route).")
    if unavoidable:
        events = ", ".join(sorted({zone_by_id[i]["event"] for i in unavoidable}))
        parts.append(f"The start or destination is inside the {events} zone, so the last stretch "
                     "can't avoid it. Use extra caution there.")
    caution = [c["event"] for c in d["zones_crossed"] if c["id"] not in unavoidable]
    if caution:
        parts.append("Passes through caution zone(s): " + ", ".join(sorted(set(caution))) + ".")
    if not parts:
        return "Route is clear of active danger zones."
    return " ".join(parts)


# --- Public entry point -----------------------------------------------------

def safest_route(origin: tuple[float, float], dest: tuple[float, float],
                 zones: list[dict], api_key: str | None = None) -> dict:
    """Return the safest driving route from origin to dest.

    Detours around active tornadoes and severe flooding when needed. Falls back
    to a straight-line danger assessment if OSRM is unreachable (e.g. offline
    demo). `api_key` is unused and kept for backward compatibility.
    """
    try:
        return _osrm_safest_route(origin, dest, zones)
    except Exception as exc:  # noqa: BLE001
        advisory = _straight_line(origin, dest, zones)
        advisory["note"] = (f"Live routing unavailable ({exc.__class__.__name__}); "
                            "showing a straight-line danger assessment. " + advisory["note"])
        return advisory


def _straight_line(origin, dest, zones) -> dict:
    """Fallback advisory when the routing service is unreachable: sample the direct line."""
    samples = [(origin[0] + (dest[0] - origin[0]) * t / 20,
                origin[1] + (dest[1] - origin[1]) * t / 20) for t in range(21)]
    danger = _danger_score(samples, zones)
    km = haversine_km(origin, dest)
    blocking = sorted({b["event"] for b in danger["blocking"]})
    return {
        "mode": "advisory",
        "chosen": {
            "summary": "Direct path (straight-line estimate)",
            "distance": f"{km:.1f} km (as the crow flies)",
            "duration": "—",
            "duration_s": 0,
            "path": samples,
            "via": [],
            "danger": danger,
        },
        "alternatives": [],
        "avoided_danger": False,
        "detoured": False,
        "blocked": bool(blocking),
        "unavoidable": [],
        "note": (f"The direct path crosses an active {', '.join(blocking)}; do not dispatch "
                 "until a safe road route is confirmed.") if blocking else "",
    }
