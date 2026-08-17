#!/usr/bin/env python3
"""Create/migrate every CockroachDB memory table this project uses:

  - checkpoints / checkpoint_blobs / checkpoint_writes  (LangGraph state)
  - message_store                                       (durable chat audit log)
  - case_memory (+ distributed C-SPANN vector index)     (long-term semantic memory)

Idempotent — safe to run on every deploy. Run once against a fresh cluster
before the first `make start-client` / AgentCore deployment.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.winloop import ensure_compatible_event_loop_policy

# Must run before asyncio.run() below creates the event loop — Windows'
# default ProactorEventLoop rejects psycopg's async driver outright.
ensure_compatible_event_loop_policy()

from dotenv import load_dotenv

load_dotenv()

from src.config.logging_config import configure_logging

configure_logging(force_console=True)
logger = logging.getLogger(__name__)


async def main() -> None:
    from src.memory.case_memory import init_case_memory
    from src.memory.checkpointer import build_checkpointer, close_checkpointer
    from src.memory.chat_history import get_session_history

    logger.info("1/3 Setting up LangGraph checkpoint tables (AsyncCockroachDBSaver.setup)...")
    await build_checkpointer()
    await close_checkpointer()
    logger.info("    done: checkpoints, checkpoint_blobs, checkpoint_writes")

    logger.info("2/3 Setting up chat history table (CockroachDBChatMessageHistory)...")
    # create_table_if_not_exists() is a sync wrapper that calls asyncio.run()
    # internally — calling it from here, already inside main()'s running
    # loop, raises "asyncio.run() cannot be called from a running event
    # loop". Await the async implementation directly instead.
    await get_session_history("schema-init")._acreate_table_if_not_exists()
    logger.info("    done: message_store")

    logger.info("3/3 Setting up case memory table + distributed C-SPANN vector index...")
    await init_case_memory()
    logger.info("    done: case_memory")

    logger.info("CockroachDB memory schema ready.")


if __name__ == "__main__":
    asyncio.run(main())
