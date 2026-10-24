"""Deterministic urgency scoring for AURA AI.

Urgency is a request-only concept: it answers "how badly does this org need this,
and how soon?" Offers are supply, not need, so they are never urgent.

The score (1-5) is derived from three explainable signals in the message:

  1. Stockout severity  -- "completely out" outranks "running low" outranks "could use".
  2. Explicit urgency    -- words like ASAP / emergency / now / "!!".
  3. Item sensitivity    -- baby formula and medicine serve vulnerable people
                            (newborns, patients), so they carry a higher floor.

Design principle (Bedrock suggests, code verifies): the LLM may propose an
urgency, but `reconcile` enforces a deterministic floor so the system never
under-rates a critical stockout of a sensitive item.
"""
from __future__ import annotations

URGENCY_MIN = 1
URGENCY_MAX = 5

# Signal 1 -- how severe is the shortage, by phrasing.
_CRITICAL_STOCKOUT = [
    "completely out", "totally out", "out of", "ran out", "ran out of",
    "none left", "no more", "zero", "depleted", "empty",
]
_MODERATE_SHORTAGE = [
    "running low", "low on", "short on", "almost out", "nearly out",
    "getting low", "down to",
]
# Baseline request phrasing -- a need, but not framed as a shortage crisis.
_BASELINE_REQUEST = [
    "could use", "looking for", "would like", "requesting", "request", "need",
]

# Signal 2 -- explicit urgency language.
_EXPLICIT_URGENT = [
    "asap", "urgent", "urgently", "critical", "emergency", "right now",
    "now", "immediately", "today", "!!",
]

# Signal 3 -- categories that serve especially vulnerable populations.
# These get a higher urgency floor because the cost of going unmet is high.
_SENSITIVE_CATEGORY_FLOOR = {
    "baby_formula": 4,  # newborns depend on it; no safe substitute
    "medicine": 4,      # patients / prescriptions
    "water": 3,         # hydration, acute during heat waves / outages
}


def _clamp(value: int) -> int:
    return max(URGENCY_MIN, min(URGENCY_MAX, value))


def score_urgency(kind: str, category: str, text: str, constraints: list[str] | None = None) -> int:
    """Compute a 1-5 urgency score for a message.

    Offers are never urgent (always returns URGENCY_MIN). For requests, combine
    stockout severity, explicit-urgency language, and item sensitivity.
    """
    if kind != "request":
        return URGENCY_MIN

    lower = text.lower()
    constraints = constraints or []

    # --- Signal 1: stockout severity sets the base score. ---
    if any(phrase in lower for phrase in _CRITICAL_STOCKOUT):
        score = 5
    elif any(phrase in lower for phrase in _MODERATE_SHORTAGE):
        score = 3
    elif any(phrase in lower for phrase in _BASELINE_REQUEST):
        score = 2
    else:
        score = 1

    # --- Signal 2: explicit urgency language bumps it up. ---
    if any(word in lower for word in _EXPLICIT_URGENT):
        score += 1

    # --- Signal 3: sensitive categories (and infant constraint) raise the floor. ---
    floor = _SENSITIVE_CATEGORY_FLOOR.get(category, URGENCY_MIN)
    if "infant" in constraints:
        floor = max(floor, 4)
    score = max(score, floor)

    return _clamp(score)


def reconcile(kind: str, category: str, text: str, constraints: list[str] | None,
              proposed: int | None) -> int:
    """Reconcile an LLM-proposed urgency with the deterministic score.

    Raise-only: trust the model's nuance when it rates a need AT or ABOVE the
    deterministic floor, but never let it under-rate a critical need. Offers are
    always URGENCY_MIN regardless of what the model said.
    """
    deterministic = score_urgency(kind, category, text, constraints)
    if kind != "request":
        return URGENCY_MIN
    if proposed is None:
        return deterministic
    return _clamp(max(int(proposed), deterministic))
