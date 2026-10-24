"""Shared data models for AURA AI.

Kept as plain dataclasses so the pipeline stays dependency-light and easy to
serialize to JSON (e.g. for the web UI or an API response).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# Canonical food/supply categories AURA AI understands.
CATEGORIES = [
    "baby_formula",
    "shelf_stable_meals",
    "produce",
    "dairy",
    "protein",
    "bakery",
    "water",
    "hygiene",
    "medicine",
    "other",
]


@dataclass
class Message:
    """A single parsed offer or request from a partner organization."""

    message_id: str
    org: str
    kind: str  # "offer" or "request"
    category: str
    item: str
    quantity: float
    unit: str
    urgency: int = 1  # 1 (low) .. 5 (critical)
    constraints: list[str] = field(default_factory=list)  # e.g. ["halal", "refrigerated"]
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Transfer:
    """A proposed transfer of goods from a source org to a destination org."""

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
