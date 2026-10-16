"""Admin/warden endpoints: students CRUD, hostel config, attendance workflow,
biometric deletion, audit logs."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.models import AuditLog, AttendanceRecord, FaceEnrollment
from conftest import assert_error, enroll, lat_offset_for, verify_body


def admin_headers(login) -> dict:
    token = login("admin", "AdminPass123!")
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------
# Students
# --------------------------------------------------------------------------

def test_admin_list_create_patch_students(client, db, make_admin, make_hostel,
                                          make_student, login):
    hostel = make_hostel()
    existing = make_student(hostel=hostel)
    make_admin()
    headers = admin_headers(login)

    # List
    resp = client.get("/api/v1/admin/students", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"items", "page", "page_size", "total_pages", "has_more"}
    assert len(body["items"]) == 1
    assert body["items"][0]["student_id"] == existing.student_id
    assert body["items"][0]["hostel"]["name"] == "Ganga Boys Hostel"

    # Create — no staff-chosen password; a real @ceconline.edu email is required.
    resp = client.post("/api/v1/admin/students", headers=headers, json={
        "student_id": "CS-2023-045", "name": "New Kid",
        "email": "cs-2023-045@ceconline.edu",
        "department": "Computer Science & Engg", "cohort": "2nd Year",
        "room": "210", "hostel_id": str(hostel.id),
    })
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["student_id"] == "CS-2023-045"
    assert created["email"] == "cs-2023-045@ceconline.edu"
    # New accounts start inactive until the student redeems an activation link.
    assert created["account_status"] == "inactive"
    assert created["enrollment_status"] == "created"
    assert created["hostel"]["room"] == "210"

    # Duplicate student id -> 409
    resp = client.post("/api/v1/admin/students", headers=headers, json={
        "student_id": "CS-2023-045", "name": "Impostor",
        "email": "impostor@ceconline.edu"})
    assert_error(resp, 409, "conflict")

    # Duplicate email -> 409
    resp = client.post("/api/v1/admin/students", headers=headers, json={
        "student_id": "CS-2023-099", "name": "Copycat",
        "email": "CS-2023-045@CECONLINE.EDU"})
    assert_error(resp, 409, "conflict")

    # Non-college domain -> rejected (exact domain, not substring).
    # Validation errors use the project's 400 invalid_payload envelope.
    for bad in ("kid@gmail.com", "kid@ceconline.edu.example.com",
                "kid@ceconline.com", "kid@xceconline.edu"):
        resp = client.post("/api/v1/admin/students", headers=headers, json={
            "student_id": "CS-2023-046", "name": "Wrong Domain",
            "email": bad})
        assert_error(resp, 400, "invalid_payload")
        assert "ceconline.edu" in str(resp.json()["error"]["details"])

    # Patch (by roll or by uuid) — name + room.
    resp = client.patch(f"/api/v1/admin/students/CS-2023-045", headers=headers,
                        json={"name": "Renamed Kid", "room": "211"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Renamed Kid"

    # Role and enrollment_status are NOT patchable by any staff endpoint.
    resp = client.patch(f"/api/v1/admin/students/{created['id']}", headers=headers,
                        json={"role": "admin", "enrollment_status": "active"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "student"
    assert resp.json()["enrollment_status"] == "created"

    # Audit rows for both mutations.
    actions = [a.action for a in db.scalars(select(AuditLog)).all()]
    assert "student.create" in actions
    assert "student.update" in actions
    update = db.scalar(select(AuditLog).where(AuditLog.action == "student.update"))
    assert "newpass1234" not in str(update.details)
    assert update.actor_label == "admin"
    # Creation recorded the email but no password material of any kind.
    create = db.scalar(select(AuditLog).where(AuditLog.action == "student.create"))
    assert create.details.get("email") == "cs-2023-045@ceconline.edu"
    assert "password" not in str(create.details).lower()


def test_admin_suspend_and_login_gate(client, db, make_admin, make_hostel,
                                      make_student, login):
    make_student(hostel=make_hostel())
    make_admin()
    headers = admin_headers(login)

    resp = client.post("/api/v1/admin/students/CS-2022-084/suspend", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["account_status"] == "inactive"
    assert resp.json()["enrollment_status"] == "suspended"

    # Suspended student can no longer log in (403 account_suspended).
    resp = client.post("/api/v1/auth/login", json={
        "student_id": "CS-2022-084", "password": "student123!"})
    assert_error(resp, 403, "account_suspended")

    # Audit row names the admin actor and the prior status.
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "student.suspend"))
    assert entry is not None and entry.actor_label == "admin"
    assert entry.details.get("previous_status") == "active"

    # Unsuspend restores the account.
    resp = client.post("/api/v1/admin/students/CS-2022-084/unsuspend", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["account_status"] == "active"
    resp = client.post("/api/v1/auth/login", json={
        "student_id": "CS-2022-084", "password": "student123!"})
    assert resp.status_code == 200, resp.text


def test_admin_unknown_student_404(client, make_admin, login):
    make_admin()
    headers = admin_headers(login)
    assert_error(client.patch("/api/v1/admin/students/CS-0000-000",
                              headers=headers, json={"name": "x"}), 404, "not_found")
    assert_error(client.post("/api/v1/admin/students/CS-0000-000/suspend",
                             headers=headers), 404, "not_found")


# --------------------------------------------------------------------------
# Hostel config
# --------------------------------------------------------------------------

def test_admin_put_hostel_radius_and_verify_honors_it(client, db, make_admin,
                                                      make_hostel, make_student,
                                                      login):
    hostel = make_hostel()  # radius 120
    student = make_student(hostel=hostel)
    token = login(student.student_id, "student123!")
    student_headers = {"Authorization": f"Bearer {token}"}
    enroll(client, student_headers)
    make_admin()
    headers = admin_headers(login)

    # Point ~100 m from the anchor: passes with radius 120...
    resp = client.get(f"/api/v1/admin/hostels", headers=headers)
    assert resp.status_code == 200
    assert resp.json()[0]["hostel_id"] == str(hostel.id)

    # ...but PUT shrinks the radius to 50 -> the same fix is now outside.
    resp = client.put(f"/api/v1/admin/hostels/{hostel.id}", headers=headers,
                      json={"permitted_radius_m": 50.0})
    assert resp.status_code == 200, resp.text
    assert resp.json()["permitted_radius_m"] == 50.0

    body = verify_body(latitude=lat_offset_for(100.0), accuracy_m=5.0)
    resp = client.post("/api/v1/attendance/verify", headers=student_headers, json=body)
    err = assert_error(resp, 403, "outside_geofence")
    assert err["details"]["permitted_radius_m"] == 50.0

    # Restore radius -> same fix now verifies.
    resp = client.put(f"/api/v1/admin/hostels/{hostel.id}", headers=headers,
                      json={"permitted_radius_m": 120.0})
    assert resp.json()["permitted_radius_m"] == 120.0
    resp = client.post("/api/v1/attendance/verify", headers=student_headers, json=body)
    assert resp.status_code == 200, resp.text

    # Audited config change.
    updates = db.scalars(select(AuditLog).where(AuditLog.action == "hostel.update")).all()
    assert len(updates) == 2
    assert {u.details["permitted_radius_m"] for u in updates} == {50.0, 120.0}
    assert all(u.actor_label == "admin" for u in updates)


def test_admin_put_hostel_validation(client, make_admin, make_hostel, login):
    make_admin()
    headers = admin_headers(login)
    hostel = make_hostel()
    resp = client.put(f"/api/v1/admin/hostels/{hostel.id}", headers=headers,
                      json={"window_start": "25:99"})
    assert_error(resp, 400, "invalid_payload")
    resp = client.put(f"/api/v1/admin/hostels/{hostel.id}", headers=headers,
                      json={"face_match_threshold": 1.5})
    assert_error(resp, 400, "invalid_payload")
    resp = client.put(f"/api/v1/admin/hostels/{hostel.id}", headers=headers,
                      json={"timezone": "Mars/Olympus"})
    assert_error(resp, 400, "invalid_payload")
    resp = client.put("/api/v1/admin/hostels/00000000-0000-0000-0000-000000000000",
                      headers=headers, json={"permitted_radius_m": 10.0})
    assert_error(resp, 404, "not_found")


# --------------------------------------------------------------------------
# Attendance workflow: approve / reject / correction / filters
# --------------------------------------------------------------------------

def _pending_student(client, db, make_hostel, make_student, login, roll: str):
    """A student under a no-liveness hostel whose verify yields pending_review."""
    hostel = make_hostel(name=f"Pending Hostel {roll}", block=roll[-2:],
                         require_liveness=False)
    student = make_student(hostel=hostel, roll=roll, name=f"Student {roll}")
    token = login(roll, "student123!")
    headers = {"Authorization": f"Bearer {token}"}
    emb = enroll(client, headers)
    resp = client.post("/api/v1/attendance/verify", headers=headers,
                       json=verify_body(emb, liveness={
                           "method": "antispoof_model_v1", "score": 0.9,
                           "passed": False}))
    assert resp.status_code == 200, resp.text
    assert resp.json()["outcome"] == "pending_review"
    return resp.json()["id"]


def test_admin_attendance_list_filters_and_workflow(client, db, make_admin,
                                                    make_hostel, make_student,
                                                    login):
    make_admin()
    headers = admin_headers(login)

    record_a = _pending_student(client, db, make_hostel, make_student, login,
                                "CS-2022-201")
    record_b = _pending_student(client, db, make_hostel, make_student, login,
                                "CS-2022-202")
    record_c = _pending_student(client, db, make_hostel, make_student, login,
                                "CS-2022-203")

    # List includes pending_review + student identity.
    resp = client.get("/api/v1/admin/attendance?status=pending", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"items", "page", "page_size", "total_pages", "has_more"}
    assert len(body["items"]) == 3
    assert all(i["status"] == "pending" for i in body["items"])
    assert body["items"][0]["student"]["student_id"] in {
        "CS-2022-201", "CS-2022-202", "CS-2022-203"}

    # Filter by roll + date.
    resp = client.get(
        "/api/v1/admin/attendance?student_id=CS-2022-201&date=2026-10-13",
        headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["student"]["student_id"] == "CS-2022-201"

    # Absent filter synthesizes elapsed days (Oct 1-12) without records.
    resp = client.get(
        "/api/v1/admin/attendance?student_id=CS-2022-201&status=absent",
        headers=headers)
    absent_items = resp.json()["items"]
    assert len(absent_items) == 12
    assert all(i["status"] == "absent" for i in absent_items)
    assert absent_items[0]["date"] == "2026-10-12"  # newest first

    # Today has a pending record -> not absent.
    resp = client.get(
        "/api/v1/admin/attendance?student_id=CS-2022-201&status=absent&date=2026-10-13",
        headers=headers)
    assert resp.json()["items"] == []

    # Approve A -> verified.
    resp = client.post(f"/api/v1/admin/attendance/{record_a}/approve", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["outcome"] == "verified"
    assert resp.json()["status"] == "present"
    # Approving twice -> 409.
    resp = client.post(f"/api/v1/admin/attendance/{record_a}/approve", headers=headers)
    assert_error(resp, 409, "conflict")

    # Correction B: pending -> present.
    resp = client.post(f"/api/v1/admin/attendance/{record_b}/correction",
                       headers=headers,
                       json={"new_status": "present", "reason": "warden saw him"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["outcome"] == "verified"

    # Correction C: pending -> absent removes the record.
    resp = client.post(f"/api/v1/admin/attendance/{record_c}/correction",
                       headers=headers,
                       json={"new_status": "absent", "reason": "no show"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "absent"
    assert resp.json()["id"] is None
    assert resp.json()["reason"] == "curfew_window_missed"
    assert db.scalar(select(AttendanceRecord).where(
        AttendanceRecord.id == _uuid(record_c))) is None

    # Reject B (verified) -> record removed, 204.
    resp = client.post(f"/api/v1/admin/attendance/{record_b}/reject", headers=headers)
    assert resp.status_code == 204
    assert db.scalar(select(AttendanceRecord).where(
        AttendanceRecord.id == _uuid(record_b))) is None

    # Every workflow step is audit-logged with the admin actor.
    actions = [a.action for a in db.scalars(select(AuditLog)).all()]
    for expected in ("attendance.approve", "attendance.correction",
                     "attendance.reject"):
        assert expected in actions, actions
    correction = db.scalar(select(AuditLog).where(
        AuditLog.action == "attendance.correction").limit(1))
    assert correction.actor_label == "admin"
    assert "reason" in correction.details


def test_admin_attendance_404(client, make_admin, login):
    make_admin()
    headers = admin_headers(login)
    from uuid import uuid4
    resp = client.post(f"/api/v1/admin/attendance/{uuid4()}/approve", headers=headers)
    assert_error(resp, 404, "not_found")


# --------------------------------------------------------------------------
# Biometric deletion + audit log endpoint
# --------------------------------------------------------------------------

def test_admin_biometric_delete_and_audit_endpoint(client, db, make_admin,
                                                   make_hostel, make_student,
                                                   login):
    hostel = make_hostel()
    student = make_student(hostel=hostel)
    student_token = login(student.student_id, "student123!")
    student_headers = {"Authorization": f"Bearer {student_token}"}
    enroll(client, student_headers)
    make_admin()
    headers = admin_headers(login)

    # Admin sees the enrollment exists.
    resp = client.get("/api/v1/face-enrollment", headers=student_headers)
    assert resp.json()["enrolled"] is True

    resp = client.delete(
        f"/api/v1/admin/students/{student.student_id}/face-enrollment",
        headers=headers)
    assert resp.status_code == 204, resp.text

    # Template gone for the student; audit row names the admin actor.
    assert db.scalar(select(FaceEnrollment).where(
        FaceEnrollment.student_id == student.id)) is None
    resp = client.get("/api/v1/face-enrollment", headers=student_headers)
    assert resp.json()["enrolled"] is False

    entry = db.scalar(select(AuditLog).where(
        AuditLog.action == "face_enrollment.delete"))
    assert entry is not None
    assert entry.actor_label == "admin"
    assert entry.target_id == str(student.id)

    # Audit endpoint shape + ordering (newest first). Several rows now exist
    # (login, enroll, delete), so assert on the delete entry specifically.
    resp = client.get("/api/v1/admin/audit-logs?page=1&page_size=50", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"items", "page", "page_size", "total_pages", "has_more"}
    assert len(body["items"]) >= 1
    item = body["items"][0]
    assert set(item.keys()) == {"id", "actor", "action", "target_type",
                                "target_id", "details", "created_at"}
    assert item["created_at"].endswith("Z")
    delete_entries = [i for i in body["items"] if i["action"] == "face_enrollment.delete"]
    assert delete_entries, [i["action"] for i in body["items"]]
    assert delete_entries[0]["actor"] == "admin"

    # Empty page beyond the end.
    resp = client.get("/api/v1/admin/audit-logs?page=5", headers=headers)
    assert resp.json()["items"] == []


def _uuid(value: str):
    import uuid

    return uuid.UUID(value)
