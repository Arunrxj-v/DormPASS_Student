"""Room registry helpers: validate student room assignments against it.

Policy (documented in docs/API.md):
  * a hostel with registered rooms only accepts those identifiers,
  * a hostel with NO registered rooms accepts any free-text room (backwards
    compatible with rosters created before room management existed),
  * comparisons are case-insensitive and whitespace-trimmed,
  * a room cannot be deleted while students are assigned to it.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import conflict, invalid_payload
from ..models import Room, Student


def _identifier(value: str) -> str:
    return value.strip()


def rooms_registered(db: Session, hostel_id: UUID) -> int:
    """How many rooms this hostel has registered."""
    return int(
        db.scalar(
            select(func.count()).select_from(Room).where(Room.hostel_id == hostel_id)
        )
        or 0
    )


def validate_student_room(db: Session, *, hostel_id: UUID | None, room: str | None) -> None:
    """Reject a student room that is not in the hostel's registry.

    No-op when there is no hostel, no room, or no registry for that hostel.
    Raises 400 ``invalid_payload`` otherwise.
    """
    if hostel_id is None or room is None:
        return
    value = _identifier(room)
    if not value:
        return
    if rooms_registered(db, hostel_id) == 0:
        return
    match = db.scalar(
        select(Room.id).where(
            Room.hostel_id == hostel_id,
            func.lower(Room.identifier) == value.lower(),
        )
    )
    if match is None:
        raise invalid_payload(
            f"Room '{value}' is not registered for this hostel.",
            details={"room": value, "hint": "Register it under admin hostel rooms first."},
        )


def occupied_count(db: Session, *, hostel_id: UUID, identifier: str) -> int:
    """Students currently assigned to this room (case-insensitive)."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(Student)
            .where(
                Student.hostel_id == hostel_id,
                func.lower(func.coalesce(Student.room, "")) == identifier.strip().lower(),
            )
        )
        or 0
    )


def assert_room_deletable(db: Session, room: Room) -> None:
    """Refuse to delete a room that students are still assigned to."""
    occupants = occupied_count(db, hostel_id=room.hostel_id, identifier=room.identifier)
    if occupants:
        raise conflict(
            f"{occupants} student(s) are assigned to room {room.identifier}. "
            "Move them to another room first.",
            details={"occupants": occupants, "room": room.identifier},
        )
