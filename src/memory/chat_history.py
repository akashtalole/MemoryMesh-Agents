"""Durable, human-readable conversation log on CockroachDB.

Separate from the LangGraph checkpointer on purpose: the checkpointer stores
opaque, resumable graph state; `message_store` here is a plain
session_id -> messages table a compliance reviewer (or a demo audience) can
`SELECT * FROM message_store WHERE session_id = ...` and read directly —
the kind of immutable audit trail market-surveillance workflows actually
require.
"""

import logging
import os

from langchain_cockroachdb import CockroachDBChatMessageHistory

logger = logging.getLogger(__name__)

TABLE_NAME = os.getenv("COCKROACHDB_CHAT_HISTORY_TABLE", "message_store")


def get_session_history(session_id: str) -> CockroachDBChatMessageHistory:
    history = CockroachDBChatMessageHistory(
        session_id=session_id,
        connection_string=os.environ["COCKROACHDB_URL"],
        table_name=TABLE_NAME,
    )
    return history


def record_turn(session_id: str, user_query: str, assistant_response: str) -> None:
    """Append one completed turn to the durable audit log. Best-effort: a
    logging failure here must never fail the surveillance workflow itself.
    """
    try:
        history = get_session_history(session_id)
        history.create_table_if_not_exists()
        history.add_user_message(user_query)
        history.add_ai_message(assistant_response)
        logger.info(f"Recorded turn in CockroachDB chat history (session={session_id})")
    except Exception as e:
        logger.error(f"Failed to record chat history turn for session {session_id}: {e}")
