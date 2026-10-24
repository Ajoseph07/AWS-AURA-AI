"""Reusable Amazon Bedrock client wrapper using the Converse API.

Used by extractor.py for live LLM extraction. Defaults target the AURA AI
project's Region (us-east-2) and a model confirmed available there.

The Converse API gives a single, consistent interface across chat models,
so switching models later only requires changing MODEL_ID.
"""
from __future__ import annotations

import os

# Default model for AURA AI. This is a cross-Region inference profile ID
# (note the "us." prefix) — the newer Claude models require an inference
# profile rather than a bare on-demand model ID. Override with BEDROCK_MODEL_ID.
MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)
# The AURA AI project lives in us-east-2. Override with BEDROCK_REGION.
REGION = os.environ.get("BEDROCK_REGION", "us-east-2")

# Reuse a single client across invocations (important for warm starts).
_client = None


def _get_client():
    global _client
    if _client is None:
        import boto3

        _client = boto3.client("bedrock-runtime", region_name=REGION)
    return _client


def generate(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.0,
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
