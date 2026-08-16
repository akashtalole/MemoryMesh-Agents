"""Tiny PCA helper (pure numpy, no sklearn) for projecting case-memory
embeddings down to 2D for the Vector Memory Map, plus a cached basis so a
single query typed into the search box can be projected onto the *same*
axes as the plotted cases instead of jumping around between requests.
"""

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 30
_cache: Dict[str, Any] = {"mean": None, "components": None, "scale": None, "fitted_at": 0.0}
_lock = threading.Lock()


def fit(vectors: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Top-2-component PCA via SVD. Returns (mean, components[2, dim])."""
    mean = vectors.mean(axis=0)
    centered = vectors - mean
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    components = vt[:2]
    return mean, components


def project(vectors: np.ndarray, mean: np.ndarray, components: np.ndarray) -> np.ndarray:
    return (vectors - mean) @ components.T


def fit_and_cache(vectors: np.ndarray) -> np.ndarray:
    """Fits PCA on the given vectors, caches the basis for `project_point`,
    and returns the (normalized to roughly [-1, 1]) 2D coordinates."""
    mean, components = fit(vectors)
    coords = project(vectors, mean, components)
    scale = float(np.abs(coords).max()) or 1.0
    with _lock:
        _cache["mean"] = mean
        _cache["components"] = components
        _cache["scale"] = scale
        _cache["fitted_at"] = time.time()
    return coords / scale


def project_point(vector: List[float]) -> Optional[Dict[str, float]]:
    """Projects a single new vector using the cached basis. Returns None if
    no basis has been fitted yet (embedding-map hasn't been called) or the
    cache is stale relative to the case table."""
    with _lock:
        mean, components, scale = _cache["mean"], _cache["components"], _cache["scale"]
    if mean is None:
        return None
    coords = project(np.array([vector], dtype=float), mean, components)[0]
    return {"x": float(coords[0] / scale), "y": float(coords[1] / scale)}


def cache_age_seconds() -> float:
    with _lock:
        fitted_at = _cache["fitted_at"]
    return time.time() - fitted_at if fitted_at else float("inf")


def is_stale() -> bool:
    return cache_age_seconds() > _CACHE_TTL_SECONDS


def parse_vector(raw: str) -> List[float]:
    """Parses CockroachDB's VECTOR textual form, e.g. '[0.1,0.2,0.3]'."""
    try:
        return [float(x) for x in raw.strip("[]").split(",") if x.strip()]
    except (ValueError, AttributeError):
        return []
