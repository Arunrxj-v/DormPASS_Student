"""warden role, student email + enrollment lifecycle, warden_hostels,
account_activation_tokens

Adds:
  * students.email (nullable unique) — normalized @ceconline.edu address
  * students.enrollment_status — provisioning lifecycle state
  * warden_hostels — hostel-scoped authorization grants for wardens
  * account_activation_tokens — single-use password-setup tokens

Existing rows are preserved: current students get ``enrollment_status='active'``
because they already authenticate today; email stays NULL until a warden backfills it.

Revision ID: 0002_warden_enrollment
Revises: 0001_initial
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_warden_enrollment"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("email", sa.String(254), nullable=True),
    )
    op.add_column(
        "students",
        sa.Column("enrollment_status", sa.String(32), nullable=False, server_default="created"),
    )
    op.create_index("ix_students_email", "students", ["email"], unique=True)
    op.create_index("ix_students_enrollment_status", "students", ["enrollment_status"])

    # Existing students can already log in, so they are grandfathered as active.
    op.execute("UPDATE students SET enrollment_status = 'active'")

    op.create_table(
        "warden_hostels",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("hostel_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hostel_id"], ["hostels.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "hostel_id", name="uq_warden_hostel"),
    )
    op.create_index("ix_warden_hostels_user_id", "warden_hostels", ["user_id"])
    op.create_index("ix_warden_hostels_hostel_id", "warden_hostels", ["hostel_id"])

    op.create_table(
        "account_activation_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("token_hash", name="uq_account_activation_token_hash"),
    )
    op.create_index(
        "ix_account_activation_tokens_token_hash", "account_activation_tokens", ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_account_activation_tokens_user_id", "account_activation_tokens", ["user_id"]
    )


def downgrade() -> None:
    op.drop_table("account_activation_tokens")
    op.drop_table("warden_hostels")
    op.drop_column("students", "enrollment_status")
    op.drop_column("students", "email")
