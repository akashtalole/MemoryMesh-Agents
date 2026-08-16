"""Shared CockroachDB connection plumbing.

Every memory component (checkpointer, chat history, case-memory vector
store) reads the same `COCKROACHDB_URL`. This module owns the one
`CockroachDBEngine` connection pool used by the vector store; the
checkpointer and chat history manage their own psycopg connections per the
langchain-cockroachdb API.
"""

import logging
import os
from functools import lru_cache

from langchain_cockroachdb import CockroachDBEngine

logger = logging.getLogger(__name__)


def get_connection_string() -> str:
    conn_string = os.getenv("COCKROACHDB_URL")
    if not conn_string:
        raise RuntimeError(
            "COCKROACHDB_URL is not set. Point it at a CockroachDB Cloud cluster "
            "or a local 'cockroach demo' instance — see .env.example."
        )
    return conn_string


@lru_cache(maxsize=1)
def get_engine() -> CockroachDBEngine:
    """Process-wide CockroachDBEngine connection pool for vector-store access."""
    conn_string = get_connection_string()
    pool_size = int(os.getenv("COCKROACHDB_POOL_SIZE", "10"))
    max_overflow = int(os.getenv("COCKROACHDB_POOL_MAX_OVERFLOW", "20"))
    logger.info(
        f"Creating CockroachDBEngine connection pool (pool_size={pool_size}, "
        f"max_overflow={max_overflow})"
    )
    return CockroachDBEngine.from_connection_string(
        conn_string, pool_size=pool_size, max_overflow=max_overflow
    )


def get_psycopg_dsn() -> str:
    """Connection string for callers that talk to psycopg directly (e.g. the
    Streamlit memory panel, provisioning scripts) — psycopg only recognises
    postgres/postgresql schemes, whereas langchain-cockroachdb's own factory
    methods accept 'cockroachdb://' as shown in its docs.
    """
    conn_string = get_connection_string()
    if conn_string.startswith("cockroachdb://"):
        return "postgresql://" + conn_string[len("cockroachdb://"):]
    return conn_string
