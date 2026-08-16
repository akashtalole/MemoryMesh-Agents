#!/usr/bin/env python3
"""Local chat loop against the workflow — no AWS/AgentCore needed.

Exercises the exact same CockroachDB-backed checkpointer, chat history, and
case-memory recall/persist path that runs in the deployed AgentCore
container; only the transport differs (stdin/stdout instead of the
AgentCore invoke API). Useful for fast iteration and for demonstrating
memory recall: ask a question, then ask a similar one in a new session and
watch `similar_cases` show up in the logs.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.agents import Workflow
from src.config.logging_config import configure_logging

configure_logging(force_console=True)
logger = logging.getLogger(__name__)


async def print_stream(workflow: Workflow, session_id: str, prompt: str) -> None:
    async for raw_chunk in workflow.stream_query(session_id, prompt):
        chunk = raw_chunk[6:] if raw_chunk.startswith("data: ") else raw_chunk
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict) and "error" in data:
            print(f"\n[error] {data['error']}")
            return
        if data.get("type") == "text" and "content" in data:
            print(data["content"], end="", flush=True)
        elif data.get("type") == "agent_execution":
            print(f"\n\n== {data['agent']}: {data['status']} ==")


async def main() -> None:
    workflow = await Workflow.create()
    session_id = f"cli-{asyncio.get_event_loop().time()}"
    print(f"MemoryMesh Agent — local chat (session_id={session_id}). Ctrl-C or 'quit' to exit.\n")

    while True:
        try:
            prompt = input("\nQuery: ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if prompt.lower() in ("quit", "exit", "q"):
            break
        if not prompt:
            continue
        await print_stream(workflow, session_id, prompt)
        print()


if __name__ == "__main__":
    asyncio.run(main())
