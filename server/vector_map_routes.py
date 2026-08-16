"""Vector Memory Map + semantic search — makes the distributed C-SPANN
vector index something you can look at and query directly, not just an
internal detail the agents use.

`GET /memory/embedding-map` projects every case_memory embedding to 2D
(PCA) so the whole case history renders as a point cloud. `POST
/memory/search` runs the exact same `recall_similar_cases` function the
case_triage and recall_case_memory nodes use internally, and projects the
query onto the *same* cached PCA basis so it can be plotted alongside the
cases it's semantically close to.
"""

import logging
from typing import Any, Dict, List

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from server.memory_routes import CASE_TABLE, _connect, _find_jsonb_column
from server.pca import fit_and_cache, parse_vector, project_point

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["vector-map"])


class SearchRequest(BaseModel):
    query: str
    k: int = 5


@router.get("/memory/embedding-map")
def embedding_map(limit: int = 300) -> Dict[str, Any]:
    limit = max(2, min(limit, 1000))
    try:
        with _connect() as conn, conn.cursor() as cur:
            meta_col = _find_jsonb_column(cur, CASE_TABLE)
            cur.execute(
                f"SELECT {meta_col}->>'case_id' AS case_id, "
                f"{meta_col}->>'query' AS query, "
                f"{meta_col}->>'recorded_at' AS recorded_at, "
                f"embedding::STRING AS vec "
                f"FROM {CASE_TABLE} LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.warning(f"embedding_map query failed: {e}")
        return {"points": [], "error": str(e)}

    case_ids: List[str] = []
    queries: List[str] = []
    recorded: List[str] = []
    vectors: List[List[float]] = []
    for case_id, query, recorded_at, vec_str in rows:
        vec = parse_vector(vec_str) if vec_str else []
        if len(vec) >= 2:
            case_ids.append(case_id)
            queries.append(query)
            recorded.append(recorded_at)
            vectors.append(vec)

    if len(vectors) < 2:
        return {"points": []}

    coords = fit_and_cache(np.array(vectors, dtype=float))

    return {
        "points": [
            {
                "case_id": case_ids[i],
                "query": queries[i],
                "recorded_at": recorded[i],
                "x": float(coords[i][0]),
                "y": float(coords[i][1]),
            }
            for i in range(len(vectors))
        ]
    }


@router.post("/memory/search")
async def semantic_search(body: SearchRequest) -> Dict[str, Any]:
    from src.memory.case_memory import recall_similar_cases
    from src.memory.embeddings import get_embeddings

    k = max(1, min(body.k, 20))

    try:
        matches = await recall_similar_cases(body.query, k=k, score_threshold=0.0)
    except Exception as e:
        logger.warning(f"semantic_search recall failed: {e}")
        matches = []

    point = None
    try:
        vector = get_embeddings().embed_query(body.query)
        point = project_point(vector)
    except Exception as e:
        logger.warning(f"semantic_search embedding/projection failed: {e}")

    return {"query": body.query, "point": point, "matches": matches}
