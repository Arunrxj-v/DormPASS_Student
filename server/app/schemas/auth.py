"""Auth + student schemas."""

from __future__ import annotations

import math
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class LoginRequest(BaseModel):
    """POST /auth/login body.

    Students sign in with their college email; wardens/admins use their
    username. ``student_id`` is accepted as a legacy alias so existing roll
    number logins keep working.
    """

    email: str | None = Field(default=None, max_length=254)
    student_id: str | None = Field(default=None, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _identifier_present(self) -> "LoginRequest":
        if not (self.email or self.student_id):
            raise ValueError("Either email or student_id must be provided.")
        return self

    @property
    def identifier(self) -> str:
        """The login key: email when given, else the roll number/username."""
        return (self.email or self.student_id or "").strip()


class GoogleLoginRequest(BaseModel):
    """POST /auth/google body — a Google ID token obtained by the app."""

    id_token: str = Field(min_length=20, max_length=8192)


class ActivateAccountRequest(BaseModel):
    """POST /auth/activate body — redeem a warden-issued setup token."""

    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=8, max_length=128)


class HostelRef(BaseModel):
    """Minimal hostel info embedded in student payloads (includes the room)."""

    id: UUID
    name: str
    block: str | None = None
    room: str | None = None


class StudentPublic(BaseModel):
    """<StudentPublic> from docs/API.md."""

    id: UUID
    student_id: str
    name: str
    email: str | None = None
    enrollment_status: str | None = None
    department: str | None = None
    cohort: str | None = None
    role: str
    account_status: str
    hostel: HostelRef | None = None


class LoginResponse(BaseModel):
    """POST /auth/login 200 body."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    student: StudentPublic


class FaceQuality(BaseModel):
    """Optional capture-quality diagnostics sent by the client."""

    model_config = {"extra": "allow"}

    samples_used: int | None = None
    min_eye_openness: float | None = None


def validate_embedding(embedding: list[float], embedding_dim: int) -> list[float]:
    """Shared embedding checks: length must match dim, all values finite.

    Raises ``ValueError`` (=> 400 invalid_payload) on violation. Used by the
    face-enrollment PUT schema; verify lets non-finite values through so the
    pipeline can reject them as ``face_mismatch`` per step 7 of the contract.
    """
    if embedding_dim < 1 or embedding_dim > 4096:
        raise ValueError("embedding_dim must be between 1 and 4096")
    if len(embedding) != embedding_dim:
        raise ValueError(
            f"embedding length {len(embedding)} does not match embedding_dim {embedding_dim}"
        )
    if not all(math.isfinite(v) for v in embedding):
        raise ValueError("embedding values must all be finite numbers")
    return embedding
