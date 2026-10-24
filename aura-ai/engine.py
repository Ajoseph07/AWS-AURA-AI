"""AURA AI engine: parse → prioritize → match → disrupt → rematch → metrics.

Input is two separate lists of free-text lines — item REQUESTS and SURPLUS
reports (offers) — plus an optional disruption scenario. Output is a single
JSON-serializable payload that powers every panel of the dashboard.

Matching policy:
    * Exact item match            -> status "approved" (auto)
    * Same-category substitution  -> status "proposed" (needs coordinator review)
Requests are served in PRIORITY order:
    priority = urgency weight × unmet cases   (critical/high first, then larger gaps)
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta

import metrics
from catalog import CATEGORIES, ITEM_CATEGORY, UNIT, find_item, resolve_org

NOW = datetime(2026, 10, 24, 9, 0)  # fixed "now" so the simulated demo is reproducible

URGENCY_WORDS = {
    "critical": ["critical", "emergency", "out of", "ran out", "completely", "asap", "today", "!!"],
    "high": ["urgent", "running low", "very low", "this week", "soon", "short on"],
    "low": ["whenever", "no rush", "if possible", "low priority", "nice to have"],
}


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _split_line(line: str) -> tuple[str, str]:
    if "|" in line:
        org, text = line.split("|", 1)
        return org.strip(), text.strip()
    return "", line.strip()


def _quantity(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:cases?|cs\b|boxes?|pallets?)?", text, re.I)
    if not m:
        return 1.0
    qty = float(m.group(1))
    if re.search(rf"{re.escape(m.group(1))}\s*pallets?", text, re.I):
        qty *= 40  # 1 pallet ≈ 40 cases
    return qty


def _urgency(text: str) -> str:
    lower = text.lower()
    for level in ("critical", "high", "low"):
        if any(w in lower for w in URGENCY_WORDS[level]):
            return level
    return "medium"


def _expiry_days(text: str) -> int | None:
    m = re.search(r"expir\w*\s+(?:in\s+)?(\d+)\s*day", text, re.I)
    if m:
        return int(m.group(1))
    if re.search(r"expir\w*\s+today", text, re.I):
        return 0
    return None


def bedrock_enabled() -> bool:
    """Live extraction is opt-in: set USE_BEDROCK=1 with AWS credentials available."""
    return os.environ.get("USE_BEDROCK", "0") == "1"


def _bedrock_parse_batch(lines: list[str], kind: str) -> list[dict | None]:
    """Extract every line in ONE Bedrock call (fast enough for a live demo).

    Returns one dict per line, or None per line on any failure so the caller
    falls back to rule-based extraction for that line.
    """
    if not bedrock_enabled() or not lines:
        return [None] * len(lines)
    try:
        import boto3

        # Use the same Bedrock region + model that bedrock_client.py uses, so a
        # single config works everywhere. Defaults to the confirmed-working
        # Claude Haiku inference profile in us-east-2.
        region = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "us-east-2"))
        model = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
        client = boto3.client("bedrock-runtime", region_name=region)
        numbered = "\n".join(f"{i}. {line}" for i, line in enumerate(lines))
        prompt = (
            f"Each numbered line is a food-bank {kind} in the form 'Organization | message'.\n"
            f"Catalog items (use EXACTLY one of these names): {sorted(ITEM_CATEGORY)}\n\n"
            f"{numbered}\n\n"
            "Return ONLY a JSON array with one object per line, in order, with keys: "
            "item (catalog name or null), quantity (number of cases), "
            "urgency (critical|high|medium|low), expiry_days (integer or null)."
        )
        resp = client.converse(
            modelId=model,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 4000, "temperature": 0},
        )
        raw = resp["output"]["message"]["content"][0]["text"]
        data = json.loads(re.search(r"\[.*\]", raw, re.S).group(0))
        if len(data) != len(lines):
            raise ValueError(f"expected {len(lines)} results, got {len(data)}")
        return [d if isinstance(d, dict) and d.get("item") in ITEM_CATEGORY else None for d in data]
    except Exception as exc:  # noqa: BLE001 — never let extraction take the demo down
        print(f"[engine] Bedrock unavailable ({exc}); using rule-based extraction.")
        return [None] * len(lines)


def parse_lines(blob: str, kind: str) -> tuple[list[dict], list[str]]:
    """Parse free-text lines into records. Returns (records, unrecognized_lines)."""
    records, skipped = [], []
    lines = [l for l in blob.splitlines() if l.strip()]
    extracted = _bedrock_parse_batch(lines, kind)
    for i, line in enumerate(lines):
        org_raw, text = _split_line(line)
        org, city = resolve_org(org_raw)
        data = extracted[i] or {}
        item = data.get("item") or find_item(text)
        if not item:
            skipped.append(line.strip())
            continue
        qty = float(data.get("quantity") or _quantity(text))
        rec = {
            "id": f"{kind[0]}{i + 1:03d}",
            "org": org,
            "city": city,
            "item": item,
            "category": ITEM_CATEGORY[item],
            "quantity": qty,
            "unit": UNIT,
            "text": text,
        }
        if kind == "request":
            rec["urgency"] = data.get("urgency") or _urgency(text)
        else:
            days = data.get("expiry_days", _expiry_days(text))
            rec.update({
                "available": qty,
                "start_qty": qty,
                "status": "active",
                "start_status": "active",
                "expiry": NOW + timedelta(days=days) if days is not None else None,
                "expiry_days": days,
            })
        records.append(rec)
    return records, skipped


# --------------------------------------------------------------------------- #
# Prioritized matching
# --------------------------------------------------------------------------- #
def priority(req: dict, filled: float = 0.0) -> float:
    return metrics.URGENCY_WEIGHT[req["urgency"]] * max(0.0, req["quantity"] - filled)


def match(requests: list[dict], offers: list[dict], now: datetime, existing=None, id_start=1):
    """Greedy, priority-ordered allocation. Exact item first (approved), then
    same-category substitutes (proposed). Offers expiring soonest are used first."""
    matches = list(existing or [])
    used: dict[str, float] = {}
    for m in matches:
        used[m["offer_id"]] = used.get(m["offer_id"], 0.0) + m["quantity"]
    filled: dict[str, float] = {}
    for m in matches:
        filled[m["request_id"]] = filled.get(m["request_id"], 0.0) + m["quantity"]

    live = [o for o in offers if metrics._is_live(o, now) and not o.get("route_closed")]
    expiry_key = lambda o: o["expiry"] or datetime.max  # noqa: E731
    next_id = id_start

    for req in sorted(requests, key=lambda r: priority(r, filled.get(r["id"], 0.0)), reverse=True):
        need = req["quantity"] - filled.get(req["id"], 0.0)
        for status, pool in (
            ("approved", [o for o in live if o["item"] == req["item"]]),
            ("proposed", [o for o in live if o["category"] == req["category"] and o["item"] != req["item"]]),
        ):
            for o in sorted(pool, key=expiry_key):
                if need <= 0:
                    break
                if o["org"] == req["org"]:
                    continue  # an org doesn't transfer to itself
                left = o["start_qty"] - used.get(o["id"], 0.0)
                qty = min(need, left)
                if qty <= 0:
                    continue
                matches.append({
                    "id": f"m{next_id:03d}",
                    "request_id": req["id"],
                    "offer_id": o["id"],
                    "from_org": o["org"],
                    "from_city": o["city"],
                    "to_org": req["org"],
                    "to_city": req["city"],
                    "item": o["item"],
                    "requested_item": req["item"],
                    "category": req["category"],
                    "quantity": qty,
                    "urgency": req["urgency"],
                    "status": status,
                    "priority": round(priority(req, filled.get(req["id"], 0.0)), 1),
                    "substitution": status == "proposed",
                })
                next_id += 1
                used[o["id"]] = used.get(o["id"], 0.0) + qty
                filled[req["id"]] = filled.get(req["id"], 0.0) + qty
                need -= qty
    for o in offers:
        o["available"] = max(0.0, o["start_qty"] - used.get(o["id"], 0.0))
    return matches, next_id


# --------------------------------------------------------------------------- #
# Disruption scenario
# --------------------------------------------------------------------------- #
def apply_disruption(offers: list[dict], scenario: dict) -> list[dict]:
    """Mutates offers to reflect the incident. Returns new offers added after it."""
    closed_cities = {c.lower() for c in scenario.get("closed_cities", [])}
    withdrawn_orgs = {resolve_org(o)[0] for o in scenario.get("withdrawn_orgs", [])}
    advance = int(scenario.get("advance_days", 0))
    for o in offers:
        if o["org"] in withdrawn_orgs:
            o["status"] = "withdrawn"
        if o["city"].lower() in closed_cities:
            o["route_closed"] = True
    new_offers, _ = parse_lines(scenario.get("new_offers", ""), "offer")
    for i, o in enumerate(new_offers, start=1):
        o["id"] = f"n{i:03d}"
        o["is_new"] = True
    offers.extend(new_offers)
    return new_offers if advance >= 0 else []


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(requests_text: str, offers_text: str, scenario: dict | None = None) -> dict:
    requests, skipped_r = parse_lines(requests_text, "request")
    offers, skipped_o = parse_lines(offers_text, "offer")

    # Phase 1 — normal operations.
    before, next_id = match(requests, offers, NOW)
    before_cov = metrics.coverage(requests, before)
    after = before
    now = NOW
    disruption = None

    # Phase 2 — disruption + rematch.
    if scenario and scenario.get("enabled"):
        now = NOW + timedelta(days=int(scenario.get("advance_days", 0)))
        apply_disruption(offers, scenario)
        invalid_offer_ids = {
            o["id"] for o in offers
            if not metrics._is_live(o, now) or o.get("route_closed")
        }
        surviving = [m for m in before if m["offer_id"] not in invalid_offer_ids]
        after, _ = match(requests, offers, now, existing=surviving, id_start=next_id)
        disruption = {
            "description": scenario.get("description", "Disruption"),
            "invalidated_matches": len(before) - len(surviving),
            "coverage_waterfall": metrics.coverage_waterfall(requests, before, after),
        }

    plan = sorted(after, key=lambda m: (m["status"] != "approved", -m["priority"]))
    return {
        "simulated": True,
        "unit": UNIT,
        "generated_at": now.isoformat(),
        "kpis": metrics.kpis(requests, after, offers, now, before_cov),
        "bullet": metrics.bullet_by_org(requests, after),
        "target": metrics.COVERAGE_TARGET,
        "bands": metrics.BANDS,
        "stacked": metrics.stacked_by_category(requests, after),
        "utilization": metrics.utilization_by_category(offers, after, now),
        "heatmap": metrics.heatmap(requests, after, by="city"),
        "waterfall": metrics.waterfall(offers, after, now),
        # Per-category waterfalls, so a single-unit view is one click away.
        "waterfall_by_category": {
            c: metrics.waterfall(offers, after, now, category=c)
            for c in CATEGORIES if any(o["category"] == c for o in offers)
        },
        "extraction": "bedrock" if bedrock_enabled() else "rules",
        "disruption": disruption,
        "priority_queue": _priority_queue(requests, after),
        "plan": plan,
        "skipped": {"requests": skipped_r, "offers": skipped_o},
        "counts": {"requests": len(requests), "offers": len(offers), "matches": len(after)},
        "categories": CATEGORIES,
    }


def _priority_queue(requests: list[dict], matches: list[dict]) -> list[dict]:
    rows = []
    for r in requests:
        approved = metrics._matched_for(r, matches, metrics.APPROVED)
        proj = metrics._matched_for(r, matches, metrics.APPROVED_OR_PROPOSED)
        rows.append({
            "id": r["id"], "org": r["org"], "city": r["city"], "item": r["item"],
            "category": r["category"], "quantity": r["quantity"], "urgency": r["urgency"],
            "approved": approved, "proposed": proj - approved,
            "unmet": max(0.0, r["quantity"] - proj),
            "priority": round(priority(r, approved), 1),
        })
    rows.sort(key=lambda x: (-metrics.URGENCY_WEIGHT[x["urgency"]], -x["priority"]))
    return rows
