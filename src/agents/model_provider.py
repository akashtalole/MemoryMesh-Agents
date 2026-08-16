"""Anthropic-hosted models for Strands Agents.

Every specialist agent reasons via Anthropic's API directly (client_args
carries ANTHROPIC_API_KEY) rather than through Amazon Bedrock — this
project's only AWS service is the AgentCore runtime that hosts the workflow,
not the model calls themselves.
"""

import logging
import os
from functools import lru_cache
from typing import Optional

from strands.models.anthropic import AnthropicModel

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = os.getenv("ANTHROPIC_MODEL_ID", "claude-sonnet-4-6")


@lru_cache(maxsize=None)
def get_model(
    model_id: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> AnthropicModel:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Get a key from "
            "https://console.anthropic.com/ and add it to .env"
        )

    resolved_model_id = model_id or DEFAULT_MODEL_ID
    logger.info(
        f"Creating AnthropicModel(model_id={resolved_model_id}, "
        f"max_tokens={max_tokens}, temperature={temperature})"
    )
    return AnthropicModel(
        client_args={"api_key": api_key},
        model_id=resolved_model_id,
        max_tokens=max_tokens,
        params={"temperature": temperature},
    )
