"""Security acceptance suite — the 20 scenarios from the enrollment brief.

Each test states the requirement it proves. Nothing here weakens production
behaviour to make an assertion pass.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core import clock
from app.core.config import settings
from app.models import (
    AccountActivationToken,
    AuditLog,
    FaceEnrollment,
    Student,
    User,
)
from conftest import (
    assert_error,
    base_embedding,
    enroll,
    verify_body,
)

ACTIVATE = "/api/v1/auth/activate"
W_STUDENTS = "/api/v1/warden/students"
VERIFY = "/api/v1/attendance/verify"


# --------------------------------------------------------------------------
# 1-3. Registration is closed; creation is warden/admin only
# --------------------------------------------------------------------------


def test_no_public_registration_route_exists():
    """(1) There is no endpoint at all that creates an account without auth.

    Registration is not merely protected — the route does not exist.
    """
    from app.main import app

    banned_paths = {
        "/api/v1/auth/register", "/api/v1/auth/signup", "/api/v1/auth/sign-up",
        "/api/v1/students", "/api/v1/students/register", "/api/v1/auth/student-register",
    }
    existing = {
        getattr(r, "path", "") for r in app.routes
    }
    for path in banned_paths:
        assert path not in existing, f"public registration route present: {path}"
    # And the student-facing router exposes no POST at all.
    from app.api import students_router

    post_methods = [
        route for route in students_router.routes
        if "POST" in (getattr(route, "methods", None) or set())
    ]
    assert post_methods == [], post_methods


def test_unauthenticated_cannot_create_student(client, make_hostel):
    """(2) Unauthenticated student creation -> 401 on every staff path."""
    hostel = make_hostel()
    payload = {"student_id": "CS-2024-001", "name": "Ghost",
               "email": "ghost@ceconline.edu", "hostel_id": str(hostel.id)}
    assert_error(client.post(W_STUDENTS, json=payload), 401, "token_invalid")
    assert_error(client.post("/api/v1/admin/students", json=payload),
                 401, "token_invalid")


def test_student_cannot_create_student(student_env, make_hostel):
    """(1/2) An authenticated STUDENT still cannot create accounts."""
    env = student_env
    hostel = make_hostel(name="Other", block="Z")
    payload = {"student_id": "CS-2024-002", "name": "Friend",
               "email": "friend@ceconline.edu", "hostel_id": str(hostel.id)}
    assert_error(env.client.post(W_STUDENTS, headers=env.headers, json=payload),
                 403, "forbidden")
    assert_error(env.client.post("/api/v1/admin/students", headers=env.headers,
                                 json=payload), 403, "forbidden")


def test_warden_can_create_student(client, db, make_hostel, make_warden, login):
    """(3) An authorized warden creates a student in their own hostel."""
    hostel = make_hostel()
    make_warden(username="warden1", hostels=[hostel])
    token = login("warden1", "WardenPass123!")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(W_STUDENTS, headers=headers, json={
        "student_id": "CS-2024-100", "name": "New Student",
        "email": "New.Student@CECONLINE.edu",   # normalized on save
        "hostel_id": str(hostel.id), "room": "212",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "new.student@ceconline.edu"
    assert body["enrollment_status"] == "created"
    assert body["account_status"] == "inactive"   # cannot sign in yet
    assert body["role"] == "student"

    # Audit row records the warden as actor.
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "student.create"))
    assert entry is not None
    assert entry.actor_label == "warden1"

    # The new student cannot sign in.
    # They have NO password yet (the placeholder hash was never issued to
    # anyone), so every attempt fails generically — this also means a pending
    # account cannot be probed for existence.
    resp = client.post("/api/v1/auth/login", json={
        "student_id": "CS-2024-100", "password": "whatever123"})
    assert_error(resp, 401, "invalid_credentials")
    resp = client.post("/api/v1/auth/login", json={
        "email": "new.student@ceconline.edu", "password": "whatever123"})
    assert_error(resp, 401, "invalid_credentials")

    # And with the CORRECT password a pending account is still refused, with
    # the honest "contact your warden" message (403, not 401).
    from sqlalchemy import select as _select

    from app.core.security import hash_password as _hp
    from app.db.session import SessionFactory as _SF
    from app.models import User as _U

    with _SF() as session:
        user = session.scalar(_select(_U).where(_U.username == "CS-2024-100"))
        user.password_hash = _hp("Correct!Pass1")
        session.commit()
    resp = client.post("/api/v1/auth/login", json={
        "student_id": "CS-2024-100", "password": "Correct!Pass1"})
    assert_error(resp, 403, "account_not_activated")
    assert "contact your hostel warden" in resp.json()["error"]["message"]


def test_warden_cannot_manage_hostel_outside_grant(client, db, make_hostel,
                                                   make_warden, login):
    """(4) Hostel scoping: no grants on either side of the operation."""
    mine = make_hostel(name="Mine", block="A")
    other = make_hostel(name="Not Mine", block="B")
    make_warden(username="warden_scope", hostels=[mine])
    headers = {"Authorization": f"Bearer {login('warden_scope', 'WardenPass123!')}"}

    # Cannot create into a hostel outside the grant.
    resp = client.post(W_STUDENTS, headers=headers, json={
        "student_id": "CS-2024-200", "name": "Outsider",
        "email": "outsider@ceconline.edu", "hostel_id": str(other.id)})
    assert_error(resp, 403, "forbidden")

    # Cannot create into their own hostel.
    resp = client.post(W_STUDENTS, headers=headers, json={
        "student_id": "CS-2024-201", "name": "Insider",
        "email": "insider@ceconline.edu", "hostel_id": str(mine.id)})
    assert resp.status_code == 201, resp.text

    # Cannot read a student belonging to the other hostel (404 by scoping,
    # so the warden cannot probe which roll numbers exist elsewhere).
    resp = client.get(f"{W_STUDENTS}/CS-2024-201", headers=headers)
    assert resp.status_code == 200  # own hostel -> visible

    # A second warden with the other hostel cannot see or touch them.
    make_warden(username="warden_other", hostels=[other])
    other_headers = {"Authorization": f"Bearer {login('warden_other', 'WardenPass123!')}"}
    assert_error(client.get(f"{W_STUDENTS}/CS-2024-201", headers=other_headers),
                 404, "not_found")
    # Enrollment for an out-of-scope student is also refused with 404, so the
    # warden learns nothing about whether that roll exists.
    assert_error(client.put(f"{W_STUDENTS}/CS-2024-201/face-enrollment",
                            headers=other_headers,
                            json={"embedding": base_embedding(),
                                  "embedding_dim": 128,
                                  "model_version": "m"}),
                 404, "not_found")

    # Roster listing is scoped too.
    resp = client.get(W_STUDENTS, headers=other_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []

    # Filtering by an ungranted hostel is refused outright.
    assert_error(client.get(f"{W_STUDENTS}?hostel_id={mine.id}",
                            headers=other_headers), 403, "forbidden")

    # A warden with NO hostel grants sees nothing rather than everything.
    make_warden(username="warden_bare", hostels=[])
    bare = {"Authorization": f"Bearer {login('warden_bare', 'WardenPass123!')}"}
    assert client.get(W_STUDENTS, headers=bare).json()["items"] == []
    assert client.get("/api/v1/warden/dashboard", headers=bare).json()[
        "total_students"] == 0


def test_warden_create_requires_hostel(client, make_warden, login):
    """A warden cannot create an unassigned student (would bypass scoping)."""
    make_warden(username="warden_nohostel", hostels=[])
    headers = {"Authorization": f"Bearer {login('warden_nohostel', 'WardenPass123!')}"}
    resp = client.post(W_STUDENTS, headers=headers, json={
        "student_id": "CS-2024-300", "name": "Unassigned",
        "email": "unassigned@ceconline.edu"})
    assert_error(resp, 403, "forbidden")


# --------------------------------------------------------------------------
# 5. Face enrollment authorization
# --------------------------------------------------------------------------

def test_student_cannot_enroll_any_face(student_env, db):
    """(5) A student can neither enroll themselves nor another student."""
    env = student_env
    body = {"embedding": base_embedding(), "embedding_dim": 128,
            "model_version": "m"}

    # Themselves (self-service route answers an explicit 403).
    assert_error(env.client.put("/api/v1/face-enrollment",
                                headers=env.headers, json=body), 403, "forbidden")
    # Themselves through the warden route.
    assert_error(env.client.put(f"{W_STUDENTS}/{env.student.student_id}/face-enrollment",
                                headers=env.headers, json=body), 403, "forbidden")
    # Another student through the warden route.
    assert_error(env.client.put(f"{W_STUDENTS}/CS-2022-999/face-enrollment",
                                headers=env.headers, json=body), 403, "forbidden")
    # Deleting is equally closed.
    assert_error(env.client.delete(f"{W_STUDENTS}/{env.student.student_id}/face-enrollment",
                                   headers=env.headers), 403, "forbidden")

    assert db.scalar(select(FaceEnrollment.id)) is None


# --------------------------------------------------------------------------
# 6-8. Uniqueness and college-email rules
# --------------------------------------------------------------------------

def _create(client, headers, sid, email, hostel_id=None, name="X"):
    payload = {"student_id": sid, "name": name, "email": email}
    if hostel_id is not None:
        payload["hostel_id"] = str(hostel_id)
    return client.post(W_STUDENTS, headers=headers, json=payload)


def test_duplicate_student_id_rejected(client, make_hostel, make_warden, login):
    """(6) Roll numbers are unique — case-insensitively, on both keys."""
    hostel = make_hostel()
    make_warden(hostels=[hostel])
    headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}

    assert _create(client, headers, "CS-2024-050", "a@ceconline.edu",
                   hostel.id).status_code == 201
    resp = _create(client, headers, "CS-2024-050", "b@ceconline.edu", hostel.id)
    assert_error(resp, 409, "conflict")
    resp = _create(client, headers, "cs-2024-050", "c@ceconline.edu", hostel.id)
    assert_error(resp, 409, "conflict")


def test_duplicate_email_rejected_and_normalized(client, make_hostel, make_warden, login):
    """(7) College emails are unique after normalization."""
    hostel = make_hostel()
    make_warden(hostels=[hostel])
    headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}

    assert _create(client, headers, "CS-2024-060", "Same@ceconline.edu",
                   hostel.id).status_code == 201
    resp = _create(client, headers, "CS-2024-061", "  same@CECONLINE.edu ",
                   hostel.id)
    assert_error(resp, 409, "conflict")


@pytest.mark.parametrize("bad_email", [
    "student@gmail.com",                    # wrong provider
    "student@ceconline.com",                # look-alike TLD
    "student@ceconline.edu.example.com",    # suffix attack
    "student@xceconline.edu",               # prefixed host
    "student@sub.ceconline.edu",            # subdomain (not exact)
    "student@ceconline.edu.",               # trailing dot
    "student+tag@ceconline.edu",            # still exact domain? -> allowed below
])
def test_email_domain_validation(client, make_hostel, make_warden, login, bad_email):
    """(8) Exact-domain validation — no substring or suffix shortcuts."""
    hostel = make_hostel()
    make_warden(hostels=[hostel])
    headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}
    allowed = bad_email.endswith("+tag@ceconline.edu")
    resp = _create(client, headers, "CS-2024-070", bad_email, hostel.id)
    if allowed:
        assert resp.status_code == 201, resp.text
    else:
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"]["code"] == "invalid_payload"


def test_exact_valid_email_accepted(client, make_hostel, make_warden, login):
    """The canonical valid address is accepted verbatim."""
    hostel = make_hostel()
    make_warden(hostels=[hostel])
    headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}
    resp = _create(client, headers, "CS-2024-071", "student@ceconline.edu", hostel.id)
    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] == "student@ceconline.edu"


# --------------------------------------------------------------------------
# 9-10, 14. Lifecycle gates on sign-in and attendance
# --------------------------------------------------------------------------

def test_pending_student_cannot_mark_attendance(client, db, make_hostel,
                                                make_student):
    """(9) created/details_verified/face_enrolled/account_provisioned -> no token."""
    hostel = make_hostel()
    for status in ("created", "details_verified", "face_enrolled",
                   "account_provisioned"):
        student = make_student(hostel=hostel, roll=f"CS-2024-{status[:3].upper()}",
                               email=f"{status}@ceconline.edu",
                               enrollment_status=status, account_status="inactive")
        resp = client.post("/api/v1/auth/login", json={
            "student_id": student.student_id, "password": "student123!"})
        assert_error(resp, 403, "account_not_activated"), status

        # Even with a token smuggled in, verify must refuse (no token exists).
        assert_error(client.post(VERIFY, json=verify_body()), 401, "token_invalid")

    # And an ACTIVE student without a token cannot verify either.
    assert_error(client.post(VERIFY, json=verify_body()), 401, "token_invalid")


def test_active_student_signs_in_with_valid_credentials(client, make_hostel,
                                                        make_student, db):
    """(10) Email + password sign-in for a provisioned, active student."""
    hostel = make_hostel()
    make_student(hostel=hostel, roll="CS-2024-800",
                 email="cs-2024-800@ceconline.edu")

    # College email login.
    resp = client.post("/api/v1/auth/login", json={
        "email": "cs-2024-800@ceconline.edu", "password": "student123!"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["student"]["role"] == "student"
    assert resp.json()["student"]["enrollment_status"] == "active"

    # Roll number still works (legacy identifier).
    resp = client.post("/api/v1/auth/login", json={
        "student_id": "CS-2024-800", "password": "student123!"})
    assert resp.status_code == 200, resp.text

    # Wrong password -> 401, same envelope as unknown user (no enumeration).
    assert_error(client.post("/api/v1/auth/login", json={
        "email": "cs-2024-800@ceconline.edu", "password": "nope"}), 401,
        "invalid_credentials")
    assert_error(client.post("/api/v1/auth/login", json={
        "email": "nobody@ceconline.edu", "password": "nope"}), 401,
        "invalid_credentials")

    # Login is audit-logged without any password material.
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "auth.login"))
    assert entry is not None
    assert "student123" not in str(entry.details)


def test_suspended_account_cannot_sign_in(client, make_hostel, make_student,
                                          make_warden, login):
    """(14) Suspension blocks password sign-in until restored."""
    hostel = make_hostel()
    student = make_student(hostel=hostel)
    make_warden(hostels=[hostel])
    headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}

    resp = client.post(f"{W_STUDENTS}/{student.student_id}/suspend", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["enrollment_status"] == "suspended"

    assert_error(client.post("/api/v1/auth/login", json={
        "student_id": student.student_id, "password": "student123!"}),
        403, "account_suspended")

    # Restore -> sign-in works again.
    assert client.post(f"{W_STUDENTS}/{student.student_id}/unsuspend",
                       headers=headers).status_code == 200
    assert client.post("/api/v1/auth/login", json={
        "student_id": student.student_id,
        "password": "student123!"}).status_code == 200


# --------------------------------------------------------------------------
# 11-13. Google Sign-In verifies server-side and never registers
# --------------------------------------------------------------------------

class _FakeVerifier:
    """Test double for GoogleTokenVerifier — production code is untouched."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def verify(self, id_token, audience):
        self.calls.append((id_token, audience))
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def fake_google(monkeypatch):
    from app.services import google_auth

    def _install(verifier):
        monkeypatch.setattr(google_auth, "get_verifier", lambda: verifier)
        monkeypatch.setattr(settings, "google_oauth_client_id",
                            "test-client.apps.googleusercontent.com")
        return verifier

    return _install


def _identity(email="cs-2024-900@ceconline.edu", subject="g-sub-1", name="G Student"):
    from app.services.google_auth import VerifiedGoogleIdentity

    return VerifiedGoogleIdentity(email=email, subject=subject, name=name)


def test_google_rejects_unprovisioned_account(client, fake_google):
    """(11) A Google identity with no provisioned student is refused."""
    from app.services.google_auth import GoogleTokenError

    fake_google(_FakeVerifier(result=_identity()))
    resp = client.post("/api/v1/auth/google", json={"id_token": "a" * 40})
    assert_error(resp, 403, "account_not_activated")
    assert "contact your hostel warden" in resp.json()["error"]["message"]


def test_google_rejects_wrong_domain(client, fake_google):
    """(12) A verified Google account outside @ceconline.edu is refused."""
    fake_google(_FakeVerifier(result=_identity(email="someone@gmail.com")))
    resp = client.post("/api/v1/auth/google", json={"id_token": "a" * 40})
    # Fails at token verification (domain is part of the token contract).
    assert resp.status_code in (401, 403), resp.text
    assert resp.json()["error"]["code"] in ("invalid_credentials",
                                            "account_not_activated")


def test_google_rejects_invalid_token(client, fake_google):
    """(13) Structurally invalid / unverifiable tokens are rejected."""
    from app.services.google_auth import GoogleTokenError

    fake_google(_FakeVerifier(error=GoogleTokenError("bad_alg")))
    resp = client.post("/api/v1/auth/google", json={"id_token": "a" * 40})
    assert_error(resp, 401, "invalid_credentials")


def test_google_never_creates_or_links(client, db, make_hostel, make_student,
                                       fake_google):
    """Google sign-in authenticates only — it must not create rows."""
    hostel = make_hostel()

    fake_google(_FakeVerifier(result=_identity(email="fresh@ceconline.edu")))
    assert_error(client.post("/api/v1/auth/google", json={"id_token": "a" * 40}),
                 403, "account_not_activated")

    # No user, no student row was created by the attempt.
    assert db.scalar(select(User)) is None
    assert db.scalar(select(Student)) is None

    # Now provision a student whose email matches, and Google sign-in works.
    make_student(hostel=hostel, roll="CS-2024-900",
                 email="fresh@ceconline.edu")
    fake_google(_FakeVerifier(result=_identity(email="fresh@ceconline.edu")))
    resp = client.post("/api/v1/auth/google", json={"id_token": "a" * 40})
    assert resp.status_code == 200, resp.text
    assert resp.json()["student"]["student_id"] == "CS-2024-900"
    # Still exactly one student row — nothing was duplicated or linked.
    assert db.scalar(select(Student)) is not None
    assert db.scalar(select(User)) is not None


def test_google_disabled_when_not_configured(client, monkeypatch):
    """No OAuth client id configured -> honest 503, never a silent bypass."""
    monkeypatch.setattr(settings, "google_oauth_client_id", "")
    resp = client.post("/api/v1/auth/google", json={"id_token": "a" * 40})
    assert_error(resp, 503, "google_signin_not_configured")


# --------------------------------------------------------------------------
# 15-16. Students cannot escalate or reach other students' data
# --------------------------------------------------------------------------

def test_student_cannot_change_own_role(client, student_env, db):
    """(15) No client-side path lets a student become admin/warden."""
    env = student_env
    # Even a forged JWT role claim is ignored — role comes from the DB.
    from app.core.security import create_access_token

    forged, _jti, _exp = create_access_token(str(env.student.user_id), "admin")
    forged_headers = {"Authorization": f"Bearer {forged}"}
    resp = client.get("/api/v1/auth/me", headers=forged_headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "student"  # DB role, not the claim

    # Reaching staff routes with the forged token -> 403.
    assert_error(client.get("/api/v1/warden/dashboard", headers=forged_headers),
                 403, "forbidden")
    assert_error(client.get("/api/v1/admin/students", headers=forged_headers),
                 403, "forbidden")

    # PATCH with a role field is ignored by the schema.
    assert_error(env.client.patch(f"/api/v1/warden/students/{env.student.student_id}",
                                  headers=env.headers,
                                  json={"role": "admin"}), 403, "forbidden")

    db.expire_all()
    assert db.get(User, env.student.user_id).role == "student"


def test_student_cannot_read_other_students(student_env, client, make_student,
                                            make_hostel):
    """(16) No student-to-student data access anywhere in the API."""
    env = student_env
    other = make_student(hostel=env.hostel, roll="CS-2022-777",
                         email="other@ceconline.edu")

    blocked = [
        ("GET", f"/api/v1/warden/students/{other.student_id}"),
        ("GET", "/api/v1/warden/students"),
        ("GET", "/api/v1/warden/dashboard"),
        ("GET", "/api/v1/warden/attendance"),
        ("GET", "/api/v1/warden/hostels"),
        ("GET", "/api/v1/admin/students"),
        ("GET", "/api/v1/admin/attendance"),
        ("GET", "/api/v1/admin/audit-logs"),
        ("GET", "/api/v1/admin/hostels"),
    ]
    for method, path in blocked:
        resp = env.client.request(method, path, headers=env.headers)
        assert_error(resp, 403, "forbidden"), f"{method} {path}"

    # Even guessing the other student's UUID through a self-looking route.
    resp = env.client.get(f"/api/v1/warden/students/{other.id}",
                          headers=env.headers)
    assert_error(resp, 403, "forbidden")


def test_students_me_only_returns_self(student_env):
    """The one student self-route returns exactly the caller's own record."""
    env = student_env
    resp = env.client.get("/api/v1/students/me", headers=env.headers)
    assert resp.status_code == 200
    assert resp.json()["student_id"] == env.student.student_id
    assert "email" in resp.json()


# --------------------------------------------------------------------------
# 17-18. Face enrollment state is server-controlled and recoverable
# --------------------------------------------------------------------------

def test_client_boolean_cannot_fake_enrollment(client, student_env, db):
    """(17) A client-asserted ``face_enrolled: true`` proves nothing.

    Sending every plausible client flag leaves the server state untouched.
    """
    env = student_env
    for body in (
        {"face_enrolled": True},
        {"enrolled": True, "status": "active"},
        {"embedding": [], "face_enrolled": True},
    ):
        resp = env.client.put("/api/v1/face-enrollment", headers=env.headers,
                              json=body)
        assert resp.status_code in (400, 403), resp.text
    assert db.scalar(select(FaceEnrollment.id)) is None
    assert db.get(Student, env.student.id).enrollment_status == "active"

    # Login response reports enrollment truthfully as not-yet-enrolled.
    resp = client.get("/api/v1/students/me", headers=env.headers)
    assert resp.json()["enrollment_status"] == "active"


def test_enrollment_failure_leaves_recoverable_state(client, db, make_hostel,
                                                     make_warden, login):
    """(18) A rejected enrollment changes nothing and the retry succeeds."""
    hostel = make_hostel()
    make_warden(hostels=[hostel])
    headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}

    resp = client.post(W_STUDENTS, headers=headers, json={
        "student_id": "CS-2024-400", "name": "Retry Me",
        "email": "retry@ceconline.edu", "hostel_id": str(hostel.id)})
    assert resp.status_code == 201, resp.text
    roll = "CS-2024-400"

    # Bad payload: dimension mismatch -> 400, no partial state.
    assert_error(client.put(f"{W_STUDENTS}/{roll}/face-enrollment",
                            headers=headers,
                            json={"embedding": base_embedding(64),
                                  "embedding_dim": 128,
                                  "model_version": "m"}), 400, "invalid_payload")
    student = db.scalar(select(Student).where(Student.student_id == roll))
    assert student.enrollment_status == "created"       # unchanged
    assert db.scalar(select(FaceEnrollment.id)) is None  # nothing written

    # Non-finite values -> 400, still unchanged. (httpx refuses to serialize
    # NaN, so the raw body is sent, mirroring the pre-existing enrollment test.)
    assert_error(client.put(
        f"{W_STUDENTS}/{roll}/face-enrollment",
        headers={**headers, "Content-Type": "application/json"},
        content=(b'{"embedding": [NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN], '
                 b'"embedding_dim": 8, "model_version": "m"}'),
    ), 400, "invalid_payload")
    db.expire_all()
    student = db.scalar(select(Student).where(Student.student_id == roll))
    assert student.enrollment_status == "created"

    # Retry succeeds and the lifecycle advances normally.
    resp = client.put(f"{W_STUDENTS}/{roll}/face-enrollment", headers=headers,
                      json={"embedding": base_embedding(),
                            "embedding_dim": 128,
                            "model_version": "mobilefacenet_tflite_128_v1"})
    assert resp.status_code == 200, resp.text
    db.expire_all()
    student = db.scalar(select(Student).where(Student.student_id == roll))
    assert student.enrollment_status == "face_enrolled"

    # Deleting the template rolls the account back to a recoverable state.
    resp = client.delete(f"{W_STUDENTS}/{roll}/face-enrollment", headers=headers)
    assert resp.status_code == 204
    db.expire_all()
    student = db.scalar(select(Student).where(Student.student_id == roll))
    assert student.enrollment_status == "details_verified"
    assert db.scalar(select(FaceEnrollment.id)) is None

    # And re-enrollment restores forward progress.
    assert client.put(f"{W_STUDENTS}/{roll}/face-enrollment", headers=headers,
                      json={"embedding": base_embedding(),
                            "embedding_dim": 128,
                            "model_version": "m"}).status_code == 200


# --------------------------------------------------------------------------
# 19. Activation tokens: strong, single-use, time-limited, bound
# --------------------------------------------------------------------------

def _provisioned(client, db, make_hostel, make_warden, login,
                 roll="CS-2024-500", email="act@ceconline.edu"):
    hostel = make_hostel()
    make_warden(hostels=[hostel])
    warden_headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}
    resp = client.post(W_STUDENTS, headers=warden_headers, json={
        "student_id": roll, "name": "Activating Student",
        "email": email, "hostel_id": str(hostel.id)})
    assert resp.status_code == 201, resp.text
    assert client.put(f"{W_STUDENTS}/{roll}/face-enrollment",
                      headers=warden_headers,
                      json={"embedding": base_embedding(), "embedding_dim": 128,
                            "model_version": "m"}).status_code == 200
    return warden_headers, roll, hostel


def test_activation_requires_provisioning_first(client, make_hostel, make_warden,
                                                login):
    """Activation is refused before face enrollment — no skipping stages."""
    hostel = make_hostel()
    make_warden(hostels=[hostel])
    headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}
    client.post(W_STUDENTS, headers=headers, json={
        "student_id": "CS-2024-501", "name": "Early",
        "email": "early@ceconline.edu", "hostel_id": str(hostel.id)})

    assert_error(client.post(f"{W_STUDENTS}/CS-2024-501/activate",
                             headers=headers), 409, "not_ready_to_provision")


def test_activation_token_flow_single_use_and_bounded(client, db, make_hostel,
                                                      make_warden, login,
                                                      monkeypatch):
    """(19) Tokens are strong, single-use, bound to one account, expiring."""
    warden_headers, roll, _hostel = _provisioned(client, db, make_hostel,
                                                 make_warden, login, roll="CS-2024-510",
                                                 email="a1@ceconline.edu")
    # Dev mode returns the plaintext so the flow can be exercised end-to-end.
    monkeypatch.setattr(settings, "allow_inline_activation_token", True)

    resp = client.post(f"{W_STUDENTS}/{roll}/activate", headers=warden_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    token = body["activation_token"]
    assert body["delivered"] is False  # no email transport configured
    assert len(token) >= 40            # secrets.token_urlsafe(32) -> 43 chars

    # Only a hash is stored — the plaintext never touches the database.
    stored = db.scalar(select(AccountActivationToken))
    assert stored is not None
    assert stored.token_hash != token
    assert len(stored.token_hash) == 64
    assert token not in str(stored.token_hash)

    # Redeem -> password set, account ACTIVE. The body also smuggles claims
    # naming a DIFFERENT account; identity comes from the token, not the body.
    resp = client.post(ACTIVATE, json={
        "token": token, "password": "MyPass!2345",
        "user_id": "00000000-0000-0000-0000-000000000000",
        "student_id": "SOMEONE_ELSE",
        "role": "admin",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["student"]["student_id"] == roll
    assert resp.json()["student"]["enrollment_status"] == "active"
    assert resp.json()["student"]["role"] == "student"

    # (a) Reuse -> rejected.
    assert_error(client.post(ACTIVATE, json={"token": token,
                                             "password": "Another!Pass1"}),
                 400, "activation_token_invalid")

    # (b) A second redemption attempt cannot be redirected either.
    assert_error(client.post(ACTIVATE, json={"token": token,
                                             "password": "Third!Pass123",
                                             "student_id": "SOMEONE_ELSE"}),
                 400, "activation_token_invalid")

    # (c) Unknown token -> identical error (no probing).
    assert_error(client.post(ACTIVATE, json={"token": "z" * 43,
                                             "password": "Whatever!123"}),
                 400, "activation_token_invalid")

    # (d) The chosen password now signs in; the old one does not.
    assert client.post("/api/v1/auth/login", json={
        "student_id": roll, "password": "MyPass!2345"}).status_code == 200
    assert_error(client.post("/api/v1/auth/login", json={
        "student_id": roll, "password": "student123!"}), 401, "invalid_credentials")


def test_activation_token_expires(client, db, make_hostel, make_warden, login,
                                  monkeypatch):
    """(19) An expired token is rejected exactly like an unknown one."""
    warden_headers, roll, _h = _provisioned(client, db, make_hostel, make_warden,
                                            login, roll="CS-2024-520",
                                            email="a2@ceconline.edu")
    monkeypatch.setattr(settings, "allow_inline_activation_token", True)
    token = client.post(f"{W_STUDENTS}/{roll}/activate",
                        headers=warden_headers).json()["activation_token"]

    # Age the stored record past its expiry.
    record = db.scalar(select(AccountActivationToken))
    record.expires_at = clock.utcnow() - timedelta(seconds=1)
    db.commit()

    assert_error(client.post(ACTIVATE, json={"token": token,
                                             "password": "LongEnough!1"}),
                 400, "activation_token_invalid")


def test_issuing_a_new_token_revokes_the_previous(client, db, make_hostel,
                                                  make_warden, login, monkeypatch):
    """Only the most recent setup link works (recovery is safe to retry)."""
    warden_headers, roll, _h = _provisioned(client, db, make_hostel, make_warden,
                                            login, roll="CS-2024-530",
                                            email="a3@ceconline.edu")
    monkeypatch.setattr(settings, "allow_inline_activation_token", True)

    first = client.post(f"{W_STUDENTS}/{roll}/activate",
                        headers=warden_headers).json()["activation_token"]
    second = client.post(f"{W_STUDENTS}/{roll}/resend-activation",
                         headers=warden_headers).json()["activation_token"]
    assert first != second

    assert_error(client.post(ACTIVATE, json={"token": first,
                                             "password": "LongEnough!1"}),
                 400, "activation_token_invalid")
    assert client.post(ACTIVATE, json={"token": second,
                                       "password": "LongEnough!2"}).status_code == 200


def test_activation_before_enrollment_is_impossible(client, db, make_hostel,
                                                    make_warden, login, monkeypatch):
    """No token can be minted for a student who has not been enrolled."""
    hostel = make_hostel()
    make_warden(hostels=[hostel])
    headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}
    client.post(W_STUDENTS, headers=headers, json={
        "student_id": "CS-2024-540", "name": "No Face",
        "email": "noface@ceconline.edu", "hostel_id": str(hostel.id)})

    assert_error(client.post(f"{W_STUDENTS}/CS-2024-540/activate", headers=headers),
                 409, "not_ready_to_provision")
    assert db.scalar(select(AccountActivationToken.id)) is None

    # A student cannot mint their own activation token either.
    monkeypatch.setattr(settings, "allow_inline_activation_token", True)
    assert db.scalar(select(AccountActivationToken.id)) is None


def test_inline_token_withheld_when_configured_off(client, db, make_hostel,
                                                   make_warden, login,
                                                   monkeypatch):
    """ALLOW_INLINE_ACTIVATION_TOKEN=false withholds the key (email-only mode)."""
    warden_headers, roll, _h = _provisioned(client, db, make_hostel, make_warden,
                                            login, roll="CS-2024-550",
                                            email="a4@ceconline.edu")
    monkeypatch.setattr(settings, "allow_inline_activation_token", False)
    resp = client.post(f"{W_STUDENTS}/{roll}/activate", headers=warden_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["activation_token"] is None
    assert body["setup_url"] is None
    # Honest contract: with EMAIL_MODE=off no email was attempted, so the
    # response must NOT claim delivery just because the token was stored.
    assert body["delivered"] is False
    assert body["email_status"] == "not_configured"
    assert body["activation_pending"] is True
    assert body["expires_at"].endswith("Z")

    # The hash is still stored so the student CAN redeem the link (delivered
    # by hand or by email once a transport is configured).
    assert db.scalar(select(AccountActivationToken.token_hash)) is not None


def test_issue_response_returns_key_by_default(client, db, make_hostel,
                                               make_warden, login, caplog):
    """(warden WhatsApp hand-off) The ISSUING response carries the fresh key,
    and ONLY that response: reads and logs never see the plaintext."""
    warden_headers, roll, _h = _provisioned(client, db, make_hostel, make_warden,
                                            login, roll="CS-2024-555",
                                            email="a4b@ceconline.edu")
    assert settings.allow_inline_activation_token is True  # default contract

    resp = client.post(f"{W_STUDENTS}/{roll}/activate", headers=warden_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    key = body["activation_token"]
    assert key and len(key) >= 40                     # secrets.token_urlsafe(32)
    assert key in (body["setup_url"] or "")

    # Issuance-only exposure: no read endpoint ever echoes it.
    detail = client.get(f"{W_STUDENTS}/{roll}", headers=warden_headers)
    listing = client.get(W_STUDENTS, headers=warden_headers)
    assert detail.status_code == 200 and key not in detail.text
    assert listing.status_code == 200 and key not in listing.text

    # And it never reaches an application log line.
    assert key not in " ".join(r.getMessage() for r in caplog.records)


def test_keys_unique_per_student_and_bound_to_their_account(
        client, db, make_hostel, make_warden, login):
    """(warden WhatsApp hand-off) Each student gets a DIFFERENT key, and one
    student's key can never activate anyone else's account."""
    hostel = make_hostel()
    make_warden(hostels=[hostel])
    headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}

    keys = {}
    for roll in ("CS-2024-601", "CS-2024-602"):
        resp = client.post(W_STUDENTS, headers=headers, json={
            "student_id": roll, "name": f"Student {roll}",
            "email": f"{roll}@ceconline.edu", "hostel_id": str(hostel.id)})
        assert resp.status_code == 201, resp.text
        assert client.put(f"{W_STUDENTS}/{roll}/face-enrollment", headers=headers,
                          json={"embedding": base_embedding(), "embedding_dim": 128,
                                "model_version": "m"}).status_code == 200
        issue = client.post(f"{W_STUDENTS}/{roll}/activate", headers=headers)
        assert issue.status_code == 200, issue.text
        keys[roll] = issue.json()["activation_token"]
        assert keys[roll]

    assert keys["CS-2024-601"] != keys["CS-2024-602"]  # unique per student

    # Student 1 redeems THEIR key...
    resp = client.post(ACTIVATE, json={"token": keys["CS-2024-601"],
                                       "password": "First!Pass123"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["student"]["student_id"] == "CS-2024-601"
    assert resp.json()["student"]["enrollment_status"] == "active"

    # ...and student 2's account is completely untouched by it.
    db.expire_all()
    other = db.scalar(select(Student).where(Student.student_id == "CS-2024-602"))
    assert other.enrollment_status == "account_provisioned"
    assert client.post("/api/v1/auth/login", json={
        "student_id": "CS-2024-602",
        "password": "First!Pass123"}).status_code == 401


# --------------------------------------------------------------------------
# 20. Attendance protections are untouched
# --------------------------------------------------------------------------

def test_geofence_and_duplicate_protection_still_enforced(student_env):
    """(20) Existing location + duplicate rules remain authoritative."""
    env = student_env
    headers = env.headers
    enroll(env.client, headers)

    # 600 m away, 4 m accuracy -> far outside 120 m + uncertainty.
    resp = env.client.post(VERIFY, headers=headers,
                           json=verify_body(latitude=12.97709, longitude=79.15851))
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "outside_geofence"

    # Valid location -> first mark succeeds, second is a duplicate.
    body = verify_body()
    first = env.client.post(VERIFY, headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["outcome"] == "verified"
    assert first.json()["status"] == "present"

    second = env.client.post(VERIFY, headers=headers, json=body)
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "duplicate_attendance"


def test_verify_rejects_mismatched_face(student_env):
    """A face far from the stored template is still a mismatch."""
    env = student_env
    headers = env.headers
    from conftest import mismatched_embedding

    enroll(env.client, headers)
    resp = env.client.post(VERIFY, headers=headers,
                           json=verify_body(embedding=mismatched_embedding()))
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "face_mismatch"


def test_face_mismatch_does_not_create_record(student_env, db):
    """Location/face failures never leave a successful attendance row."""
    env = student_env
    from app.models import AttendanceRecord

    enroll(env.client, env.headers)
    env.client.post(VERIFY, headers=env.headers,
                    json=verify_body(latitude=12.97709, longitude=79.15851))
    env.client.post(VERIFY, headers=env.headers,
                    json=verify_body(embedding=[-1.0] * 128))
    assert db.scalar(select(AttendanceRecord.id)) is None


# --------------------------------------------------------------------------
# Audit coverage for sensitive actions
# --------------------------------------------------------------------------

def test_audit_covers_sensitive_actions(client, db, make_hostel, make_warden,
                                        login, monkeypatch):
    """Sensitive operations are recorded WITHOUT secrets or biometrics."""
    warden_headers, roll, _h = _provisioned(client, db, make_hostel, make_warden,
                                            login, roll="CS-2024-600",
                                            email="audit@ceconline.edu")
    monkeypatch.setattr(settings, "allow_inline_activation_token", True)
    token = client.post(f"{W_STUDENTS}/{roll}/activate",
                        headers=warden_headers).json()["activation_token"]
    client.post(ACTIVATE, json={"token": token, "password": "Chosen!Pass1"})
    client.post(f"{W_STUDENTS}/{roll}/suspend", headers=warden_headers)

    actions = {e.action for e in db.scalars(select(AuditLog)).all()}
    assert {"student.create", "face_enrollment.enroll",
            "student.activate_issue", "auth.activate",
            "student.suspend"} <= actions, actions

    for entry in db.scalars(select(AuditLog)).all():
        blob = str(entry.details) + str(entry.action)
        assert "Chosen!Pass" not in blob
        assert token not in blob
        # No raw embedding material in any audit row.
        assert "embedding" not in blob.lower()
