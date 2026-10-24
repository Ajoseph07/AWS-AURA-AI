"""Run the AURA-AI handler locally (no Lambda deploy needed).

Usage, from an AWS-authenticated terminal or CloudShell:

    python local_test.py --prompt "Summarize what AURA-AI does"

Requires Bedrock model access to be enabled for the configured model.
"""
from __future__ import annotations

import argparse
import json

import handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AURA-AI locally.")
    parser.add_argument(
        "--prompt",
        default="Say hello from AURA-AI and explain what you can do in one sentence.",
        help="Prompt text to send to the model.",
    )
    parser.add_argument("--system", help="Optional system prompt override.")
    args = parser.parse_args()

    event = {"prompt": args.prompt}
    if args.system:
        event["system"] = args.system

    result = handler.handler(event)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
