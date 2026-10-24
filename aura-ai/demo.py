"""AURA AI five-minute demo.

Loads ~30 informal offer/request messages, uses Bedrock to extract structured
data, runs the deterministic matcher, and prints a proposed transfer plan plus
urgent-need alerts.

Usage:
    python demo.py                 # uses Bedrock if available, else offline fallback
    python demo.py --offline       # force offline keyword extraction (no AWS needed)
    python demo.py --file msgs.json

Persona: Robert, a regional food-bank partnership manager coordinating eight
independent pantries, pastes the week's messages and gets an organized plan.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from extractor import extract
from matcher import build_transfer_plan

HERE = os.path.dirname(os.path.abspath(__file__))

# Optional network policy: which source orgs may supply which destinations.
# Orgs omitted here may supply anyone (open network). Shown for demonstration.
ELIGIBILITY = {
    # "Green Valley Farm Partner": ["Southpoint Pantry", "Maplewood Pantry"],
}

# Optional per-source transport capacity caps (total units movable this cycle).
TRANSPORT_CAPACITY = {
    # "Harbor Community Kitchen": 180,
}


def load_messages(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def run(path: str, use_bedrock: bool) -> int:
    raw_messages = load_messages(path)

    banner(f"AURA AI — processing {len(raw_messages)} partner messages")
    mode = "Bedrock extraction" if use_bedrock else "offline keyword extraction"
    print(f"Extraction mode: {mode}\n")

    parsed = []
    for i, m in enumerate(raw_messages, start=1):
        msg = extract(f"msg-{i:03d}", m["org"], m["text"], use_bedrock=use_bedrock)
        parsed.append(msg)
        flag = "REQUEST" if msg.kind == "request" else "OFFER  "
        print(
            f"  [{flag}] {msg.org:<28} {msg.item:<18} "
            f"{msg.quantity:>5.0f} {msg.unit:<7} urgency={msg.urgency} "
            f"{('(' + ','.join(msg.constraints) + ')') if msg.constraints else ''}"
        )

    offers = sum(1 for m in parsed if m.kind == "offer")
    requests = len(parsed) - offers
    banner(f"Organized: {requests} requests, {offers} offers")

    transfers, alerts = build_transfer_plan(
        parsed,
        transport_capacity=TRANSPORT_CAPACITY,
        eligibility=ELIGIBILITY,
    )

    banner(f"Proposed transfer plan ({len(transfers)} transfers)")
    if not transfers:
        print("  No feasible transfers found.")
    for i, t in enumerate(transfers, start=1):
        print(
            f"  {i:>2}. {t.from_org}  ->  {t.to_org}\n"
            f"      {t.quantity:.0f} {t.unit} of {t.item} "
            f"(category={t.category}, urgency={t.urgency}, score={t.score})"
        )
        if t.notes:
            print(f"      notes: {'; '.join(t.notes)}")

    banner(f"Urgent unmet needs / alerts ({len(alerts)})")
    if not alerts:
        print("  None — all urgent needs have a proposed match.")
    for a in alerts:
        print(f"  ! {a['message']}")

    print()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA AI demo")
    parser.add_argument(
        "--file",
        default=os.path.join(HERE, "sample_messages.json"),
        help="Path to a JSON array of {org, text} messages.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force offline keyword extraction (no AWS/Bedrock needed).",
    )
    args = parser.parse_args()
    sys.exit(run(args.file, use_bedrock=not args.offline))


if __name__ == "__main__":
    main()
