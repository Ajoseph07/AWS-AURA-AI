# AURA AI Web UI

A single-page web interface for the AURA AI demo. Paste partner messages,
click **Process**, and see the proposed transfer plan rendered live.

**Zero dependencies** — uses only the Python standard library, so it runs
anywhere (your laptop, AWS CloudShell, a workshop account) with no `pip install`.

## Run it

```bash
cd aura-ai/web

# Offline extraction (no AWS needed — perfect for rehearsing the demo):
python server.py

# With live Bedrock extraction (needs AWS auth + model access):
USE_BEDROCK=1 python server.py
```

Then open **http://localhost:8000** in your browser.

> Change the port with `PORT=8080 python server.py`.
> Force a mode with `USE_BEDROCK=1` or `USE_BEDROCK=0`.

## Using the UI

1. Click **Load 30 sample messages** (or paste your own).
2. Each line is one message. Optional org prefix: `Org Name | message text`.
3. Click **Process**.

You'll see:
- **Stat tiles** — messages / requests / offers / transfers / alerts
- **Proposed transfer plan** — ranked `from → to` transfers with urgency,
  category, score, and logistics notes (e.g. *requires cold-chain transport*)
- **Urgent unmet needs** — red alerts for critical requests with no match
- **Organized messages** — expandable list of every parsed message

The badge in the header shows whether extraction is running in **bedrock** or
**offline** mode.

## Endpoints

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET | `/` | The single-page UI |
| GET | `/sample` | The 30 bundled sample messages |
| POST | `/api/process` | Run the pipeline. Body: `{"text": "..."}` or `{"messages": [{"org","text"}]}` |
