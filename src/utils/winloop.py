"""Windows-only asyncio event loop fix.

psycopg's async driver refuses to run under Windows' default
`ProactorEventLoop` ("Psycopg cannot use the 'ProactorEventLoop' to run in
async mode"), because it needs a selector-based loop to do socket I/O the
way it expects. Every other platform's default loop is already
selector-based (epoll/kqueue), so this is a Windows-only problem — but it
hits every entrypoint that opens a CockroachDB connection: the FastAPI
server, the AgentCore container entrypoint, and every standalone script.

Call `ensure_compatible_event_loop_policy()` once, as early as possible in
each entrypoint (before anything creates an event loop) — it's a no-op on
non-Windows platforms.
"""

import asyncio
import sys


def ensure_compatible_event_loop_policy() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
