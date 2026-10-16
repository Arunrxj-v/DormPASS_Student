"""Face enrollment schemas."""

from __future__ import annotations

from pydantic import BaseModel, field_validator, model_validator

from .auth import FaceQuality, validate_embedding


class FaceEnrollmentPut(BaseModel):
    """PUT /face-enrollment body.

    Server validates dim/finite, L2-renormalizes and encrypts (never logs).
    """

    embedding: list[float]
    embedding_dim: int
    model_version: str = "mobilefacenet_tflite_128_v1"
    quality: FaceQuality | None = None

    @field_validator("embedding_dim")
    @classmethod
    def _dim_bounds(cls, value: int) -> int:
        if value < 1 or value > 4096:
            raise ValueError("embedding_dim must be between 1 and 4096")
        return value

    @model_validator(mode="after")
    def _embedding_valid(self) -> "FaceEnrollmentPut":
        # Runs after every field is set, so embedding_dim is always present
        # regardless of declaration order.
        validate_embedding(self.embedding, self.embedding_dim)
        return self
