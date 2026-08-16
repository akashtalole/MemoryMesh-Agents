"""Strands tools that let an agent explicitly query CockroachDB's memory
layer — distinct from the automatic recall_case_memory/persist_case_memory
graph nodes in workflow.py. Those two run unconditionally on every request;
these let a specialist reason about *when* and *why* to consult memory.
"""

import json
import logging

from strands import tool

logger = logging.getLogger(__name__)


@tool
async def recall_similar_investigations(query: str, k: int = 5) -> str:
    """Search CockroachDB's long-term case memory (distributed vector index)
    for prior investigations similar to the given pattern or question.

    Use this to judge whether the current situation has come up before —
    and, if so, whether past investigations confirmed a real issue or
    turned out to be a false positive — before deciding on priority.

    Args:
        query: Description of the current pattern or question to check
            against case history (e.g. "AAPL wash trading by ALPHA_CAPITAL").
        k: Maximum number of similar cases to return.

    Returns:
        str: JSON array of matches, each with case_id, query, findings,
        recorded_at, and a similarity score (higher is more similar).
    """
    from src.memory.case_memory import recall_similar_cases

    logger.info(f"recall_similar_investigations called: query={query!r} k={k}")
    results = await recall_similar_cases(query, k=k, score_threshold=0.0)
    return json.dumps(results, indent=2)


@tool
def get_session_audit_trail(session_id: str) -> str:
    """Retrieve the durable, human-readable audit log for a session from
    CockroachDB's message_store table — every completed turn (user query +
    final answer), independent of internal LangGraph checkpoint state.

    Args:
        session_id: The session/thread id to retrieve the audit trail for.

    Returns:
        str: JSON array of {role, content} for every logged turn, oldest
        first. Empty array if the session has no logged turns yet.
    """
    from src.memory.chat_history import get_session_history

    logger.info(f"get_session_audit_trail called: session_id={session_id}")
    try:
        history = get_session_history(session_id)
        messages = [{"role": m.type, "content": m.content} for m in history.messages]
    except Exception as e:
        logger.warning(f"get_session_audit_trail failed for {session_id}: {e}")
        messages = []
    return json.dumps(messages, indent=2)
