"""AURA-AI Lambda handler.

A stateless request -> Bedrock -> response function. The prompt is passed in
directly on the event and the generated answer is returned in the response;
nothing is read from or written to a database.

Trigger with an event like:
    {"prompt": "Summarize the latest alerts"}

Optional fields:
    {"prompt": "...", "requestId": "req-123", "system": "custom system prompt"}
"""
from __future__ import annotations

import os
import time
import uuid

import bedrock_client

SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "You are AURA-AI, a concise and helpful assistant.",
)


def handler(event, context=None):
    """Lambda entry point. Returns the model's answer for the given prompt."""
    event = event or {}
    prompt = event.get("prompt")
    if not prompt:
        return {"statusCode": 400, "error": "Missing 'prompt' in event."}

    request_id = event.get("requestId") or str(uuid.uuid4())
    system = event.get("system", SYSTEM_PROMPT)

    try:
        answer = bedrock_client.generate(prompt, system=system)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the caller
        msg = f"Error while processing {request_id}: {exc}"
        print(msg)
        return {"statusCode": 500, "requestId": request_id, "error": msg}

    return {
        "statusCode": 200,
        "requestId": request_id,
        "prompt": prompt,
        "response": answer,
        "model": bedrock_client.MODEL_ID,
        "createdAt": int(time.time()),
    }
