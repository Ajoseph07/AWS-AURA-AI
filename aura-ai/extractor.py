"""Bedrock-powered extraction of structured data from free-text messages.

Each informal partner message (e.g. "we're totally out of baby formula, need
it bad!!") is turned into a structured Message with category, quantity, unit,
urgency, and constraints.

The LLM extracts; downstream code verifies. If Bedrock is unavailable, a
deterministic keyword fallback keeps the demo runnable offline.
"""
from __future__ import annotations

import json
import re

from models import CATEGORIES, Message

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


def _bedrock_extract(org: str, text: str) -> dict:
    import bedrock_client  # imported lazily so offline mode needs no boto3

    prompt = PROMPT_TEMPLATE.format(org=org, text=text, categories=CATEGORIES)
    raw = bedrock_client.generate(prompt, system=SYSTEM, temperature=0)
    # The model may wrap JSON in markdown fences; strip them.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return json.loads(match.group(0) if match else raw)


# --- Offline fallback -------------------------------------------------------

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
    if any(w in lower for w in _OFFER_WORDS) and not any(w in lower for w in _REQUEST_WORDS):
        kind = "offer"
    elif any(w in lower for w in _OFFER_WORDS) and any(w in lower for w in _REQUEST_WORDS):
        # ambiguous: lean on which keyword appears first
        offer_pos = min((lower.find(w) for w in _OFFER_WORDS if w in lower), default=9999)
        req_pos = min((lower.find(w) for w in _REQUEST_WORDS if w in lower), default=9999)
        kind = "offer" if offer_pos < req_pos else "request"

    qty_match = re.search(r"(\d+(?:\.\d+)?)", text)
    quantity = float(qty_match.group(1)) if qty_match else 1.0

    # Prefer a unit word that appears right after the quantity (e.g. "40 units").
    unit = "units"
    unit_pattern = r"\b(cans|cases|lbs|pounds|units|meals|boxes|bottles|packs)\b"
    if qty_match:
        after_qty = lower[qty_match.end():]
        near = re.search(unit_pattern, after_qty)
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

    item = category.replace("_", " ")
    return {
        "kind": kind,
        "category": category,
        "item": item,
        "quantity": quantity,
        "unit": unit,
        "urgency": urgency,
        "constraints": constraints,
    }


def extract(message_id: str, org: str, text: str, *, use_bedrock: bool = True) -> Message:
    """Parse one message into a structured Message.

    Falls back to offline keyword extraction if Bedrock is unavailable.
    """
    data = None
    if use_bedrock:
        try:
            data = _bedrock_extract(org, text)
        except Exception as exc:  # noqa: BLE001 - keep the demo resilient
            print(f"[extractor] Bedrock unavailable ({exc}); using offline fallback.")
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
