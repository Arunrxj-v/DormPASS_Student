"""rooms — managed room registry per hostel

Adds:
  * rooms — (hostel_id, identifier) unique registry with advisory capacity

No student data is rewritten: ``students.room`` remains a free-text string.
The registry is enforced on student create/update only when a hostel has
rooms registered; hostels without rooms keep accepting free-text rooms.

Revision ID: 0003_rooms
Revises: 0002_warden_enrollment
Create Date: 2026-10-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_rooms"
down_revision: Union[str, None] = "0002_warden_enrollment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("hostel_id", sa.Uuid(), nullable=False),
        sa.Column("identifier", sa.String(32), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hostel_id"], ["hostels.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("hostel_id", "identifier", name="uq_room_hostel_identifier"),
    )
    op.create_index("ix_rooms_hostel_id", "rooms", ["hostel_id"])


def downgrade() -> None:
    op.drop_index("ix_rooms_hostel_id", table_name="rooms")
    op.drop_table("rooms")
