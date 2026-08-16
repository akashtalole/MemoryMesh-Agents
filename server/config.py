"""Backend-mode resolution for the FastAPI layer.

Two ways to talk to the agent:

- "agentcore": proxy chat requests to a deployed Amazon Bedrock AgentCore
  runtime over boto3. This is what a real deployment uses.
- "local": run the LangGraph workflow in this process, against the same
  CockroachDB + Anthropic credentials. No AWS needed at all — this is what
  makes `make dev` work before you've ever run `make deploy`.

Mode is auto-detected (AgentCore if a runtime ARN is configured, local
otherwise) unless AGENT_BACKEND_MODE forces one explicitly.
"""

import os
from typing import Optional


def get_runtime_arn() -> Optional[str]:
    arn = os.getenv("AGENTCORE_RUNTIME_ARN")
    if arn:
        return arn
    try:
        from src.config.config_manager import ConfigManager

        return ConfigManager().get_runtime_arn() or None
    except Exception:
        return None


def get_region() -> str:
    return os.getenv("AWS_REGION", "us-east-1")


def get_backend_mode() -> str:
    forced = os.getenv("AGENT_BACKEND_MODE", "auto").lower()
    if forced in ("local", "agentcore"):
        return forced
    return "agentcore" if get_runtime_arn() else "local"
