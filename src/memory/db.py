"""Shared CockroachDB connection plumbing.

Every memory component (checkpointer, chat history, case-memory vector
store) reads the same `COCKROACHDB_URL`. This module owns the one
`CockroachDBEngine` connection pool used by the vector store; the
checkpointer and chat history manage their own psycopg connections per the
langchain-cockroachdb API.
"""

import logging
import os
import urllib.request
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from langchain_cockroachdb import CockroachDBEngine

logger = logging.getLogger(__name__)

_DEFAULT_CERT_PATH = Path.home() / ".postgresql" / "root.crt"


def _ensure_cluster_ca_cert(cluster_id: str) -> str:
    """Downloads (once) and caches this CockroachDB Cloud cluster's CA cert
    to ~/.postgresql/root.crt — the same file the Cloud console's own
    connect instructions have you fetch by hand with
    `curl --create-dirs -o $HOME/.postgresql/root.crt
    'https://cockroachlabs.cloud/clusters/<cluster-id>/cert'`. Done here at
    runtime instead of baked into the Docker image, so the exact same image
    works for any cluster (dev, prod, a rotated cluster) via
    COCKROACHDB_CLUSTER_ID alone, no rebuild — consistent with every other
    credential in this project being injected at runtime, never baked in.
    """
    if not _DEFAULT_CERT_PATH.exists():
        _DEFAULT_CERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://cockroachlabs.cloud/clusters/{cluster_id}/cert"
        logger.info(f"Downloading CockroachDB Cloud CA cert for cluster {cluster_id}")
        urllib.request.urlretrieve(url, _DEFAULT_CERT_PATH)
    return str(_DEFAULT_CERT_PATH)


def _with_default_sslrootcert(conn_string: str) -> str:
    """CockroachDB Cloud connection strings default to sslmode=verify-full
    with no sslrootcert, which makes libpq look for a CA file at
    ~/.postgresql/root.crt — a file that exists on a developer's own machine
    (downloaded once from the Cloud console) but not in any container image
    we ship, unless one of these puts it there. In priority order:

    1. sslrootcert already set explicitly (e.g. a real file path) — leave
       it alone.
    2. The file already exists at ~/.postgresql/root.crt — either baked
       into the image at build time (see Dockerfile / Dockerfile.web's
       COCKROACHDB_CLUSTER_ID build arg, populated via `curl ...
       'https://cockroachlabs.cloud/clusters/<id>/cert'` in the same step
       that creates the app user) or left by a previous
       _ensure_cluster_ca_cert() call. This IS libpq's own default lookup
       path, so there's nothing to add to the connection string.
    3. COCKROACHDB_CLUSTER_ID is set — fetch that cluster's actual CA cert
       at runtime instead (see _ensure_cluster_ca_cert). Needed for
       clusters whose certificate isn't publicly-trusted-CA-signed, when
       it wasn't baked into the image.
    4. Otherwise, sslrootcert=system — sufficient for clusters that *are*
       publicly-trusted-CA-signed.
    """
    parts = urlsplit(conn_string)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if query.get("sslmode") not in ("verify-full", "verify-ca") or "sslrootcert" in query:
        return conn_string

    if _DEFAULT_CERT_PATH.exists():
        return conn_string

    cluster_id = os.getenv("COCKROACHDB_CLUSTER_ID")
    query["sslrootcert"] = _ensure_cluster_ca_cert(cluster_id) if cluster_id else "system"
    parts = parts._replace(query=urlencode(query))
    return urlunsplit(parts)


def get_connection_string() -> str:
    conn_string = os.getenv("COCKROACHDB_URL")
    if not conn_string:
        raise RuntimeError(
            "COCKROACHDB_URL is not set. Point it at a CockroachDB Cloud cluster "
            "or a local 'cockroach demo' instance — see .env.example."
        )
    return _with_default_sslrootcert(conn_string)


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
