"""Students can never modify their own attendance — no routes exist."""

from __future__ import annotations

from uuid import uuid4
import uuid

from conftest import assert_error, enroll, verify_body


def test_no_patch_route_for_attendance_records(student_env):
    """Direct PATCH attempts against record-shaped paths 404 (no such route)."""
    env = student_env
    fake_id = uuid4()
    for path in (f"/api/v1/attendance/records/{fake_id}",
                 f"/api/v1/attendance/{fake_id}",
                 "/api/v1/attendance"):
        resp = env.client.patch(path, headers=env.headers,
                                json={"outcome": "verified"})
        assert_error(resp, 404, "not_found")


def test_method_not_allowed_on_existing_paths(student_env):
    """Methods the contract never defines answer 405 (envelope intact)."""
    env = student_env
    resp = env.client.patch("/api/v1/attendance/verify",
                            headers=env.headers, json={})
    assert resp.status_code == 405
    assert resp.json()["error"]["code"] == "not_found"

    resp = env.client.put("/api/v1/attendance/history", headers=env.headers, json={})
    assert_error(resp, 405, "not_found")

    resp = env.client.delete("/api/v1/attendance/status", headers=env.headers)
    assert_error(resp, 405, "not_found")


def test_student_cannot_call_admin_workflow_on_own_attendance(student_env, db):
    """Even with a record id, the admin correction route rejects students."""
    from sqlalchemy import select

    from app.models import AttendanceRecord

    env = student_env
    emb = enroll(env.client, env.headers)
    resp = env.client.post("/api/v1/attendance/verify", headers=env.headers,
                           json=verify_body(emb))
    assert resp.status_code == 200, resp.text
    record_id = resp.json()["id"]

    resp = env.client.post(
        f"/api/v1/admin/attendance/{record_id}/correction",
        headers=env.headers, json={"new_status": "absent", "reason": "self edit"},
    )
    assert_error(resp, 403, "forbidden")

    # Record untouched.
    record = db.scalar(select(AttendanceRecord).where(
        AttendanceRecord.id == uuid.UUID(record_id)))
    assert record is not None and record.outcome == "verified"
