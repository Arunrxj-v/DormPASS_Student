"""Face enrollment: warden-driven only, validation, and student denial."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import AuditLog, FaceEnrollment
from conftest import assert_error, base_embedding, enroll, staff_headers


def test_warden_enrolls_student_and_student_reads_status(student_env, db):
    env = student_env
    headers = env.headers

    # Student sees own status: not enrolled initially.
    resp = env.client.get("/api/v1/face-enrollment", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"enrolled": False, "model_version": None, "updated_at": None}

    # A warden performs the enrollment on the student's behalf.
    emb = enroll(env.client, headers)
    resp = env.client.get("/api/v1/face-enrollment", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["enrolled"] is True
    assert body["model_version"] == "mobilefacenet_tflite_128_v1"
    assert body["updated_at"].endswith("Z")

    # Exactly one template row, encrypted at rest (never plaintext).
    row = db.scalar(select(FaceEnrollment).where(
        FaceEnrollment.student_id == env.student.id))
    assert row is not None
    assert row.embedding_dim == 128
    assert row.embedding != str(emb).encode()
    assert len(row.embedding) > 128  # Fernet token wrapping 128 float32s

    # Re-enroll (warden) = upsert, still one row.
    emb2 = [v + 0.001 for v in base_embedding()]
    enroll(env.client, headers, emb2)
    count = db.scalar(select(func.count(FaceEnrollment.id)).where(
        FaceEnrollment.student_id == env.student.id))
    assert count == 1

    # Warden deletes -> 204, gone.
    resp = env.client.delete(
        f"/api/v1/warden/students/{env.student.student_id}/face-enrollment",
        headers=staff_headers(env.client))
    assert resp.status_code == 204
    resp = env.client.get("/api/v1/face-enrollment", headers=headers)
    assert resp.json()["enrolled"] is False

    # Re-enroll works.
    enroll(env.client, headers)
    resp = env.client.get("/api/v1/face-enrollment", headers=headers)
    assert resp.json()["enrolled"] is True


def test_student_cannot_self_enroll_or_delete(student_env, db):
    """Requirement: students must never enroll or delete their own face."""
    env = student_env
    resp = env.client.put(
        "/api/v1/face-enrollment", headers=env.headers,
        json={"embedding": base_embedding(), "embedding_dim": 128,
              "model_version": "mobilefacenet_tflite_128_v1"},
    )
    assert_error(resp, 403, "forbidden")
    assert db.scalar(select(FaceEnrollment.id)) is None

    # And cannot delete their own template either.
    resp = env.client.delete("/api/v1/face-enrollment", headers=env.headers)
    assert_error(resp, 403, "forbidden")


def test_student_cannot_enroll_another_student(student_env, db):
    """A student cannot reach the warden enrollment path at all."""
    env = student_env
    resp = env.client.put(
        f"/api/v1/warden/students/{env.student.student_id}/face-enrollment",
        headers=env.headers,
        json={"embedding": base_embedding(), "embedding_dim": 128,
              "model_version": "mobilefacenet_tflite_128_v1"},
    )
    assert_error(resp, 403, "forbidden")
    assert db.scalar(select(FaceEnrollment.id)) is None


def test_delete_writes_audit(student_env, db):
    env = student_env
    enroll(env.client, env.headers)
    resp = env.client.delete(
        f"/api/v1/warden/students/{env.student.student_id}/face-enrollment",
        headers=staff_headers(env.client))
    assert resp.status_code == 204

    entry = db.scalar(select(AuditLog).where(AuditLog.action == "face_enrollment.delete"))
    assert entry is not None
    assert entry.target_type == "student"
    assert entry.target_id == str(env.student.id)
    # The warden/admin session performed it, not the student.
    assert entry.actor_label == "_test_admin"


def test_put_wrong_dim_rejected(student_env):
    env = student_env
    resp = env.client.put(
        f"/api/v1/warden/students/{env.student.student_id}/face-enrollment",
        headers=staff_headers(env.client),
        json={"embedding": base_embedding(64), "embedding_dim": 128,
              "model_version": "mobilefacenet_tflite_128_v1"},
    )
    assert_error(resp, 400, "invalid_payload")


def test_put_nan_embedding_rejected(student_env):
    """NaN is non-standard JSON but parses in Python — must still be 400."""
    env = student_env
    raw = (
        '{"embedding": [NaN, 0.1, 0.2], "embedding_dim": 3, '
        '"model_version": "mobilefacenet_tflite_128_v1"}'
    )
    resp = env.client.put(
        f"/api/v1/warden/students/{env.student.student_id}/face-enrollment",
        headers={**staff_headers(env.client), "Content-Type": "application/json"},
        content=raw.encode("utf-8"),
    )
    assert_error(resp, 400, "invalid_payload")


def test_put_inconsistent_length_rejected(student_env):
    env = student_env
    resp = env.client.put(
        f"/api/v1/warden/students/{env.student.student_id}/face-enrollment",
        headers=staff_headers(env.client),
        json={"embedding": [0.1, 0.2, 0.3], "embedding_dim": 4,
              "model_version": "mobilefacenet_tflite_128_v1"},
    )
    assert_error(resp, 400, "invalid_payload")


def test_enrollment_requires_auth(client):
    resp = client.get("/api/v1/face-enrollment")
    assert_error(resp, 401, "token_invalid")
    resp = client.put("/api/v1/face-enrollment",
                      json={"embedding": [0.1], "embedding_dim": 1,
                            "model_version": "x"})
    assert_error(resp, 401, "token_invalid")
    resp = client.put("/api/v1/warden/students/CS-2022-084/face-enrollment",
                      json={"embedding": [0.1], "embedding_dim": 1,
                            "model_version": "x"})
    assert_error(resp, 401, "token_invalid")
