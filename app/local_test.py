"""Run the AURA-AI flow locally (no Lambda deploy needed).

Usage, from an AWS-authenticated terminal or CloudShell:

    # 1. Seed a request into AuraRequests and run the full flow:
    python local_test.py --seed --prompt "Summarize what AURA-AI does"

    # 2. Or run against an existing request already in the table:
    python local_test.py --request-id req-123

Requires the three DynamoDB tables to exist and Bedrock model access enabled.
"""
from __future__ import annotations

import argparse
import json
import os
import uuid

import boto3

import handler

REGION = os.environ.get("AWS_REGION", "us-east-1")
REQUESTS_TABLE = os.environ.get("REQUESTS_TABLE", "AuraRequests")


def seed_request(prompt: str) -> str:
    request_id = f"req-{uuid.uuid4().hex[:8]}"
    boto3.resource("dynamodb", region_name=REGION).Table(REQUESTS_TABLE).put_item(
        Item={"requestId": request_id, "prompt": prompt}
    )
    print(f"Seeded request {request_id!r} into {REQUESTS_TABLE}")
    return request_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AURA-AI locally.")
    parser.add_argument("--request-id", help="Existing requestId to process.")
    parser.add_argument("--seed", action="store_true", help="Create a new request first.")
    parser.add_argument(
        "--prompt",
        default="Say hello from AURA-AI and explain what you can do in one sentence.",
        help="Prompt text to use when --seed is given.",
    )
    args = parser.parse_args()

    if args.seed:
        request_id = seed_request(args.prompt)
    elif args.request_id:
        request_id = args.request_id
    else:
        parser.error("Provide either --seed or --request-id.")

    result = handler.handler({"requestId": request_id})
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
