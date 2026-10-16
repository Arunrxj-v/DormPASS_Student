"""Admin Console → Warden App provisioning tier.

Tier 1 of the account hierarchy::

    admin console  --creates/assigns-->  warden  --enrolls-->  student

Every assertion here is what FastAPI returns for a given session role. Nothing
depends on a button being hidden in a client: a warden or student token hits
the same routes and is refused by ``require_admin`` at the router level.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from conftest import assert_error

from app.models import AuditLog, User, WardenHostel

# Not a reusable "default" password — a per-suite literal for a fixture
# account that only exists inside the truncated test database.
WARDEN_PW = "InitialWarden-Pass1!"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def admin_env(client, make_admin, login):
    """Authenticated administrator session (created through the normal API)."""
    make_admin(username="admin")
    token = login("admin", "AdminPass123!")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def hostel(make_hostel):
    return make_hostel()


@pytest.fixture
def second_hostel(make_hostel):
    return make_hostel(name="Yamuna Girls Hostel", block="A", anchor_label="Yamuna Block A")


def warden_login(client, username: str, password: str = WARDEN_PW) -> dict:
    resp = client.post("/api/v1/auth/login",
                       json={"student_id": username, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def create_warden(client, headers, *, username: str = "warden.ganga",
                  hostel_ids: list | None = None, password: str = WARDEN_PW):
    return client.post(
        "/api/v1/admin/wardens",
        headers=headers,
        json={
            "username": username,
            "password": password,
            "hostel_ids": [str(h) for h in (hostel_ids or [])],
        },
    )


def audit_actions(db, *actions: str) -> list[AuditLog]:
    db.expire_all()
    rows = db.scalars(
        select(AuditLog).where(AuditLog.action.in_(actions))
    ).all()
    return list(rows)


# --------------------------------------------------------------------------
# 1. Role isolation — only ADMIN reaches the warden-management surface
# --------------------------------------------------------------------------

def test_warden_cannot_read_admin_routes(client, make_warden, login):
    make_warden()  # granted a hostel, so this is a fully working warden
    headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}
    for path in ("/api/v1/admin/wardens", "/api/v1/admin/students",
                 "/api/v1/admin/hostels", "/api/v1/admin/audit-logs"):
        assert_error(client.get(path, headers=headers), 403, "forbidden")


def test_warden_cannot_manage_warden_accounts(client, make_warden, login, hostel):
    make_warden(hostels=[])  # grants are irrelevant to a 403; avoids a hostel clash
    headers = {"Authorization": f"Bearer {login('warden', 'WardenPass123!')}"}

    # Create another warden.
    assert_error(
        create_warden(client, headers, username="warden.two",
                      hostel_ids=[hostel.id]),
        403, "forbidden",
    )
    # Grant / revoke / deactivate themselves.
    assert_error(
        client.patch("/api/v1/admin/wardens/warden", headers=headers,
                     json={"hostel_ids": [], "account_status": "inactive"}),
        403, "forbidden",
    )
    # Try to hand themselves ADMIN through the same call.
    assert_error(
        client.patch("/api/v1/admin/wardens/warden", headers=headers,
                     json={"role": "admin"}),
        403, "forbidden",
    )
    # Delete a staff account.
    assert_error(client.delete("/api/v1/admin/wardens/warden", headers=headers),
                 403, "forbidden")


def test_student_cannot_manage_warden_accounts(student_env):
    env = student_env
    assert_error(
        create_warden(client=env.client, headers=env.headers,
                      username="sneaky.warden"),
        403, "forbidden",
    )
    assert_error(
        env.client.patch("/api/v1/admin/wardens/whatever", headers=env.headers,
                         json={"role": "admin"}),
        403, "forbidden",
    )
    assert_error(
        env.client.delete("/api/v1/admin/wardens/whatever", headers=env.headers),
        403, "forbidden",
    )


def test_unauthenticated_cannot_manage_warden_accounts(client):
    resp = create_warden(client, {}, username="anon.warden")
    assert_error(resp, 401, "token_invalid")
    assert_error(client.get("/api/v1/admin/wardens"), 401, "token_invalid")


# --------------------------------------------------------------------------
# 2. Administrator creates and assigns a warden
# --------------------------------------------------------------------------

def test_admin_creates_warden_with_hostel_grant(client, admin_env, hostel, db):
    resp = create_warden(client, admin_env, hostel_ids=[hostel.id])
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["username"] == "warden.ganga"
    assert body["role"] == "warden"            # never "admin"
    assert body["account_status"] == "active"  # staff activate on creation
    assert body["hostel_ids"] == [str(hostel.id)]
    assert body["hostel_names"] == [hostel.name]

    # It is listed for the administrator to see.
    listing = client.get("/api/v1/admin/wardens", headers=admin_env)
    assert listing.status_code == 200, listing.text
    usernames = [w["username"] for w in listing.json()["items"]]
    assert "warden.ganga" in usernames

    # And the provisioning step is on the record.
    entries = audit_actions(db, "warden.create")
    assert len(entries) == 1, entries
    assert entries[0].actor_label == "admin"
    assert entries[0].details["hostels"] == [str(hostel.id)]
    # The audit payload must never carry the password.
    assert "password" not in str(entries[0].details)


def test_warden_creation_validates_input(client, admin_env, hostel, db):
    # Too-short password.
    resp = create_warden(client, admin_env, password="short")
    assert_error(resp, 400, "invalid_payload")

    # Whitespace in the login name.
    resp = client.post("/api/v1/admin/wardens", headers=admin_env,
                       json={"username": "two words", "password": WARDEN_PW,
                             "hostel_ids": []})
    assert_error(resp, 400, "invalid_payload")

    # Missing username entirely.
    resp = client.post("/api/v1/admin/wardens", headers=admin_env,
                       json={"password": WARDEN_PW, "hostel_ids": []})
    assert_error(resp, 400, "invalid_payload")

    # Granting a hostel that does not exist must not silently succeed.
    resp = create_warden(client, admin_env, username="warden.ghost",
                         hostel_ids=[uuid.uuid4()])
    assert_error(resp, 404, "not_found")

    # Nothing was created by any of the failed attempts.
    db.expire_all()
    assert db.scalars(select(User).where(User.username == "warden.ghost")).first() is None


def test_duplicate_warden_username_rejected(client, admin_env, hostel, db):
    first = create_warden(client, admin_env, hostel_ids=[hostel.id])
    assert first.status_code == 201, first.text

    # Exact duplicate.
    dup = create_warden(client, admin_env, hostel_ids=[hostel.id])
    assert_error(dup, 409, "conflict")

    # Case-insensitive duplicate — usernames must be a unique login key.
    ci = create_warden(client, admin_env, username="WARDEN.GANGA",
                       hostel_ids=[hostel.id])
    assert_error(ci, 409, "conflict")

    db.expire_all()
    count = len(db.scalars(
        select(User).where(User.role == "warden")
    ).all())
    assert count == 1


# --------------------------------------------------------------------------
# 3. The created warden authenticates and sees only its own assignments
# --------------------------------------------------------------------------

def test_created_warden_signs_in_and_sees_assigned_hostel(
    client, admin_env, hostel, second_hostel,
):
    assert create_warden(client, admin_env, hostel_ids=[hostel.id]).status_code == 201
    headers = warden_login(client, "warden.ganga")

    # Authenticated identity comes from the session, not the request body.
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["role"] == "warden"

    # Only the granted hostel is visible — not the other hostel in the DB.
    hostels = client.get("/api/v1/warden/hostels", headers=headers)
    assert hostels.status_code == 200, hostels.text
    ids = [h["hostel_id"] for h in hostels.json()]
    assert ids == [str(hostel.id)]
    assert str(second_hostel.id) not in ids

    # The dashboard and roster load for this scope.
    assert client.get("/api/v1/warden/dashboard", headers=headers).status_code == 200
    roster = client.get("/api/v1/warden/students", headers=headers)
    assert roster.status_code == 200, roster.text
    assert roster.json()["items"] == []


def test_warden_cannot_manage_hostel_outside_grant(
    client, admin_env, hostel, second_hostel,
):
    """Changing a request parameter must not widen the warden's scope."""
    assert create_warden(client, admin_env, hostel_ids=[hostel.id]).status_code == 201
    headers = warden_login(client, "warden.ganga")

    # In-grant creation succeeds...
    ok = client.post(
        "/api/v1/warden/students", headers=headers,
        json={"student_id": "CS-2024-777", "name": "In Scope",
              "email": "cs-2024-777@ceconline.edu", "hostel_id": str(hostel.id),
              "room": "12"},
    )
    assert ok.status_code == 201, ok.text

    # ...the same call aimed at an ungranted hostel is refused.
    denied = client.post(
        "/api/v1/warden/students", headers=headers,
        json={"student_id": "CS-2024-778", "name": "Out Of Scope",
              "email": "cs-2024-778@ceconline.edu",
              "hostel_id": str(second_hostel.id), "room": "12"},
    )
    assert_error(denied, 403, "forbidden")

    # Filtering the roster by that hostel is refused too.
    assert_error(
        client.get(f"/api/v1/warden/students?hostel_id={second_hostel.id}",
                   headers=headers),
        403, "forbidden",
    )


def test_warden_without_grant_has_empty_roster(client, admin_env, hostel):
    resp = create_warden(client, admin_env, username="warden.unassigned",
                         hostel_ids=[])
    assert resp.status_code == 201, resp.text
    assert resp.json()["hostel_ids"] == []

    headers = warden_login(client, "warden.unassigned")
    assert client.get("/api/v1/warden/hostels", headers=headers).json() == []
    roster = client.get("/api/v1/warden/students", headers=headers)
    assert roster.status_code == 200
    assert roster.json()["items"] == []


def test_admin_can_grant_and_revoke_hostels_after_creation(
    client, admin_env, hostel, second_hostel,
):
    assert create_warden(client, admin_env, hostel_ids=[]).status_code == 201
    headers = warden_login(client, "warden.ganga")
    assert client.get("/api/v1/warden/hostels", headers=headers).json() == []

    # Grant.
    patched = client.patch("/api/v1/admin/wardens/warden.ganga",
                           headers=admin_env,
                           json={"hostel_ids": [str(hostel.id)]})
    assert patched.status_code == 200, patched.text
    assert patched.json()["hostel_ids"] == [str(hostel.id)]
    ids = [h["hostel_id"] for h in
           client.get("/api/v1/warden/hostels", headers=headers).json()]
    assert ids == [str(hostel.id)]

    # Swap to the other hostel — the old grant must not linger.
    swapped = client.patch("/api/v1/admin/wardens/warden.ganga",
                           headers=admin_env,
                           json={"hostel_ids": [str(second_hostel.id)]})
    assert swapped.status_code == 200, swapped.text
    ids = [h["hostel_id"] for h in
           client.get("/api/v1/warden/hostels", headers=headers).json()]
    assert ids == [str(second_hostel.id)]

    # Revoke entirely.
    revoked = client.patch("/api/v1/admin/wardens/warden.ganga",
                           headers=admin_env, json={"hostel_ids": []})
    assert revoked.status_code == 200, revoked.text
    assert client.get("/api/v1/warden/hostels", headers=headers).json() == []


# --------------------------------------------------------------------------
# 4. No path promotes anybody to administrator
# --------------------------------------------------------------------------

def test_role_cannot_be_set_through_warden_endpoints(client, admin_env, hostel, db):
    # Creation ignores a client-supplied role and hardcodes warden.
    resp = client.post(
        "/api/v1/admin/wardens", headers=admin_env,
        json={"username": "warden.escalate", "password": WARDEN_PW,
              "hostel_ids": [str(hostel.id)], "role": "admin",
              "account_status": "active"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "warden"

    # Update ignores it too — WardenPatch has no role field at all.
    patched = client.patch("/api/v1/admin/wardens/warden.escalate",
                           headers=admin_env,
                           json={"role": "admin", "hostel_ids": [str(hostel.id)]})
    assert patched.status_code == 200, patched.text
    assert patched.json()["role"] == "warden"

    db.expire_all()
    user = db.scalar(select(User).where(User.username == "warden.escalate"))
    assert user.role == "warden"

    # The only administrator is still the one created by the bootstrap.
    admins = db.scalars(select(User).where(User.role == "admin")).all()
    assert [a.username for a in admins] == ["admin"]


def test_warden_endpoint_cannot_touch_an_administrator(client, admin_env, db):
    """PATCH/DELETE resolve only role=warden, so admin accounts are unreachable."""
    assert_error(
        client.patch("/api/v1/admin/wardens/admin", headers=admin_env,
                     json={"account_status": "inactive"}),
        404, "not_found",
    )
    assert_error(
        client.delete("/api/v1/admin/wardens/admin", headers=admin_env),
        404, "not_found",
    )
    db.expire_all()
    admin = db.scalar(select(User).where(User.username == "admin"))
    assert admin.account_status == "active"


def test_unknown_warden_target_is_404(client, admin_env, hostel):
    assert_error(
        client.patch("/api/v1/admin/wardens/nobody", headers=admin_env,
                     json={"account_status": "inactive"}),
        404, "not_found",
    )
    assert_error(client.delete("/api/v1/admin/wardens/nobody", headers=admin_env),
                 404, "not_found")


# --------------------------------------------------------------------------
# 5. Activate / deactivate / recover / remove
# --------------------------------------------------------------------------

def test_admin_deactivates_warden_blocks_sign_in_then_restores(
    client, admin_env, hostel,
):
    assert create_warden(client, admin_env, hostel_ids=[hostel.id]).status_code == 201
    headers = warden_login(client, "warden.ganga")  # works while active

    off = client.patch("/api/v1/admin/wardens/warden.ganga",
                       headers=admin_env, json={"account_status": "inactive"})
    assert off.status_code == 200, off.text
    assert off.json()["account_status"] == "inactive"

    blocked = client.post("/api/v1/auth/login",
                          json={"student_id": "warden.ganga", "password": WARDEN_PW})
    assert_error(blocked, 403, "account_inactive")
    # A live session is cut too — deactivation must not merely leave the
    # bearer token to expire on its own.
    assert_error(client.get("/api/v1/warden/students", headers=headers),
                 403, "account_inactive")

    on = client.patch("/api/v1/admin/wardens/warden.ganga",
                      headers=admin_env, json={"account_status": "active"})
    assert on.status_code == 200, on.text
    assert on.json()["account_status"] == "active"
    warden_login(client, "warden.ganga")  # restored


def test_admin_resets_warden_password(client, admin_env, hostel, db):
    assert create_warden(client, admin_env, hostel_ids=[hostel.id]).status_code == 201

    reset = client.patch("/api/v1/admin/wardens/warden.ganga",
                         headers=admin_env,
                         json={"password": "Rotated-Warden-Pass2!"})
    assert reset.status_code == 200, reset.text
    assert "password" not in reset.text

    # Old password stops working, new one works.
    old = client.post("/api/v1/auth/login",
                      json={"student_id": "warden.ganga", "password": WARDEN_PW})
    assert_error(old, 401, "invalid_credentials")
    warden_login(client, "warden.ganga", "Rotated-Warden-Pass2!")

    # The reset is audited without the secret.
    entries = audit_actions(db, "warden.update")
    assert len(entries) == 1
    assert entries[0].details.get("password") == "reset"
    assert "Rotated-Warden-Pass2!" not in str(entries[0].details)


def test_delete_warden_removes_sign_in_and_access(client, admin_env, hostel, db):
    assert create_warden(client, admin_env, hostel_ids=[hostel.id]).status_code == 201
    headers = warden_login(client, "warden.ganga")
    assert client.get("/api/v1/warden/students", headers=headers).status_code == 200

    gone = client.delete("/api/v1/admin/wardens/warden.ganga", headers=admin_env)
    assert gone.status_code == 204, gone.text

    # Sign-in fails the same way an unknown account does (no enumeration).
    assert_error(
        client.post("/api/v1/auth/login",
                    json={"student_id": "warden.ganga", "password": WARDEN_PW}),
        401, "invalid_credentials",
    )
    assert_error(client.get("/api/v1/warden/students", headers=headers),
                 401, "token_invalid")

    listing = client.get("/api/v1/admin/wardens", headers=admin_env)
    assert [w["username"] for w in listing.json()["items"]] == []

    db.expire_all()
    assert db.scalar(select(User).where(User.username == "warden.ganga")) is None
    assert db.scalars(select(WardenHostel)).all() == []
    assert len(audit_actions(db, "warden.delete")) == 1


def test_warden_management_is_audited_end_to_end(client, admin_env, hostel, db):
    assert create_warden(client, admin_env, hostel_ids=[hostel.id]).status_code == 201
    client.patch("/api/v1/admin/wardens/warden.ganga", headers=admin_env,
                 json={"hostel_ids": []})
    client.delete("/api/v1/admin/wardens/warden.ganga", headers=admin_env)

    entries = audit_actions(db, "warden.create", "warden.update", "warden.delete")
    actions = [e.action for e in entries]
    assert actions == ["warden.create", "warden.update", "warden.delete"]
    # Acting staff recorded; affected account recorded; no secrets anywhere.
    for e in entries:
        assert e.actor_label == "admin"
        assert e.target_type == "user"
        assert e.target_id
        assert "password" not in str(e.details).lower().replace('"password": "reset"', "")
    assert entries[0].details["username"] == "warden.ganga"
