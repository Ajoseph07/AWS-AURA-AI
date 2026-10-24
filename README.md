# AWS-AURA-AI

**AURA AI** — an AI-powered food bank mutual-aid exchange. Partner organizations
submit informal offers and requests; Amazon Bedrock extracts structure
(quantities, categories, constraints, urgency) and the matching engine produces
a ranked transfer plan.

## Quick start — run the web UI

```bash
git clone https://github.com/Ajoseph07/AWS-AURA-AI.git
cd AWS-AURA-AI
git checkout main
git pull
cd aura-ai/web
python server.py
```

Then open **http://localhost:8000** in your browser, click **Load 30 sample
messages**, and press **Process**.

> Runs offline by default (no AWS needed). For live Bedrock extraction, run it
> from an AWS-authenticated terminal with:
> `PYTHONPATH=../../app python server.py`

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
> `PYTHONPATH=../../app python3 server.py`

## Project layout

| Path | What it is |
| ---- | ---------- |
| `aura-ai/` | The AURA AI matching engine + command-line demo |
| `aura-ai/web/` | Zero-dependency browser UI (the quick-start above) |
| `web-app/` | Production, deployable version (Flask + App Runner, live Bedrock) |
| `app/` | Standalone Bedrock Lambda function (prompt → AI response) |

## Deploy to AWS

The production web app in `web-app/` is container-ready for **AWS App Runner**
(public HTTPS URL, live Bedrock). See [`web-app/README.md`](web-app/README.md)
for the full deployment guide.

## How it works

1. **Partners submit informal messages** — offers of surplus and requests for needs.
2. **Bedrock extracts structure** — quantities, categories, constraints
   (infant-safe, halal, gluten-free, refrigerated), and urgency.
3. **Code verifies and matches** — checks category, specialized-nutrition
   constraints, eligibility, and transport capacity, then ranks the transfers.
4. **Alerts** — urgent needs with no available supply are surfaced.

> **Design principle:** Bedrock *suggests*, code *verifies* — the LLM handles
> messy free text; deterministic Python enforces the hard constraints.

See [`aura-ai/README.md`](aura-ai/README.md) for full details.
