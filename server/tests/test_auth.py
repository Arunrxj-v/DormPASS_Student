"""Auth: login, wrong password, unknown student, logout revocation, /auth/me."""

from __future__ import annotations

from conftest import assert_error


def test_login_success(client, make_hostel, make_student):
    hostel = make_hostel()
    make_student(hostel=hostel, roll="CS-2022-084", name="Rohan Sharma")

    resp = client.post("/api/v1/auth/login", json={
        "student_id": "CS-2022-084", "password": "student123!",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 1800  # 30 minutes
    assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20
    student = data["student"]
    assert student["student_id"] == "CS-2022-084"
    assert student["name"] == "Rohan Sharma"
    assert student["role"] == "student"
    assert student["account_status"] == "active"
    assert student["hostel"]["name"] == "Ganga Boys Hostel"
    assert student["hostel"]["room"] == "314"


def test_login_wrong_password(client, make_hostel, make_student):
    make_student(hostel=make_hostel())
    resp = client.post("/api/v1/auth/login", json={
        "student_id": "CS-2022-084", "password": "wrong-password",
    })
    assert_error(resp, 401, "invalid_credentials")


def test_login_unknown_student(client):
    resp = client.post("/api/v1/auth/login", json={
        "student_id": "CS-9999-999", "password": "whatever123",
    })
    # Same envelope as a wrong password — no user enumeration.
    assert_error(resp, 401, "invalid_credentials")


def test_login_rate_limited_per_ip_and_student(client, make_hostel, make_student):
    make_student(hostel=make_hostel())
    body = {"student_id": "CS-2022-084", "password": "wrong-password"}
    codes = [client.post("/api/v1/auth/login", json=body).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5
    resp = client.post("/api/v1/auth/login", json=body)
    assert_error(resp, 429, "rate_limited")


def test_logout_revokes_token(student_env):
    env = student_env
    # Token works, then logout, then it is rejected as revoked.
    assert env.client.get("/api/v1/auth/me", headers=env.headers).status_code == 200

    out = env.client.post("/api/v1/auth/logout", headers=env.headers)
    assert out.status_code == 204

    resp = env.client.get("/api/v1/auth/me", headers=env.headers)
    assert_error(resp, 401, "token_revoked")

    # Logout again — the token is already invalid.
    resp2 = env.client.post("/api/v1/auth/logout", headers=env.headers)
    assert_error(resp2, 401, "token_revoked")


def test_auth_me_without_token(client):
    resp = client.get("/api/v1/auth/me")
    assert_error(resp, 401, "token_invalid")


def test_auth_me_with_garbage_token(client):
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert_error(resp, 401, "token_invalid")


def test_auth_me_with_token(student_env):
    env = student_env
    resp = env.client.get("/api/v1/auth/me", headers=env.headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["student_id"] == env.student.student_id
    assert body["role"] == "student"


def test_students_me_matches_auth_me(student_env):
    env = student_env
    me = env.client.get("/api/v1/auth/me", headers=env.headers).json()
    mine = env.client.get("/api/v1/students/me", headers=env.headers)
    assert mine.status_code == 200
    assert mine.json() == me


def test_protected_routes_require_token(client):
    for path in ("/api/v1/students/me", "/api/v1/attendance/status",
                 "/api/v1/attendance/history", "/api/v1/hostels/me/geofence"):
        assert_error(client.get(path), 401, "token_invalid")
    assert_error(client.post("/api/v1/attendance/verify", json={}), 401, "token_invalid")
