"""LangGraph state checkpointing on CockroachDB.

Replaces the AgentCore Memory checkpointer used by the original sample with
`AsyncCockroachDBSaver`: every workflow-node transition is snapshotted into
CockroachDB's `checkpoints` / `checkpoint_blobs` / `checkpoint_writes`
tables (SERIALIZABLE isolation, ACID, geo-replicated). A crashed container,
a scaled-out AgentCore replica, or a mid-investigation restart all resume
from the exact same point because the state never lived only in-process.
"""

import logging
import os
from typing import Optional

from langchain_cockroachdb import AsyncCockroachDBSaver

from src.memory.db import get_connection_string

logger = logging.getLogger(__name__)

_saver_cm = None
_checkpointer: Optional[AsyncCockroachDBSaver] = None


async def build_checkpointer() -> AsyncCockroachDBSaver:
    """Open (once) and migrate the CockroachDB-backed checkpointer.

    Kept open for the lifetime of the process — a LangGraph runtime serves
    many invocations, so we manage the async context manager manually
    instead of scoping it to a single request.
    """
    global _saver_cm, _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    conn_string = get_connection_string()
    _saver_cm = AsyncCockroachDBSaver.from_conn_string(conn_string)
    _checkpointer = await _saver_cm.__aenter__()
    await _checkpointer.setup()

    ttl_days = os.getenv("CHECKPOINT_TTL_DAYS")
    if ttl_days:
        await _checkpointer.aenable_ttl(ttl_interval=f"{int(ttl_days)} days", cron="@daily")
        logger.info(f"Checkpoint TTL enabled: {ttl_days} days")

    logger.info("AsyncCockroachDBSaver ready — LangGraph state now persists in CockroachDB")
    return _checkpointer


async def close_checkpointer() -> None:
    global _saver_cm, _checkpointer
    if _saver_cm is not None:
        await _saver_cm.__aexit__(None, None, None)
        _saver_cm = None
        _checkpointer = None
        logger.info("CockroachDB checkpointer connection closed")
