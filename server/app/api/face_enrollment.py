"""Face enrollment status for the authenticated student: GET /face-enrollment.

Students may READ their own enrollment status but can never create, replace or
delete their own template — enrollment is a warden-initiated operation
(``PUT /warden/students/{id}/face-enrollment``). The mutating verbs are kept
here only to answer with an explicit 403 instead of an opaque 405.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import clock
from ..core.errors import forbidden
from ..db.session import get_session
from ..models import FaceEnrollment, Student
from ..schemas import FaceEnrollmentPublic, FaceEnrollmentPut
from .deps import get_current_student

router = APIRouter(tags=["face-enrollment"])


def _public(row: FaceEnrollment | None) -> FaceEnrollmentPublic:
    if row is None:
        return FaceEnrollmentPublic(enrolled=False, model_version=None, updated_at=None)
    return FaceEnrollmentPublic(
        enrolled=True,
        model_version=row.model_version,
        updated_at=clock.utc_z(row.updated_at),
    )


@router.get("/face-enrollment", response_model=FaceEnrollmentPublic)
def get_enrollment(
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_session),
) -> FaceEnrollmentPublic:
    """Whether the student has an enrolled template (never the template itself)."""
    row = db.scalar(select(FaceEnrollment).where(FaceEnrollment.student_id == student.id))
    return _public(row)


_ENROLL_DENIED = (
    "Face enrollment is performed by your hostel warden. "
    "Contact your warden to enroll or re-enroll your face."
)


@router.put("/face-enrollment", response_model=FaceEnrollmentPublic)
def put_enrollment(
    payload: FaceEnrollmentPut,
    _student: Student = Depends(get_current_student),
) -> FaceEnrollmentPublic:
    """Students cannot enroll their own face — warden-initiated only."""
    raise forbidden(_ENROLL_DENIED)


@router.delete("/face-enrollment", status_code=204)
def delete_enrollment(
    _student: Student = Depends(get_current_student),
) -> Response:
    """Students cannot delete their own template — warden-initiated only."""
    raise forbidden(_ENROLL_DENIED)
