"""Encryption at rest for face templates (Fernet over AES-128-CBC + HMAC).

The stored value is a Fernet token wrapping the L2-normalized float32 bytes of
the embedding. Raw embeddings are never logged.
"""

from __future__ import annotations

import math

import numpy as np
from cryptography.fernet import Fernet, InvalidToken

from ..core.config import settings
from ..core.errors import internal_error


def _fernet() -> Fernet:
    try:
        return Fernet(settings.face_template_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise internal_error() from exc


def l2_normalize(values: list[float]) -> list[float]:
    """Renormalize to unit L2 norm. Non-finite input is rejected upstream;
    a zero vector is stored as-is (it can never match above threshold)."""
    arr = np.asarray(values, dtype=np.float64)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0 or not math.isfinite(norm):
        return [float(v) for v in values]
    return [float(v) / norm for v in (arr / norm).tolist()]


def encrypt_embedding(values: list[float]) -> bytes:
    """Encrypt a normalized embedding as float32 bytes under the Fernet key."""
    arr = np.asarray(values, dtype=np.float32)
    return _fernet().encrypt(arr.tobytes())


def decrypt_embedding(blob: bytes) -> list[float]:
    """Decrypt a stored template back to a list of floats."""
    try:
        raw = _fernet().decrypt(blob)
    except InvalidToken as exc:
        # Wrong/rotated key: never crash the request path with a stack trace
        # that could leak context — surface as an internal error.
        raise internal_error() from exc
    arr = np.frombuffer(raw, dtype=np.float32)
    return [float(v) for v in arr.tolist()]
