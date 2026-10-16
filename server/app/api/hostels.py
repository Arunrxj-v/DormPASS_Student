"""Hostel geofence retrieval — server is the single source of truth."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..db.session import get_session
from ..models import Student
from ..schemas import GeofencePublic
from .deps import get_current_student

router = APIRouter(tags=["hostels"])


@router.get("/hostels/me/geofence", response_model=GeofencePublic)
def my_geofence(
    student: Student = Depends(get_current_student),
    _db: Session = Depends(get_session),
) -> GeofencePublic:
    """Geofence + policy for the student's assigned hostel.

    Clients cannot supply or widen coordinates/radius — this payload is the
    authoritative rule the server re-checks on every verify.
    """
    hostel = student.hostel
    if hostel is None:
        raise AppError(403, "hostel_not_configured",
                       "No hostel is assigned to this student.")
    return GeofencePublic.from_hostel(hostel)
