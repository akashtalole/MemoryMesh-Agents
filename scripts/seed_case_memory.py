#!/usr/bin/env python3
"""Seed a handful of past investigations into CockroachDB's case_memory
vector table so a fresh demo immediately shows semantic recall working,
instead of needing to run the full workflow a few times first.

Run after `python scripts/init_memory_schema.py`.
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

SEED_CASES = [
    {
        "session_id": "seed-001",
        "query_text": "What was the trading activity for AAPL on March 15, 2024 and which brokers were most active?",
        "required_agents": ["security_monitor", "risk_monitor"],
        "summary": (
            "- AAPL traded actively across the session with volume concentrated between 09:30-10:35.\n"
            "- ALPHA_CAPITAL, SUMMIT_TRADING, and VERTEX_SECURITIES accounted for the largest share of executions.\n"
            "- VERTEX_SECURITIES carried an elevated risk score (0.45) with an anomaly flag on AAPL.\n"
            "CASE SUMMARY: AAPL, 2024-03-15 — elevated broker risk concentration in VERTEX_SECURITIES."
        ),
    },
    {
        "session_id": "seed-002",
        "query_text": "Analyze MSFT's price movement and broker risk scores between March 10-15, 2024",
        "required_agents": ["broker_monitor"],
        "summary": (
            "- MSFT showed a steady upward drift over the window with no single-day outsized moves.\n"
            "- MERIDIAN_BROKERS carried the highest risk score (0.67) with an anomaly flag on MSFT.\n"
            "CASE SUMMARY: MSFT, 2024-03-10..15 — MERIDIAN_BROKERS flagged for elevated risk on MSFT."
        ),
    },
    {
        "session_id": "seed-003",
        "query_text": "Show me unusual trading patterns for TSLA on March 20, 2024 and check for related market news",
        "required_agents": ["security_monitor", "intel_analyst"],
        "summary": (
            "- TSLA order book showed transient depth imbalance around the open, consistent with normal price discovery.\n"
            "- No corroborating public news/regulatory filings were found for the anomaly window.\n"
            "CASE SUMMARY: TSLA, 2024-03-20 — no external catalyst found for the intraday imbalance."
        ),
    },
]


async def main() -> None:
    from src.memory.case_memory import init_case_memory, record_case

    await init_case_memory()

    for case in SEED_CASES:
        case_id = await record_case(
            session_id=case["session_id"],
            query_text=case["query_text"],
            required_agents=case["required_agents"],
            summary=case["summary"],
            metadata={"seed": True},
        )
        logger.info(f"Seeded case {case_id}: {case['query_text'][:60]}...")

    logger.info(f"Seeded {len(SEED_CASES)} case(s) into CockroachDB case memory.")


if __name__ == "__main__":
    asyncio.run(main())
