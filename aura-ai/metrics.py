"""Chart metrics for the AURA AI dashboard.

Implements the formulas from the metrics spec. All math runs on the server so
the dashboard, KPIs, and any notification drafts share the same numbers.

Shared definitions (per category, never mixing units — all values are cases):
    Requested  R = Σ request.quantity
    Approved   A = Σ match.quantity where status = approved
    Proposed   P = Σ match.quantity where status = proposed
    matched(r)   = min(Σ matches for r, r.quantity)      # per-request cap
    Unmet      U = max(0, R − A)
    Supply     S = Σ offer.available where status = active and not expired
"""
from __future__ import annotations

from datetime import datetime

from catalog import CATEGORIES, CATEGORY_SHORT, UNIT

URGENCY_WEIGHT = {"critical": 3.0, "high": 2.0, "medium": 1.0, "low": 0.5}
COVERAGE_TARGET = 0.90
BANDS = [  # bullet-graph background bands
    {"label": "Critical", "from": 0.0, "to": 0.5},
    {"label": "At risk", "from": 0.5, "to": 0.8},
    {"label": "On track", "from": 0.8, "to": 1.0},
]
APPROVED = ("approved",)
APPROVED_OR_PROPOSED = ("approved", "proposed")


def _matched_for(req: dict, matches: list[dict], statuses=APPROVED) -> float:
    """min(request quantity, Σ matches for that request in the given statuses)."""
    total = sum(
        m["quantity"] for m in matches
        if m["request_id"] == req["id"] and m["status"] in statuses
    )
    return min(req["quantity"], total)


def coverage(reqs: list[dict], matches: list[dict], statuses=APPROVED) -> float | None:
    """Σ matched(r) / Σ quantity(r). None means 'No demand' (avoid divide-by-zero)."""
    requested = sum(r["quantity"] for r in reqs)
    if requested == 0:
        return None
    return sum(_matched_for(r, matches, statuses) for r in reqs) / requested


def _is_live(offer: dict, now: datetime) -> bool:
    return offer["status"] == "active" and (offer.get("expiry") is None or offer["expiry"] > now)


# --------------------------------------------------------------------------- #
# 1. Bullet graph — demand coverage per organization
# --------------------------------------------------------------------------- #
def bullet_by_org(requests: list[dict], matches: list[dict]) -> list[dict]:
    orgs: dict[str, list[dict]] = {}
    for r in requests:
        orgs.setdefault(r["org"], []).append(r)
    rows = []
    for org, reqs in orgs.items():
        cov = coverage(reqs, matches, APPROVED)
        proj = coverage(reqs, matches, APPROVED_OR_PROPOSED)
        rows.append({
            "org": org,
            "city": reqs[0].get("city", ""),
            "requested": sum(r["quantity"] for r in reqs),
            "coverage": cov,
            "projected": proj,
            "status": _band_label(cov),
        })
    # Worst coverage first: the orgs that need attention lead the chart.
    rows.sort(key=lambda r: (r["coverage"] if r["coverage"] is not None else 2.0, -r["requested"]))
    return rows


def _band_label(cov: float | None) -> str:
    if cov is None:
        return "No demand"
    for band in BANDS:
        if cov < band["to"]:
            return band["label"]
    return "On track"


# --------------------------------------------------------------------------- #
# 2. Bar charts — requested vs matched by category, and resource utilization
# --------------------------------------------------------------------------- #
def stacked_by_category(requests: list[dict], matches: list[dict]) -> list[dict]:
    rows = []
    for cat in CATEGORIES:
        reqs = [r for r in requests if r["category"] == cat]
        if not reqs:
            continue
        r_total = sum(r["quantity"] for r in reqs)
        a = sum(_matched_for(r, matches, APPROVED) for r in reqs)
        a_plus_p = sum(_matched_for(r, matches, APPROVED_OR_PROPOSED) for r in reqs)
        p = a_plus_p - a
        rows.append({
            "category": cat,
            "short": CATEGORY_SHORT[cat],
            "requested": r_total,
            "approved": a,
            "proposed": p,
            "unmet": max(0.0, r_total - a - p),
        })
    return rows


def utilization_by_category(offers: list[dict], matches: list[dict], now: datetime) -> list[dict]:
    """Σ approved quantity drawn from category-c offers / Σ starting available supply in c."""
    offer_cat = {o["id"]: o["category"] for o in offers}
    rows = []
    for cat in CATEGORIES:
        start = sum(o["start_qty"] for o in offers if o["category"] == cat and o["start_status"] == "active")
        if start == 0:
            continue
        used = sum(
            m["quantity"] for m in matches
            if m["status"] == "approved" and offer_cat.get(m["offer_id"]) == cat
        )
        rows.append({
            "category": cat,
            "short": CATEGORY_SHORT[cat],
            "supply": start,
            "used": used,
            "utilization": used / start,
        })
    return rows


# --------------------------------------------------------------------------- #
# 3. Heatmap — urgency-weighted unmet demand, organization × category
# --------------------------------------------------------------------------- #
def heatmap(requests: list[dict], matches: list[dict], by: str = "city") -> dict:
    """Rows are food bank locations (`by` = "city" or "org"), columns are categories.

    Two cell values are computed so the UI can toggle between them:
        unmet  = Σ (quantity − matched) × w(urgency)   ← spec formula (default)
        demand = Σ quantity × w(urgency)                ← total weighted demand
    Color intensity = cell / max(cell over the grid), so the worst cell is darkest.
    """
    unmet: dict[tuple[str, str], float] = {}
    demand: dict[tuple[str, str], float] = {}
    for r in requests:
        key = (r[by], r["category"])
        w = URGENCY_WEIGHT[r["urgency"]]
        demand[key] = demand.get(key, 0.0) + r["quantity"] * w
        gap = r["quantity"] - _matched_for(r, matches, APPROVED)
        if gap > 0:
            unmet[key] = unmet.get(key, 0.0) + gap * w

    row_total: dict[str, float] = {}
    for (row, _), v in demand.items():
        row_total[row] = row_total.get(row, 0.0) + v
    rows = sorted(row_total, key=row_total.get, reverse=True)
    cols = [c for c in CATEGORIES if any(c == k[1] for k in demand)]

    def build(cells: dict) -> tuple[list, float]:
        peak = max(cells.values(), default=0.0)
        grid = []
        for row in rows:
            line = []
            for cat in cols:
                heat = cells.get((row, cat), 0.0)
                intensity = heat / peak if peak else 0.0
                line.append({
                    "heat": round(heat, 1),
                    "intensity": round(intensity, 3),
                    "level": _demand_level(intensity, heat),
                })
            grid.append({"row": row, "cells": line})
        return grid, round(peak, 1)

    unmet_grid, unmet_peak = build(unmet)
    demand_grid, demand_peak = build(demand)
    return {
        "by": by,
        "rows": rows,
        "columns": [{"category": c, "short": CATEGORY_SHORT[c]} for c in cols],
        "unmet": {"grid": unmet_grid, "peak": unmet_peak},
        "demand": {"grid": demand_grid, "peak": demand_peak},
    }


def _demand_level(intensity: float, heat: float) -> str:
    """Categorical color bucket: green (low) / yellow (medium) / red (high)."""
    if heat == 0:
        return "none"
    if intensity >= 0.6:
        return "high"
    if intensity >= 0.25:
        return "medium"
    return "low"


# --------------------------------------------------------------------------- #
# 4. Waterfall — effect of a disruption on supply, in a fixed step order
# --------------------------------------------------------------------------- #
def waterfall(offers: list[dict], matches: list[dict], now: datetime, category: str | None = None) -> dict:
    """Follows supply start → end (all categories, or one). Each offer is removed by
    at most one step, applied in order: withdrawn → inaccessible → expired → new → allocated."""
    if category:
        offers = [o for o in offers if o["category"] == category]
        matches = [m for m in matches if m["category"] == category]
    s0 = sum(o["start_qty"] for o in offers if not o.get("is_new") and o["start_status"] == "active")
    removed: set[str] = set()

    def take(pred) -> float:
        total = 0.0
        for o in offers:
            if o["id"] in removed or o.get("is_new"):
                continue
            if pred(o):
                removed.add(o["id"])
                total += o["start_qty"]
        return total

    withdrawn = take(lambda o: o["status"] == "withdrawn")
    inaccessible = take(lambda o: o.get("route_closed", False))
    expired = take(lambda o: o.get("expiry") is not None and o["expiry"] <= now)
    new = sum(o["start_qty"] for o in offers if o.get("is_new"))
    allocated = sum(m["quantity"] for m in matches if m["status"] == "approved")
    end = s0 - withdrawn - inaccessible - expired + new - allocated

    steps = [
        {"label": "Starting supply", "value": s0, "kind": "total"},
        {"label": "Withdrawn", "value": -withdrawn, "kind": "delta"},
        {"label": "Road closures", "value": -inaccessible, "kind": "delta"},
        {"label": "Expired", "value": -expired, "kind": "delta"},
        {"label": "New offers", "value": new, "kind": "delta"},
        {"label": "Allocated", "value": -allocated, "kind": "delta"},
        {"label": "Ending supply", "value": end, "kind": "total"},
    ]
    return {"steps": steps, "unit": UNIT}


def coverage_waterfall(requests: list[dict], before: list[dict], after: list[dict]) -> dict:
    """Coverage before − lost (invalidated) + recovered (rematched) = final, in % points."""
    r_total = sum(r["quantity"] for r in requests) or 1.0
    cov_before = sum(_matched_for(r, before) for r in requests) / r_total

    before_ids = {m["id"] for m in before}
    after_ids = {m["id"] for m in after}
    surviving = [m for m in before if m["id"] in after_ids]
    cov_surviving = sum(_matched_for(r, surviving) for r in requests) / r_total
    cov_final = sum(_matched_for(r, after) for r in requests) / r_total

    cov_projected = sum(_matched_for(r, after, APPROVED_OR_PROPOSED) for r in requests) / r_total

    lost = cov_before - cov_surviving
    recovered = cov_final - cov_surviving
    new_match_count = len(after_ids - before_ids)
    steps = [
        {"label": "Coverage before", "value": cov_before * 100, "kind": "total"},
        {"label": "Lost to disruption", "value": -lost * 100, "kind": "delta"},
        {"label": "Recovered by rematch", "value": recovered * 100, "kind": "delta"},
        {"label": "Final coverage", "value": cov_final * 100, "kind": "total"},
    ]
    return {
        "steps": steps,
        "unit": "% pts",
        "rematches": new_match_count,
        # Coverage if every pending (proposed) substitution is approved.
        "projected": cov_projected * 100,
    }


# --------------------------------------------------------------------------- #
# Network KPIs
# --------------------------------------------------------------------------- #
def kpis(requests, matches, offers, now, before_cov: float | None = None) -> dict:
    r_total = sum(r["quantity"] for r in requests)
    a = sum(_matched_for(r, matches, APPROVED) for r in requests)
    a_p = sum(_matched_for(r, matches, APPROVED_OR_PROPOSED) for r in requests)
    start_supply = sum(o["start_qty"] for o in offers if o["start_status"] == "active")
    used = sum(m["quantity"] for m in matches if m["status"] == "approved")
    critical_open = sum(
        1 for r in requests
        if r["urgency"] == "critical" and _matched_for(r, matches) < r["quantity"]
    )
    cov = a / r_total if r_total else None
    return {
        "requested": r_total,
        "approved": a,
        "proposed": a_p - a,
        "unmet": max(0.0, r_total - a),
        "coverage": cov,
        "projected": a_p / r_total if r_total else None,
        "coverage_before_disruption": before_cov,
        "supply_utilization": used / start_supply if start_supply else None,
        "critical_open": critical_open,
        "orgs_requesting": len({r["org"] for r in requests}),
        "orgs_offering": len({o["org"] for o in offers}),
        "unit": UNIT,
    }
