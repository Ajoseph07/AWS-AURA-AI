"""Reusable Amazon Bedrock client wrapper using the Converse API.

The Converse API gives a single, consistent interface across chat models,
so switching models later only requires changing MODEL_ID.
"""
from __future__ import annotations

import os

import boto3

# Default model for AURA-AI. Override with the BEDROCK_MODEL_ID env var.
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-6")
REGION = os.environ.get("AWS_REGION", "us-east-1")

# Reuse a single client across invocations (important for Lambda warm starts).
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=REGION)
    return _client


def generate(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """Send a single user prompt to the model and return the text response.

    Args:
        prompt: The user's message.
        system: Optional system instruction to steer the model.
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature (0 = deterministic, 1 = creative).

    Returns:
        The model's text reply.
    """
    kwargs = {
        "modelId": MODEL_ID,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system:
        kwargs["system"] = [{"text": system}]

    response = _get_client().converse(**kwargs)
    return response["output"]["message"]["content"][0]["text"]
