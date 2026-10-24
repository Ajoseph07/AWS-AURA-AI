"""Assemble map data for AURA AI.

Combines three things into one payload for the map view:
  1. Food bank markers with lat/long and a green/yellow/red status derived from
     the live engine run (coverage + urgency).
  2. Active hazard / danger zones (NWS live or simulated).
  3. Stock-level breakdown per food bank (stockout / low / medium / high) for the
     marker popups and the AI inventory agent summary.
"""
from __future__ import annotations

import engine
import hazards as hazards_mod
from geo import coords_for, status_from_metrics

# Stock buckets map one-to-one onto the marker status color so the map tells a
# single consistent story (red marker == stockout, green == high stock).
_STATUS_TO_STOCK = {"red": "stockout", "yellow": "low", "green": "high", "none": "unknown"}


def _stock_level(status: str, coverage: float | None) -> str:
    """Derive a stock bucket from the marker status, with a 'medium' middle.

    A yellow marker with decent coverage (0.5-0.8) reads as 'medium' rather than
    'low'; everything else follows the status color directly.
    """
    if status == "yellow" and coverage is not None and coverage >= 0.5:
        return "medium"
    return _STATUS_TO_STOCK.get(status, "unknown")


def build_map(requests_text: str, offers_text: str, scenario: dict | None,
              prefer_live_hazards: bool | None = None) -> dict:
    """Run the engine and produce the full map payload."""
    result = engine.run(requests_text, offers_text, scenario)

    # Per-food-bank max urgency from the priority queue (urgency is a word there).
    urgency_num = {"critical": 5, "high": 4, "medium": 3, "low": 2}
    top_urgency: dict[str, int] = {}
    items_needed: dict[str, list[dict]] = {}
    for r in result["priority_queue"]:
        u = urgency_num.get(r["urgency"], 1)
        top_urgency[r["org"]] = max(top_urgency.get(r["org"], 0), u)
        items_needed.setdefault(r["org"], []).append({
            "item": r["item"], "category": r["category"], "quantity": r["quantity"],
            "unmet": r["unmet"], "urgency": r["urgency"],
        })

    markers = []
    for b in result["bullet"]:
        org, city = b["org"], b["city"]
        lat, lon = coords_for(org, city)
        status = status_from_metrics(b["coverage"], top_urgency.get(org, 0))
        markers.append({
            "org": org,
            "city": city,
            "lat": lat,
            "lon": lon,
            "status": status,  # green / yellow / red / none
            "coverage": b["coverage"],
            "projected": b["projected"],
            "requested": b["requested"],
            "stock_level": _stock_level(status, b["coverage"]),
            "max_urgency": top_urgency.get(org, 0),
            "items": sorted(items_needed.get(org, []), key=lambda x: -x["unmet"])[:6],
        })
    # Most urgent / least covered first so the map legend and list lead with need.
    markers.sort(key=lambda m: (m["coverage"] if m["coverage"] is not None else 2, -m["max_urgency"]))

    haz = hazards_mod.get_hazards(prefer_live_hazards)

    # Inventory agent rollup across the network.
    buckets = {"stockout": 0, "low": 0, "medium": 0, "high": 0, "unknown": 0}
    for m in markers:
        buckets[m["stock_level"]] += 1

    return {
        "simulated": True,
        "markers": markers,
        "hazards": haz,
        "inventory": {
            "buckets": buckets,
            "critical_open": result["kpis"]["critical_open"],
            "coverage": result["kpis"]["coverage"],
            "unit": result["unit"],
        },
        "counts": result["counts"],
        "extraction": result.get("extraction", "rules"),
    }
