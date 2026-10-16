"""initial schema — users, students, hostels, face_enrollments, attendance_records,
attendance_attempts, audit_logs, revoked_tokens

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("account_status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username", name="users_username_key"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "hostels",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("block", sa.String(32), nullable=True),
        sa.Column("anchor_label", sa.String(128), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("permitted_radius_m", sa.Float(), nullable=False),
        sa.Column("max_location_accuracy_m", sa.Float(), nullable=False),
        sa.Column("boundary_policy", sa.String(32), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("window_start", sa.String(5), nullable=False),
        sa.Column("window_end", sa.String(5), nullable=False),
        sa.Column("require_liveness", sa.Boolean(), nullable=False),
        sa.Column("face_match_threshold", sa.Float(), nullable=False),
        sa.Column("warden_name", sa.String(128), nullable=True),
        sa.Column("warden_extension", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", "block", name="uq_hostel_name_block"),
    )

    op.create_table(
        "students",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("department", sa.String(128), nullable=True),
        sa.Column("cohort", sa.String(64), nullable=True),
        sa.Column("room", sa.String(32), nullable=True),
        sa.Column("hostel_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hostel_id"], ["hostels.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", name="students_user_id_key"),
        sa.UniqueConstraint("student_id", name="students_student_id_key"),
    )
    op.create_index("ix_students_student_id", "students", ["student_id"])
    op.create_index("ix_students_hostel_id", "students", ["hostel_id"])

    op.create_table(
        "face_enrollments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("quality", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("student_id", name="face_enrollments_student_id_key"),
    )
    op.create_index("ix_face_enrollments_student_id", "face_enrollments", ["student_id"])

    op.create_table(
        "attendance_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("reference", sa.String(32), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("hostel_id", sa.Uuid(), nullable=True),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("face_similarity", sa.Float(), nullable=True),
        sa.Column("liveness_score", sa.Float(), nullable=True),
        sa.Column("liveness_method", sa.String(48), nullable=True),
        sa.Column("gate", sa.String(48), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hostel_id"], ["hostels.id"], ondelete="SET NULL"),
        # The duplicate-prevention guarantee, enforced by the database.
        sa.UniqueConstraint("student_id", "attendance_date", name="uq_attendance_student_date"),
        sa.UniqueConstraint("reference", name="uq_attendance_reference"),
    )
    op.create_index("ix_attendance_records_student_id", "attendance_records", ["student_id"])
    op.create_index("ix_attendance_records_attendance_date", "attendance_records", ["attendance_date"])
    op.create_index("ix_attendance_records_reference", "attendance_records", ["reference"])

    op.create_table(
        "attendance_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("rejection_code", sa.String(48), nullable=True),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_attendance_attempts_student_id", "attendance_attempts", ["student_id"])
    op.create_index("ix_attendance_attempts_created_at", "attendance_attempts", ["created_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_label", sa.String(64), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("jti", name="revoked_tokens_jti_key"),
    )
    op.create_index("ix_revoked_tokens_jti", "revoked_tokens", ["jti"])
    op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_table("revoked_tokens")
    op.drop_table("audit_logs")
    op.drop_table("attendance_attempts")
    op.drop_table("attendance_records")
    op.drop_table("face_enrollments")
    op.drop_table("students")
    op.drop_table("hostels")
    op.drop_table("users")
