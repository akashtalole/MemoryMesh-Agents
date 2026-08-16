"""Read-only endpoints the UI polls to show CockroachDB memory state live.

Every query here is a plain SELECT against the same tables the agent itself
writes to (case_memory, message_store) — this is a window into the agent's
actual persistent memory, not a separate mocked-up dashboard.
"""

import logging
import os
from datetime import date, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter

from server.config import get_backend_mode, get_region, get_runtime_arn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["memory"])

CASE_TABLE = os.getenv("COCKROACHDB_CASE_MEMORY_TABLE", "case_memory")
CHAT_TABLE = os.getenv("COCKROACHDB_CHAT_HISTORY_TABLE", "message_store")


def _connect():
    import psycopg

    from src.memory.db import get_psycopg_dsn

    return psycopg.connect(get_psycopg_dsn(), connect_timeout=5)


def _find_jsonb_column(cur, table: str) -> str:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s AND data_type = 'jsonb' LIMIT 1",
        (table,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"No JSONB metadata column found on '{table}'")
    return row[0]


@router.get("/health")
def health() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "status": "ok",
        "backend_mode": get_backend_mode(),
        "runtime_arn": get_runtime_arn(),
        "region": get_region(),
        "cockroachdb_connected": False,
    }
    try:
        with _connect():
            status["cockroachdb_connected"] = True
    except Exception as e:
        status["cockroachdb_error"] = str(e)
    return status


@router.get("/memory/stats")
def memory_stats() -> Dict[str, Any]:
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {CASE_TABLE}")
            case_count = cur.fetchone()[0]

            cur.execute(f"SELECT count(*) FROM {CHAT_TABLE}")
            turn_count = cur.fetchone()[0]

            cur.execute(f"SELECT count(DISTINCT session_id) FROM {CHAT_TABLE}")
            session_count = cur.fetchone()[0]

        return {
            "connected": True,
            "cases": case_count,
            "turns": turn_count,
            "sessions": session_count,
        }
    except Exception as e:
        logger.warning(f"memory_stats query failed: {e}")
        return {"connected": False, "error": str(e), "cases": 0, "turns": 0, "sessions": 0}


@router.get("/memory/cases")
def recent_cases(limit: int = 8) -> List[Dict[str, Any]]:
    limit = max(1, min(limit, 50))
    try:
        with _connect() as conn, conn.cursor() as cur:
            meta_col = _find_jsonb_column(cur, CASE_TABLE)
            cur.execute(
                f"SELECT {meta_col}->>'case_id' AS case_id, "
                f"{meta_col}->>'query' AS query, "
                f"{meta_col}->>'recorded_at' AS recorded_at, "
                f"{meta_col}->>'agents' AS agents "
                f"FROM {CASE_TABLE} ORDER BY recorded_at DESC NULLS LAST LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
        return [
            {"case_id": case_id, "query": query, "recorded_at": recorded_at, "agents": agents}
            for case_id, query, recorded_at, agents in rows
        ]
    except Exception as e:
        logger.warning(f"recent_cases query failed: {e}")
        return []


@router.get("/memory/agent-usage")
def agent_usage() -> List[Dict[str, Any]]:
    """How many recorded cases each agent participated in — powers the
    dashboard's agent-activity bar chart. Reads case_memory.metadata->'agents',
    the same list the orchestrator's routing decision produced for each case.
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            meta_col = _find_jsonb_column(cur, CASE_TABLE)
            cur.execute(
                f"SELECT elem AS agent, count(*) AS n "
                f"FROM {CASE_TABLE}, jsonb_array_elements_text({meta_col}->'agents') AS elem "
                f"WHERE jsonb_typeof({meta_col}->'agents') = 'array' "
                f"GROUP BY elem ORDER BY n DESC"
            )
            rows = cur.fetchall()
        return [{"agent": agent, "count": count} for agent, count in rows]
    except Exception as e:
        logger.warning(f"agent_usage query failed: {e}")
        return []


@router.get("/memory/timeseries")
def cases_timeseries(days: int = 14) -> List[Dict[str, Any]]:
    """Cases recorded per day over the trailing window — zero-filled so the
    chart always spans a continuous range even on a fresh cluster.
    """
    days = max(1, min(days, 90))
    today = date.today()
    series = {(today - timedelta(days=i)): 0 for i in range(days - 1, -1, -1)}

    try:
        with _connect() as conn, conn.cursor() as cur:
            meta_col = _find_jsonb_column(cur, CASE_TABLE)
            cur.execute(
                f"SELECT ({meta_col}->>'recorded_at')::timestamptz::date AS day, count(*) AS n "
                f"FROM {CASE_TABLE} "
                f"WHERE {meta_col}->>'recorded_at' IS NOT NULL "
                f"AND ({meta_col}->>'recorded_at')::timestamptz::date >= %s "
                f"GROUP BY day ORDER BY day",
                (today - timedelta(days=days - 1),),
            )
            for day, count in cur.fetchall():
                if day in series:
                    series[day] = count
    except Exception as e:
        logger.warning(f"cases_timeseries query failed: {e}")

    return [{"date": day.isoformat(), "count": count} for day, count in series.items()]


@router.get("/memory/history/{session_id}")
def session_history(session_id: str) -> List[Dict[str, Any]]:
    try:
        from src.memory.chat_history import get_session_history

        history = get_session_history(session_id)
        return [{"role": m.type, "content": m.content} for m in history.messages]
    except Exception as e:
        logger.warning(f"session_history query failed for {session_id}: {e}")
        return []
