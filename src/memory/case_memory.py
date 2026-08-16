"""Long-term semantic memory: past surveillance cases, stored and recalled
via CockroachDB's native VECTOR type and distributed C-SPANN index.

This is what makes the agent's memory more than a chat transcript: every
finished investigation is embedded and written here, and every new query
starts by asking "have we seen this pattern before?" across *every* prior
session, not just the current thread. As the case history grows the C-SPANN
index keeps recall fast without a separate vector database to provision,
reindex, or keep consistent with the operational data.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_cockroachdb import (
    AsyncCockroachDBVectorStore,
    CSPANNIndex,
    DistanceStrategy,
)

from src.memory.db import get_engine
from src.memory.embeddings import get_embedding_dimension, get_embeddings

logger = logging.getLogger(__name__)

CASE_MEMORY_TABLE = os.getenv("COCKROACHDB_CASE_MEMORY_TABLE", "case_memory")

_vectorstore: Optional[AsyncCockroachDBVectorStore] = None


async def init_case_memory() -> AsyncCockroachDBVectorStore:
    """Ensure the case_memory table + distributed vector index exist, and
    build the vector store handle. Idempotent — safe to call on every boot.
    """
    global _vectorstore

    engine = get_engine()
    await engine.ainit_vectorstore_table(
        table_name=CASE_MEMORY_TABLE,
        vector_dimension=get_embedding_dimension(),
        distance_strategy=DistanceStrategy.COSINE,
        overwrite_existing=False,
        drop_if_exists=False,
    )

    _vectorstore = AsyncCockroachDBVectorStore(
        engine=engine,
        embeddings=get_embeddings(),
        collection_name=CASE_MEMORY_TABLE,
        distance_strategy=DistanceStrategy.COSINE,
    )

    try:
        await _vectorstore.aapply_vector_index(
            CSPANNIndex(distance_strategy=DistanceStrategy.COSINE)
        )
        logger.info(f"C-SPANN distributed vector index ensured on '{CASE_MEMORY_TABLE}'")
    except Exception as e:
        # Index creation is idempotent server-side in normal operation; log
        # instead of failing startup so a transient DDL race never takes the
        # workflow down.
        logger.warning(f"Could not create/verify vector index on '{CASE_MEMORY_TABLE}': {e}")

    logger.info(f"Case memory ready: table='{CASE_MEMORY_TABLE}' dim={get_embedding_dimension()}")
    return _vectorstore


def get_case_memory() -> AsyncCockroachDBVectorStore:
    if _vectorstore is None:
        raise RuntimeError("Case memory not initialised — call init_case_memory() at startup")
    return _vectorstore


async def record_case(
    *,
    session_id: str,
    query_text: str,
    required_agents: List[str],
    summary: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Embed and persist a finished investigation as long-term memory."""
    vectorstore = get_case_memory()
    case_id = str(uuid.uuid4())
    doc_metadata = {
        "case_id": case_id,
        "session_id": session_id,
        "query": query_text,
        "agents": required_agents,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        **(metadata or {}),
    }
    text = f"QUERY: {query_text}\n\nFINDINGS:\n{summary}"

    await vectorstore.aadd_texts([text], metadatas=[doc_metadata], ids=[case_id])
    logger.info(f"Recorded case {case_id} into CockroachDB case memory (session={session_id})")
    return case_id


async def recall_similar_cases(
    query_text: str,
    k: Optional[int] = None,
    score_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Semantic search over every past investigation, regardless of session."""
    vectorstore = get_case_memory()
    k = k if k is not None else int(os.getenv("CASE_MEMORY_RECALL_K", "3"))
    score_threshold = (
        score_threshold
        if score_threshold is not None
        else float(os.getenv("CASE_MEMORY_SCORE_THRESHOLD", "0.55"))
    )

    try:
        results = await vectorstore.asimilarity_search_with_relevance_scores(
            query_text, k=k, score_threshold=score_threshold
        )
    except Exception as e:
        logger.warning(f"Case memory recall failed, continuing without prior context: {e}")
        return []

    return [
        {
            "score": round(float(score), 4),
            "case_id": doc.metadata.get("case_id"),
            "query": doc.metadata.get("query"),
            "recorded_at": doc.metadata.get("recorded_at"),
            "findings": doc.page_content,
        }
        for doc, score in results
    ]
