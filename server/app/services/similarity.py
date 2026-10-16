"""Cosine similarity between face embeddings (server-side, authoritative)."""

from __future__ import annotations

import math
import numpy as np


def all_finite(values: list[float]) -> bool:
    """True when every value is a finite float (no NaN/Inf)."""
    return all(math.isfinite(v) for v in values)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors; returns 0.0 for zero/length mismatch.

    Callers must have validated finiteness — NaN inputs are rejected upstream
    by the verify pipeline (contract step 7).
    """
    if len(a) != len(b) or not a:
        return 0.0
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)
