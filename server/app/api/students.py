"""Student self-service: GET /students/me."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db.session import get_session
from ..models import Student
from ..schemas import StudentPublic
from ..services.students import build_student_public
from .deps import get_current_student

router = APIRouter(tags=["students"])


@router.get("/students/me", response_model=StudentPublic)
def students_me(
    student: Student = Depends(get_current_student),
    _db: Session = Depends(get_session),
) -> StudentPublic:
    """The authenticated student's profile (hostel + room included)."""
    return build_student_public(student.user, student)
