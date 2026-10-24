"""AURA-AI Lambda handler.

Flow:
    1. Read a request item from the AuraRequests table (by requestId).
    2. Send its prompt text to Amazon Bedrock (Claude Sonnet via Converse API).
    3. Write the AI response to the AuraResources table.
    4. On failure, log an entry to the AuraAlerts table.

Trigger with an event like:
    {"requestId": "req-123"}

The AuraRequests item is expected to look like:
    {"requestId": "req-123", "prompt": "Summarize the latest alerts"}
"""
from __future__ import annotations

import os
import time
import uuid

import boto3
from botocore.exceptions import ClientError

import bedrock_client

REGION = os.environ.get("AWS_REGION", "us-east-1")

REQUESTS_TABLE = os.environ.get("REQUESTS_TABLE", "AuraRequests")
RESOURCES_TABLE = os.environ.get("RESOURCES_TABLE", "AuraResources")
ALERTS_TABLE = os.environ.get("ALERTS_TABLE", "AuraAlerts")

SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "You are AURA-AI, a concise and helpful assistant.",
)

_dynamodb = boto3.resource("dynamodb", region_name=REGION)


def _record_alert(message: str, request_id: str | None = None) -> None:
    """Write a failure record to the AuraAlerts table (best effort)."""
    try:
        _dynamodb.Table(ALERTS_TABLE).put_item(
            Item={
                "alertId": str(uuid.uuid4()),
                "message": message,
                "requestId": request_id or "unknown",
                "createdAt": int(time.time()),
            }
        )
    except ClientError as exc:  # pragma: no cover - alert logging is best effort
        print(f"Failed to write alert: {exc}")


def handler(event, context=None):
    """Lambda entry point."""
    request_id = (event or {}).get("requestId")
    if not request_id:
        return {"statusCode": 400, "error": "Missing 'requestId' in event."}

    try:
        # 1. Read the request.
        req_table = _dynamodb.Table(REQUESTS_TABLE)
        result = req_table.get_item(Key={"requestId": request_id})
        item = result.get("Item")
        if not item:
            msg = f"No request found for requestId={request_id}"
            _record_alert(msg, request_id)
            return {"statusCode": 404, "error": msg}

        prompt = item.get("prompt")
        if not prompt:
            msg = f"Request {request_id} has no 'prompt' field."
            _record_alert(msg, request_id)
            return {"statusCode": 400, "error": msg}

        # 2. Call Bedrock.
        answer = bedrock_client.generate(prompt, system=SYSTEM_PROMPT)

        # 3. Write the result.
        resource_id = str(uuid.uuid4())
        _dynamodb.Table(RESOURCES_TABLE).put_item(
            Item={
                "resourceId": resource_id,
                "requestId": request_id,
                "prompt": prompt,
                "response": answer,
                "model": bedrock_client.MODEL_ID,
                "createdAt": int(time.time()),
            }
        )

        return {
            "statusCode": 200,
            "resourceId": resource_id,
            "requestId": request_id,
            "response": answer,
        }

    except ClientError as exc:
        msg = f"AWS error while processing {request_id}: {exc}"
        print(msg)
        _record_alert(msg, request_id)
        return {"statusCode": 500, "error": msg}
    except Exception as exc:  # noqa: BLE001 - surface any unexpected failure
        msg = f"Unexpected error while processing {request_id}: {exc}"
        print(msg)
        _record_alert(msg, request_id)
        return {"statusCode": 500, "error": msg}
