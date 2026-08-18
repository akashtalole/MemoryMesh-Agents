"""
MemoryMesh Agent — AWS Bedrock AgentCore entrypoint.

AgentCore hosts this container as a managed runtime and exposes it over the
bedrock-agentcore invoke API — that's its only job; CodeBuild/ECR/ECS/IAM
handle build and hosting automation elsewhere in deployment/, and none of
it is in the inference path. Model reasoning goes straight to Anthropic's
API (Strands `AnthropicModel`); all persistent memory — checkpoints, chat
history, long-term case memory — lives in CockroachDB.
"""

import asyncio
import json
import logging
from typing import Optional

from dotenv import load_dotenv
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from src.agents import Workflow
from src.config.logging_config import configure_logging

load_dotenv()

# AgentCore captures stdout/stderr to CloudWatch; no file logging in-container.
configure_logging(force_console=True)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

_workflow: Optional[Workflow] = None
_workflow_lock = asyncio.Lock()


async def get_workflow() -> Workflow:
    """Lazily build the workflow on first invocation.

    Building it requires awaiting the CockroachDB checkpointer's `setup()`
    and the case-memory vector store's table/index initialisation, which
    can't happen at plain module-import time, so we initialise on first
    request instead and cache the result for the life of the container.
    """
    global _workflow
    if _workflow is None:
        async with _workflow_lock:
            if _workflow is None:
                logger.info("Initializing MemoryMesh workflow (CockroachDB checkpointer + case memory)...")
                _workflow = await Workflow.create()
                logger.info("Workflow initialized successfully")
    return _workflow


@app.entrypoint
async def memorymesh_workflow(payload):
    """
    Main entrypoint for AgentCore invocations.

    Args:
        payload: dict with
            - prompt (str, required): the user query
            - session_id (str): conversation identifier — maps to the
              CockroachDB checkpoint thread_id and the durable chat-history
              audit table (defaults to "default-session")
            - actor_id (str): optional, accepted for payload-shape
              compatibility with the upstream AgentCore Memory sample

    Yields:
        Event dicts (e.g. {"type": "text", ...}, {"type": "agent_execution", ...}) —
        NOT pre-formatted SSE strings. BedrockAgentCoreApp does its own
        SSE encoding on whatever this generator yields; yielding an
        already-"data: ...\\n\\n"-formatted string double-wraps it (see the
        comment below) and silently breaks every event the deployed UI
        relies on.
    """
    try:
        prompt = payload.get("prompt")
        session_id = payload.get("session_id", "default-session")
        actor_id = payload.get("actor_id", "default-actor")

        logger.info(f"Workflow invocation - session: {session_id}, actor: {actor_id}")

        if not prompt:
            yield {"type": "error", "content": "No prompt provided in payload"}
            return

        workflow = await get_workflow()
        async for raw_chunk in workflow.stream_query(session_id=session_id, prompt=prompt, actor_id=actor_id):
            # stream_query() yields pre-formatted SSE lines ("data: {...}\n\n")
            # because its other callers (LocalWorkflowBridge, chat_cli.py)
            # parse that exact format themselves. BedrockAgentCoreApp does
            # its OWN SSE encoding on whatever this generator yields —
            # json.dumps() + "data: ...\n\n" — so yielding the already-
            # formatted string here double-wraps it: the deployed runtime
            # ends up sending a JSON string *literal* containing the
            # original SSE line, which the client parses into a plain
            # string instead of an event object, so every field the UI
            # looks for (evt.type, evt.content, ...) is undefined and
            # nothing ever renders. Unwrap back to the raw event dict
            # before yielding so AgentCore only wraps it once.
            unwrapped = raw_chunk[len("data: "):].strip() if raw_chunk.startswith("data: ") else raw_chunk.strip()
            if not unwrapped:
                continue
            try:
                yield json.loads(unwrapped)
            except json.JSONDecodeError:
                yield {"type": "raw", "content": unwrapped}

    except Exception as e:
        error_msg = f"Error in workflow execution: {str(e)}"
        logger.error(error_msg)
        yield {"type": "error", "content": error_msg}


if __name__ == "__main__":
    logger.info("Starting MemoryMesh Agent AgentCore runtime...")
    app.run()
