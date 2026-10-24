# AURA AI — AI Food Bank Mutual-Aid Exchange

**Best multi-organization collaboration**

> **Persona:** Robert, a regional food-bank partnership manager overseeing eight
> independent pantries.
>
> **Failure it fixes:** One pantry runs out of baby formula and shelf-stable
> meals while a nearby organization sits on surplus stock — and nobody can
> coordinate a transfer across organizations efficiently.

AURA AI is an AI-powered exchange connecting food banks, pantries, kitchens,
and approved community partners.

## How it works

1. **Partner organizations submit informal messages** — offers of surplus and
   requests for what they need, in plain language.
2. **Bedrock extracts structure** — quantities, categories, constraints
   (e.g. *infant-safe*, *halal*, *gluten-free*, *refrigerated*), and urgency.
   → `extractor.py`
3. **Code verifies and matches** — deterministic logic checks category match,
   specialized-nutrition constraints, org eligibility, and transport capacity,
   then produces a ranked transfer plan. → `matcher.py`
4. **Status + alerts** — urgent needs with no available supply are surfaced as
   alerts; healthcare-partner referrals are recognized as their own category.

> **Design principle: Bedrock *suggests*, code *verifies*.** The LLM handles
> messy free text; plain Python enforces the hard constraints so the system
> never proposes an infeasible or unsafe transfer (e.g. non-infant formula for
> a newborn request).

## Five-minute demo

Paste ~30 offer/request messages and watch AURA AI organize them, identify
candidate matches, and generate a proposed transfer plan.

```bash
cd aura-ai

# Run entirely offline — no AWS needed (great for rehearsing the demo):
python demo.py --offline

# Run with real Bedrock extraction (needs AWS auth + model access).
# Make the Bedrock client importable, then run:
PYTHONPATH=../app python demo.py
```

### Prefer a web UI?

There's also a browser-based UI — paste messages and see the plan rendered live:

```bash
cd aura-ai/web
python server.py          # then open http://localhost:8000
```

See `web/README.md` for details.

The demo prints three sections:
1. **Organized messages** — every message parsed into structured fields.
2. **Proposed transfer plan** — ranked transfers (`from_org -> to_org`), with
   urgency, score, and logistics notes (e.g. *requires cold-chain transport*).
3. **Urgent unmet needs** — alerts for critical requests with no match.

### What the demo demonstrates (Robert's scenario)

- **Northside Pantry** is *out of baby formula* (urgency 5) → matched to
  **Harbor Community Kitchen**'s surplus, with the **infant** constraint verified.
- **Maplewood Pantry** *out of shelf-stable meals* (urgency 5) → matched to
  surplus from **Riverside Pantry**.
- A **halal** protein request is only matched to a **halal** offer.
- A **gluten-free** bakery request is only matched to a **gluten-free** offer.
- **Refrigerated** items are flagged as needing cold-chain transport.
- Healthcare-partner **medicine referrals** are recognized as their own category.

## Files

| File | Purpose |
| ---- | ------- |
| `demo.py` | Five-minute demo orchestrator |
| `extractor.py` | Bedrock extraction (+ offline keyword fallback) |
| `matcher.py` | Deterministic matching / verification engine |
| `models.py` | Shared data models (`Message`, `Transfer`) |
| `sample_messages.json` | 30 realistic messages across 8 organizations |

## Optional policy knobs (in `demo.py`)

- `ELIGIBILITY` — restrict which source orgs may supply which destinations.
- `TRANSPORT_CAPACITY` — cap total units a source org can move per cycle.

Both are empty by default (open network, unlimited transport) and are
enforced by `matcher.py` when set.

## Statelessness

AURA AI runs entirely in memory — messages are pasted in, processed, and the
transfer plan is returned. No database is required. The structured results
(`Message`, `Transfer`, and alert dicts) serialize cleanly to JSON, so they can
be rendered by the web UI or returned from an API without any storage layer.

See `../app/` for the Bedrock client this demo reuses.
