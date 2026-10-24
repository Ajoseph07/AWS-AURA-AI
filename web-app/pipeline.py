"""AURA AI pipeline (self-contained for deployment).

Bundles the extraction + matching logic so the container image is standalone.
Mirrors ../aura-ai/{models,extractor,matcher}.py and ../app/bedrock_client.py.

  * Bedrock extracts structure from free-text messages (live, by default).
  * Deterministic code verifies constraints and builds the transfer plan.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
CATEGORIES = [
    "baby_formula", "shelf_stable_meals", "produce", "dairy", "protein",
    "bakery", "water", "hygiene", "medicine", "other",
]


@dataclass
class Message:
    message_id: str
    org: str
    kind: str
    category: str
    item: str
    quantity: float
    unit: str
    urgency: int = 1
    constraints: list[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Transfer:
    request_id: str
    offer_id: str
    from_org: str
    to_org: str
    category: str
    item: str
    quantity: float
    unit: str
    urgency: int
    score: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Bedrock client (lazy — only imported/used when live extraction is on)
# --------------------------------------------------------------------------- #
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-6")
REGION = os.environ.get("AWS_REGION", "us-east-1")
USE_BEDROCK = os.environ.get("USE_BEDROCK", "auto")  # "auto" | "1" | "0"

_bedrock = None


def _get_bedrock():
    global _bedrock
    if _bedrock is None:
        import boto3
        _bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    return _bedrock


def bedrock_available() -> bool:
    if USE_BEDROCK == "0":
        return False
    if USE_BEDROCK == "1":
        return True
    try:
        import boto3  # noqa: F401
        _get_bedrock()
        return True
    except Exception:  # noqa: BLE001
        return False


def _bedrock_generate(prompt: str, system: str) -> str:
    resp = _get_bedrock().converse(
        modelId=MODEL_ID,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 512, "temperature": 0},
    )
    return resp["output"]["message"]["content"][0]["text"]


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
SYSTEM = (
    "You are AURA AI's extraction engine for a food-bank mutual-aid network. "
    "Convert each informal partner message into structured JSON. "
    "Do not invent organizations, items, or quantities that are not present."
)

PROMPT_TEMPLATE = """Extract structured fields from this food-bank network message.

Message from organization "{org}":
\"\"\"{text}\"\"\"

Return ONLY a JSON object with these fields:
- "kind": "offer" if they have surplus to give, "request" if they need something
- "category": one of {categories}
- "item": short human-readable item name
- "quantity": a number (estimate 1 if unstated)
- "unit": e.g. "cans", "cases", "lbs", "units", "meals"
- "urgency": integer 1-5 (5 = critical / out of stock now)
- "constraints": list of strings such as "refrigerated", "halal", "infant",
  "gluten_free", "no_pork" (empty list if none)

JSON only, no prose."""

_CATEGORY_KEYWORDS = {
    "baby_formula": ["formula", "infant milk"],
    "shelf_stable_meals": ["shelf-stable", "shelf stable", "canned meal", "ready meal", "mre"],
    "produce": ["produce", "vegetable", "veggies", "fruit", "apples", "potatoes"],
    "dairy": ["milk", "cheese", "yogurt", "dairy"],
    "protein": ["chicken", "beef", "beans", "protein", "eggs", "tuna"],
    "bakery": ["bread", "bakery", "rolls", "pastries"],
    "water": ["water", "bottled water"],
    "hygiene": ["diapers", "soap", "hygiene", "wipes", "toiletries"],
    "medicine": ["medicine", "medication", "pharmacy", "insulin", "prescriptions"],
}
_CONSTRAINT_KEYWORDS = {
    "refrigerated": ["refrigerat", "cold", "chilled", "frozen"],
    "infant": ["baby", "infant", "newborn"],
    "halal": ["halal"],
    "no_pork": ["no pork", "pork-free"],
    "gluten_free": ["gluten-free", "gluten free", "celiac"],
}
_REQUEST_WORDS = ["need", "out of", "running low", "short on", "request", "looking for", "ran out"]
_OFFER_WORDS = ["surplus", "have extra", "can share", "offer", "available", "overstock", "donate"]


def _fallback_extract(org: str, text: str) -> dict:
    lower = text.lower()
    category = "other"
    for cat, words in _CATEGORY_KEYWORDS.items():
        if any(w in lower for w in words):
            category = cat
            break
    kind = "request"
    has_offer = any(w in lower for w in _OFFER_WORDS)
    has_req = any(w in lower for w in _REQUEST_WORDS)
    if has_offer and not has_req:
        kind = "offer"
    elif has_offer and has_req:
        offer_pos = min((lower.find(w) for w in _OFFER_WORDS if w in lower), default=9999)
        req_pos = min((lower.find(w) for w in _REQUEST_WORDS if w in lower), default=9999)
        kind = "offer" if offer_pos < req_pos else "request"

    qty_match = re.search(r"(\d+(?:\.\d+)?)", text)
    quantity = float(qty_match.group(1)) if qty_match else 1.0

    unit = "units"
    unit_pattern = r"\b(cans|cases|lbs|pounds|units|meals|boxes|bottles|packs)\b"
    if qty_match:
        near = re.search(unit_pattern, lower[qty_match.end():])
        if near:
            unit = near.group(1)
    if unit == "units":
        anywhere = re.search(unit_pattern, lower)
        if anywhere:
            unit = anywhere.group(1)

    urgency = 1
    if any(w in lower for w in ["asap", "urgent", "critical", "emergency", "out of", "ran out", "!!"]):
        urgency = 5
    elif any(w in lower for w in ["soon", "running low", "low on"]):
        urgency = 3

    constraints = [c for c, words in _CONSTRAINT_KEYWORDS.items() if any(w in lower for w in words)]
    if category == "baby_formula" and "infant" not in constraints:
        constraints.append("infant")

    return {
        "kind": kind, "category": category, "item": category.replace("_", " "),
        "quantity": quantity, "unit": unit, "urgency": urgency, "constraints": constraints,
    }


def _bedrock_extract(org: str, text: str) -> dict:
    prompt = PROMPT_TEMPLATE.format(org=org, text=text, categories=CATEGORIES)
    raw = _bedrock_generate(prompt, SYSTEM)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return json.loads(match.group(0) if match else raw)


def extract(message_id: str, org: str, text: str, *, use_bedrock: bool) -> Message:
    data = None
    if use_bedrock:
        try:
            data = _bedrock_extract(org, text)
        except Exception as exc:  # noqa: BLE001
            print(f"[pipeline] Bedrock extract failed ({exc}); using offline fallback.")
    if data is None:
        data = _fallback_extract(org, text)

    category = data.get("category", "other")
    if category not in CATEGORIES:
        category = "other"
    return Message(
        message_id=message_id,
        org=org,
        kind=data.get("kind", "request"),
        category=category,
        item=data.get("item", category.replace("_", " ")),
        quantity=float(data.get("quantity", 1) or 1),
        unit=data.get("unit", "units"),
        urgency=int(data.get("urgency", 1) or 1),
        constraints=list(data.get("constraints", []) or []),
        raw_text=text,
    )


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
HARD_CONSTRAINTS = {"infant", "halal", "no_pork", "gluten_free"}


def _constraints_satisfied(request: Message, offer: Message) -> tuple[bool, list[str]]:
    notes: list[str] = []
    req_hard = set(request.constraints) & HARD_CONSTRAINTS
    missing = req_hard - set(offer.constraints)
    if missing:
        return False, [f"offer missing required: {', '.join(sorted(missing))}"]
    if req_hard:
        notes.append(f"constraints met: {', '.join(sorted(req_hard))}")
    if "refrigerated" in request.constraints or "refrigerated" in offer.constraints:
        notes.append("requires cold-chain transport")
    return True, notes


def _score(request: Message, fulfilled: float) -> float:
    coverage = fulfilled / request.quantity if request.quantity else 0.0
    return round(request.urgency * 2.0 + coverage * 3.0, 3)


def build_transfer_plan(messages: list[Message]) -> tuple[list[Transfer], list[dict]]:
    requests = [m for m in messages if m.kind == "request"]
    offers = [m for m in messages if m.kind == "offer"]
    remaining = {o.message_id: o.quantity for o in offers}

    requests.sort(key=lambda r: r.urgency, reverse=True)
    transfers: list[Transfer] = []
    alerts: list[dict] = []

    for req in requests:
        need = req.quantity
        candidates = [o for o in offers if o.category == req.category and remaining[o.message_id] > 0]
        candidates.sort(key=lambda o: remaining[o.message_id], reverse=True)
        for offer in candidates:
            if need <= 0:
                break
            ok, notes = _constraints_satisfied(req, offer)
            if not ok:
                continue
            movable = min(need, remaining[offer.message_id])
            if movable <= 0:
                continue
            transfers.append(Transfer(
                request_id=req.message_id, offer_id=offer.message_id,
                from_org=offer.org, to_org=req.org, category=req.category,
                item=req.item, quantity=round(movable, 2), unit=req.unit,
                urgency=req.urgency, score=_score(req, movable), notes=notes,
            ))
            remaining[offer.message_id] -= movable
            need -= movable
        if need > 0 and req.urgency >= 4:
            alerts.append({
                "request_id": req.message_id, "org": req.org, "category": req.category,
                "item": req.item, "unmet_quantity": round(need, 2), "unit": req.unit,
                "urgency": req.urgency,
                "message": (f"URGENT: {req.org} still needs {round(need, 2)} {req.unit} "
                            f"of {req.item} with no available matching supply."),
            })

    transfers.sort(key=lambda t: t.score, reverse=True)
    return transfers, alerts


# --------------------------------------------------------------------------- #
# Orchestration helpers used by the web layer
# --------------------------------------------------------------------------- #
def parse_pasted_text(blob: str) -> list[dict]:
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


def process_messages(raw_messages: list[dict]) -> dict:
    use_bedrock = bedrock_available()
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
