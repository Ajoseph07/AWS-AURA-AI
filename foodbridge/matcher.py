"""Deterministic matching engine for FoodBridge.

The LLM proposes structure; THIS code verifies and decides. It never trusts the
model for the hard constraints that matter for safety and feasibility:

  * category must match
  * specialized-nutrition constraints must be satisfiable by the offer
  * the destination org must be eligible to receive from the source
  * transport capacity must not be exceeded

Produces a ranked transfer plan and a list of unmet urgent needs (alerts).
"""
from __future__ import annotations

from models import Message, Transfer

# Constraints that an offer MUST satisfy if a request asks for them. A request
# for infant formula can only be met by an offer that is also infant-safe, etc.
HARD_CONSTRAINTS = {"infant", "halal", "no_pork", "gluten_free"}


def _constraints_satisfied(request: Message, offer: Message) -> tuple[bool, list[str]]:
    """Every hard constraint on the request must be present on the offer."""
    notes: list[str] = []
    req_hard = set(request.constraints) & HARD_CONSTRAINTS
    offer_set = set(offer.constraints)
    missing = req_hard - offer_set
    if missing:
        return False, [f"offer missing required: {', '.join(sorted(missing))}"]
    if request.constraints:
        notes.append(f"constraints met: {', '.join(sorted(req_hard)) or 'n/a'}")
    # Refrigerated handling is a soft note (logistics), not a hard block here.
    if "refrigerated" in request.constraints or "refrigerated" in offer.constraints:
        notes.append("requires cold-chain transport")
    return True, notes


def _eligible(request: Message, offer: Message, eligibility: dict[str, list[str]]) -> bool:
    """offer.org must be allowed to send to request.org.

    eligibility maps a source org to the list of orgs it may supply. If a source
    org is absent from the map, it is treated as able to supply anyone (open network).
    """
    allowed = eligibility.get(offer.org)
    if allowed is None:
        return True
    return request.org in allowed


def _score(request: Message, offer: Message, fulfilled: float) -> float:
    """Higher is better. Prioritize urgency and how much of the need is met."""
    coverage = fulfilled / request.quantity if request.quantity else 0.0
    return round(request.urgency * 2.0 + coverage * 3.0, 3)


def build_transfer_plan(
    messages: list[Message],
    *,
    transport_capacity: dict[str, float] | None = None,
    eligibility: dict[str, list[str]] | None = None,
) -> tuple[list[Transfer], list[dict]]:
    """Match requests to offers and return (transfers, alerts).

    Args:
        messages: parsed offers and requests.
        transport_capacity: optional per-source-org cap on total units moved.
        eligibility: optional source_org -> [allowed destination orgs].

    Returns:
        (transfers, alerts) where alerts flag unmet urgent needs.
    """
    transport_capacity = dict(transport_capacity or {})
    eligibility = eligibility or {}

    requests = [m for m in messages if m.kind == "request"]
    offers = [m for m in messages if m.kind == "offer"]

    # Remaining available quantity per offer, mutated as we allocate.
    remaining = {o.message_id: o.quantity for o in offers}
    # Remaining transport budget per source org (inf if unspecified).
    budget = {o.org: transport_capacity.get(o.org, float("inf")) for o in offers}

    # Process most urgent requests first.
    requests.sort(key=lambda r: r.urgency, reverse=True)

    transfers: list[Transfer] = []
    alerts: list[dict] = []

    for req in requests:
        need = req.quantity
        candidate_offers = [
            o for o in offers
            if o.category == req.category and remaining[o.message_id] > 0
        ]
        # Prefer offers with more stock available.
        candidate_offers.sort(key=lambda o: remaining[o.message_id], reverse=True)

        for offer in candidate_offers:
            if need <= 0:
                break
            ok, notes = _constraints_satisfied(req, offer)
            if not ok:
                continue
            if not _eligible(req, offer, eligibility):
                continue
            if budget[offer.org] <= 0:
                notes.append(f"{offer.org} transport capacity exhausted")
                continue

            movable = min(need, remaining[offer.message_id], budget[offer.org])
            if movable <= 0:
                continue

            transfers.append(
                Transfer(
                    request_id=req.message_id,
                    offer_id=offer.message_id,
                    from_org=offer.org,
                    to_org=req.org,
                    category=req.category,
                    item=req.item,
                    quantity=round(movable, 2),
                    unit=req.unit,
                    urgency=req.urgency,
                    score=_score(req, offer, movable),
                    notes=notes,
                )
            )
            remaining[offer.message_id] -= movable
            budget[offer.org] -= movable
            need -= movable

        if need > 0 and req.urgency >= 4:
            alerts.append(
                {
                    "request_id": req.message_id,
                    "org": req.org,
                    "category": req.category,
                    "item": req.item,
                    "unmet_quantity": round(need, 2),
                    "unit": req.unit,
                    "urgency": req.urgency,
                    "message": (
                        f"URGENT: {req.org} still needs {round(need, 2)} {req.unit} "
                        f"of {req.item} with no available matching supply."
                    ),
                }
            )

    # Best matches first in the final plan.
    transfers.sort(key=lambda t: t.score, reverse=True)
    return transfers, alerts
