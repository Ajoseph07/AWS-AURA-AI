# AWS-AURA-AI

**AURA AI** — an AI-powered food bank mutual-aid exchange for the Santa Clara and
San Mateo food bank network. Partner organizations submit item requests and
surplus reports; AURA AI extracts structure, matches surplus to need in priority
order, and visualizes coverage, demand hot spots, and disruption recovery on a
live dashboard.

## Quick start — run the web UI

```bash
git clone https://github.com/Ajoseph07/AWS-AURA-AI.git
cd AWS-AURA-AI
git checkout main
git pull
cd aura-ai/web
python server.py
```

Then open **http://localhost:8000**. The **Disaster Response Map** loads by
default — food banks shown as green/yellow/red markers by urgency, active hazard
zones overlaid, an inventory agent summary, and a safest-route finder for
suppliers. **Network Analytics** (the charts dashboard) is one tab over, and the
original paste view is at `/classic`.

### Google Maps setup (optional — the map runs in demo mode without it)

The map shows food bank locations, colors, hazards, and a straight-line route
assessment **with no key**. To get real Google map tiles and real driving
routes, add a key:

1. Copy the template: `cp .env.example .env`
2. Put your key in `.env`: `GOOGLE_MAPS_API_KEY=AIza...`
3. Restart the server.

`.env` is gitignored and must never be committed. The server reads the key at
runtime and injects it into the page via `/config.js`, so it stays out of the
repo. Restrict the key in Google Cloud Console (HTTP referrers + Maps
JavaScript / Directions / Geocoding APIs only).

Hazard alerts come from the free, keyless U.S. National Weather Service. Set
`AURA_LIVE_HAZARDS=1` in `.env` to use live alerts instead of the simulated set.

> Runs offline by default (no AWS needed). For live Bedrock extraction, run it
> from an AWS-authenticated terminal with:
> `USE_BEDROCK=1 python server.py`

### Linux

Most Linux distributions install Python 3 as `python3` (not `python`), so use
`python3` throughout. Install Git and Python 3 first if needed:

```bash
# Debian / Ubuntu
sudo apt update && sudo apt install -y git python3

# Fedora / RHEL / Amazon Linux
sudo dnf install -y git python3
```

Then clone and run:

```bash
git clone https://github.com/Ajoseph07/AWS-AURA-AI.git
cd AWS-AURA-AI
git checkout main
git pull
cd aura-ai/web
python3 server.py
```

Open **http://localhost:8000**. Stop the server with **Ctrl+C**.

> No virtual environment or `pip install` is needed for the web UI — it uses
> only the Python standard library. (Python 3.9+ is required.)
>
> For live Bedrock extraction on Linux:
> `USE_BEDROCK=1 python3 server.py`

## Project layout

| Path | What it is |
| ---- | ---------- |
| `aura-ai/` | The AURA AI matching engine + command-line demo |
| `aura-ai/web/` | Zero-dependency dashboard (the quick-start above) |
| `aura-ai/engine.py`, `metrics.py`, `catalog.py` | Matching engine, chart formulas, item catalog and food bank directory |
| `web-app/` | Production, deployable version (Flask + App Runner, live Bedrock) |

## Deploy to AWS

The production web app in `web-app/` is container-ready for **AWS App Runner**
(public HTTPS URL, live Bedrock). See [`web-app/README.md`](web-app/README.md)
for the full deployment guide.

## How it works

1. **Food banks submit requests and surplus reports** in plain language, in two
   separate inputs, using items from the catalog (quantities in cases).
2. **Extraction** turns each line into item, category, quantity, urgency, and
   expiry (rules by default, Amazon Bedrock with `USE_BEDROCK=1`).
3. **Priority matching** serves requests in order of urgency weight × unmet
   cases. Exact item matches are approved; same-category substitutions are
   proposed for coordinator review.
4. **Disruption + rematch** applies road closures, withdrawn offers, expiries,
   and late donations, then rematches.
5. **Dashboard** shows KPIs, a coverage bullet graph per food bank, stacked
   category bars, surplus utilization, a green/yellow/red demand heat map by
   location, supply and coverage waterfalls, and the priority queue. All math
   runs server-side; all data is labelled simulated.

> **Design principle:** Bedrock *suggests*, code *verifies* — the LLM handles
> messy free text; deterministic Python enforces the hard constraints.

See [`aura-ai/README.md`](aura-ai/README.md) for full details.
