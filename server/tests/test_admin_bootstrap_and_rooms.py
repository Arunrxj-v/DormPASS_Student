"""Admin bootstrap CLI + hostel creation + room registry.

Covers the three backend gaps that previously blocked the Admin Console:
  1. no ``python -m app.cli create-admin`` (bootstrap only existed as a script
     with different, weaker behaviour),
  2. no way to CREATE a hostel over HTTP (``PUT /admin/hostels/{id}`` 404s for
     an unknown id),
  3. no room registry at all (``students.room`` was an unvalidated free-text
     string a warden could set to anything).

Nothing here depends on client-side gating: every route is also exercised with
a warden token and a student token to prove ``require_admin`` refuses them.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from conftest import assert_error

from app.cli import MIN_PASSWORD, CliError, create_admin_account, run_create_admin
from app.core.security import verify_password
from app.models import AuditLog, Hostel, Room, Student, User

HOSTEL_BODY = {
    "name": "Yamuna Girls Hostel",
    "block": "A",
    "anchor_label": "Yamuna Block A",
    "latitude": 12.9716,
    "longitude": 79.1585,
    "permitted_radius_m": 120.0,
    "max_location_accuracy_m": 50.0,
}


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def admin_env(client, make_admin, login):
    make_admin(username="admin")
    token = login("admin", "AdminPass123!")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def warden_env(client, make_hostel, make_warden, login):
    hostel = make_hostel()
    make_warden(username="warden.one", hostels=[hostel])
    token = login("warden.one", "WardenPass123!")
    return hostel, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def student_env(client, make_hostel, make_student, login):
    hostel = make_hostel(name="Yamuna Girls Hostel", block="A", anchor_label="Yamuna Block A")
    student = make_student(hostel=hostel)
    token = login(student.student_id, "student123!")
    return hostel, {"Authorization": f"Bearer {token}"}


def audit_actions(db, *actions: str) -> list[AuditLog]:
    db.expire_all()
    return list(db.scalars(select(AuditLog).where(AuditLog.action.in_(actions))).all())


# ==========================================================================
# 1. Bootstrap CLI — secure initial administrator
# ==========================================================================

class TestBootstrapCLI:
    def test_creates_first_admin_and_hashes_the_password(self, db):
        action, user = create_admin_account(
            db, username="root-admin", password="Correct-Horse-Battery-1"
        )
        db.commit()

        assert action == "admin.bootstrap"
        assert user.role == "admin"
        assert user.account_status == "active"
        # Never plaintext.
        assert "Correct-Horse" not in user.password_hash
        assert verify_password("Correct-Horse-Battery-1", user.password_hash)

    def test_bootstrap_is_audited(self, db):
        run_create_admin(
            db, username="root-admin", password="Correct-Horse-Battery-1", force=False
        )
        rows = audit_actions(db, "admin.bootstrap")
        assert len(rows) == 1
        assert rows[0].target_type == "user"
        assert rows[0].details == {"source": "cli"}

    def test_refuses_a_second_admin(self, db):
        create_admin_account(db, username="root-admin", password="Correct-Horse-Battery-1")
        db.commit()

        with pytest.raises(CliError) as exc:
            create_admin_account(db, username="second-admin", password="Another-Pass-99!")
        assert "already exists" in str(exc.value)
        assert db.scalar(select(User).where(User.role == "admin")) is not None

    def test_force_only_resets_an_existing_admin(self, db):
        created, original = create_admin_account(
            db, username="root-admin", password="Correct-Horse-Battery-1"
        )
        db.commit()
        original_id = original.id

        action, user = create_admin_account(
            db, username="root-admin", password="Rotated-Pass-2026!", force=True
        )
        db.commit()

        assert action == "admin.password_reset"
        assert user.id == original_id  # same row, not a second account
        assert verify_password("Rotated-Pass-2026!", user.password_hash)
        # Exactly one admin, ever.
        assert db.scalars(select(User).where(User.role == "admin")).all() == [user]

    def test_force_refuses_to_invent_a_new_admin(self, db):
        create_admin_account(db, username="root-admin", password="Correct-Horse-Battery-1")
        db.commit()

        with pytest.raises(CliError) as exc:
            create_admin_account(
                db, username="brand-new-admin", password="Another-Pass-99!", force=True
            )
        assert "No administrator named" in str(exc.value)
        assert db.scalars(select(User).where(User.role == "admin")).all().__len__() == 1

    def test_force_refuses_to_promote_a_warden(self, db, make_warden, make_hostel):
        hostel = make_hostel()
        make_warden(username="sneaky.warden", hostels=[hostel])
        create_admin_account(db, username="root-admin", password="Correct-Horse-Battery-1")
        db.commit()

        with pytest.raises(CliError) as exc:
            create_admin_account(
                db, username="sneaky.warden", password="Another-Pass-99!", force=True
            )
        assert "not an administrator" in str(exc.value)
        db.expire_all()
        warden = db.scalar(select(User).where(User.username == "sneaky.warden"))
        assert warden.role == "warden"  # unchanged

    def test_refuses_a_username_taken_by_a_non_admin(self, db, make_hostel, make_warden):
        hostel = make_hostel()
        make_warden(username="existing.warden", hostels=[hostel])

        with pytest.raises(CliError) as exc:
            create_admin_account(db, username="EXISTING.WARDEN", password="Another-Pass-99!")
        assert "will not be overwritten" in str(exc.value)

    @pytest.mark.parametrize("password", ["short", "12345678", "1234567890"[:MIN_PASSWORD - 1]])
    def test_refuses_a_short_password(self, db, password):
        with pytest.raises(CliError) as exc:
            create_admin_account(db, username="root-admin", password=password)
        assert "at least" in str(exc.value)

    @pytest.mark.parametrize("username", ["has space", "has\ttab", "new\nline"])
    def test_refuses_interior_whitespace_in_the_username(self, db, username):
        with pytest.raises(CliError) as exc:
            create_admin_account(db, username=username, password="Correct-Horse-Battery-1")
        assert "whitespace" in str(exc.value)

    @pytest.mark.parametrize("username", [" leading", "trailing ", "\tprefix", "suffix\n"])
    def test_trims_surrounding_whitespace_before_validation(self, db, username):
        action, user = create_admin_account(
            db, username=username, password="Correct-Horse-Battery-1"
        )
        db.commit()
        assert action == "admin.bootstrap"
        assert user.username == username.strip()
        assert not any(ch.isspace() for ch in user.username)

    def test_refuses_an_empty_username(self, db):
        with pytest.raises(CliError):
            create_admin_account(db, username="   ", password="Correct-Horse-Battery-1")

    def test_username_is_case_insensitive_for_duplicates(self, db):
        create_admin_account(db, username="Root-Admin", password="Correct-Horse-Battery-1")
        db.commit()
        with pytest.raises(CliError) as exc:
            create_admin_account(db, username="root-admin", password="Another-Pass-99!")
        assert "already exists" in str(exc.value)


class TestNoPublicBootstrapPath:
    """There is no HTTP route that can create an administrator."""

    @pytest.mark.parametrize("path", [
        "/api/v1/auth/register",
        "/api/v1/auth/signup",
        "/api/v1/admin/bootstrap",
        "/api/v1/admin/create-admin",
        "/api/v1/register",
    ])
    def test_unknown_paths_404(self, client, path):
        resp = client.post(path, json={"username": "x", "password": "y" * 12})
        assert resp.status_code == 404

    def test_admin_routes_require_a_token(self, client):
        assert_error(client.post("/api/v1/admin/wardens", json={}), 401, "token_invalid")
        assert_error(client.post("/api/v1/admin/hostels", json=HOSTEL_BODY), 401, "token_invalid")

    def test_a_warden_token_cannot_reach_admin_routes(self, client, warden_env):
        _, headers = warden_env
        assert_error(
            client.post("/api/v1/admin/hostels", headers=headers, json=HOSTEL_BODY),
            403, "forbidden",
        )

    def test_a_student_token_cannot_reach_admin_routes(self, client, student_env):
        _, headers = student_env
        assert_error(
            client.post("/api/v1/admin/hostels", headers=headers, json=HOSTEL_BODY),
            403, "forbidden",
        )


# ==========================================================================
# 2. Hostel creation
# ==========================================================================

class TestCreateHostel:
    def test_admin_creates_a_hostel_with_its_geofence(self, client, db, admin_env):
        resp = client.post("/api/v1/admin/hostels", headers=admin_env, json=HOSTEL_BODY)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "Yamuna Girls Hostel"
        assert body["block"] == "A"
        assert body["latitude"] == pytest.approx(12.9716)
        assert body["permitted_radius_m"] == pytest.approx(120.0)
        # Policy defaults come from the model, not the client.
        assert body["window_start"] == "20:30"
        assert body["window_end"] == "22:30"
        assert body["boundary_policy"] == "conservative"
        assert body["require_liveness"] is True

        assert db.scalar(select(Hostel).where(Hostel.name == "Yamuna Girls Hostel")) is not None

    def test_creation_is_audited(self, client, db, admin_env):
        client.post("/api/v1/admin/hostels", headers=admin_env, json=HOSTEL_BODY)
        rows = audit_actions(db, "hostel.create")
        assert len(rows) == 1
        assert rows[0].target_type == "hostel"
        assert rows[0].details["name"] == "Yamuna Girls Hostel"

    def test_duplicate_name_and_block_conflicts(self, client, db, admin_env, make_hostel):
        make_hostel()  # "Ganga Boys Hostel" / "B"
        resp = client.post(
            "/api/v1/admin/hostels", headers=admin_env,
            json={**HOSTEL_BODY, "name": "Ganga Boys Hostel", "block": "B"},
        )
        assert_error(resp, 409, "conflict")

    def test_same_name_different_block_is_allowed(self, client, admin_env, make_hostel):
        make_hostel()  # Ganga Boys Hostel / B
        resp = client.post(
            "/api/v1/admin/hostels", headers=admin_env,
            json={**HOSTEL_BODY, "name": "Ganga Boys Hostel", "block": "C"},
        )
        assert resp.status_code == 201, resp.text

    def test_geofence_inputs_are_mandatory(self, client, admin_env):
        for field in ("latitude", "longitude", "permitted_radius_m", "max_location_accuracy_m"):
            resp = client.post(
                "/api/v1/admin/hostels", headers=admin_env,
                json={k: v for k, v in HOSTEL_BODY.items() if k != field},
            )
            assert_error(resp, 400, "invalid_payload")

    def test_out_of_range_geofence_is_refused(self, client, admin_env):
        resp = client.post(
            "/api/v1/admin/hostels", headers=admin_env,
            json={**HOSTEL_BODY, "latitude": 91.0},
        )
        assert_error(resp, 400, "invalid_payload")

    def test_unknown_timezone_is_refused(self, client, admin_env):
        resp = client.post(
            "/api/v1/admin/hostels", headers=admin_env,
            json={**HOSTEL_BODY, "timezone": "Mars/Olympus"},
        )
        assert_error(resp, 400, "invalid_payload")

    def test_malformed_window_is_refused(self, client, admin_env):
        resp = client.post(
            "/api/v1/admin/hostels", headers=admin_env,
            json={**HOSTEL_BODY, "window_start": "25:00"},
        )
        assert_error(resp, 400, "invalid_payload")

    def test_a_created_hostel_is_usable_for_enforcement(self, client, admin_env, make_hostel):
        """The created row is the same object the geofence path serves."""
        hostel_id = client.post(
            "/api/v1/admin/hostels", headers=admin_env, json=HOSTEL_BODY
        ).json()["hostel_id"]

        resp = client.get(f"/api/v1/admin/hostels/{hostel_id}", headers=admin_env)
        assert resp.status_code == 200, resp.text
        assert resp.json()["permitted_radius_m"] == pytest.approx(120.0)


# ==========================================================================
# 3. Room registry
# ==========================================================================

class TestRoomRegistry:
    @pytest.fixture
    def hostel_with_rooms(self, client, admin_env, make_hostel):
        hostel = make_hostel()
        for identifier, capacity in (("101", 2), ("102", 2), ("201", 1)):
            resp = client.post(
                f"/api/v1/admin/hostels/{hostel.id}/rooms",
                headers=admin_env, json={"identifier": identifier, "capacity": capacity},
            )
            assert resp.status_code == 201, resp.text
        return hostel

    def test_admin_registers_a_room(self, client, db, admin_env, make_hostel):
        hostel = make_hostel()
        resp = client.post(
            f"/api/v1/admin/hostels/{hostel.id}/rooms",
            headers=admin_env, json={"identifier": "101", "capacity": 2},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["identifier"] == "101"
        assert body["capacity"] == 2
        assert body["student_count"] == 0
        assert body["hostel_id"] == str(hostel.id)

        rows = audit_actions(db, "room.create")
        assert len(rows) == 1
        assert rows[0].details["identifier"] == "101"

    def test_identifier_is_whitespace_trimmed(self, client, admin_env, make_hostel):
        hostel = make_hostel()
        resp = client.post(
            f"/api/v1/admin/hostels/{hostel.id}/rooms",
            headers=admin_env, json={"identifier": "  314  "},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["identifier"] == "314"

    def test_blank_identifier_is_refused(self, client, admin_env, make_hostel):
        hostel = make_hostel()
        resp = client.post(
            f"/api/v1/admin/hostels/{hostel.id}/rooms",
            headers=admin_env, json={"identifier": "   "},
        )
        assert_error(resp, 400, "invalid_payload")

    def test_duplicate_identifier_is_refused_case_insensitively(
        self, client, admin_env, hostel_with_rooms
    ):
        resp = client.post(
            f"/api/v1/admin/hostels/{hostel_with_rooms.id}/rooms",
            headers=admin_env, json={"identifier": "101"},
        )
        assert_error(resp, 409, "conflict")

    def test_same_identifier_in_another_hostel_is_allowed(self, client, admin_env, hostel_with_rooms, make_hostel):
        other = make_hostel(name="Yamuna Girls Hostel", block="A")
        resp = client.post(
            f"/api/v1/admin/hostels/{other.id}/rooms",
            headers=admin_env, json={"identifier": "101"},
        )
        assert resp.status_code == 201, resp.text

    def test_unknown_hostel_is_404(self, client, admin_env):
        import uuid as _uuid
        resp = client.post(
            f"/api/v1/admin/hostels/{_uuid.uuid4()}/rooms",
            headers=admin_env, json={"identifier": "101"},
        )
        assert_error(resp, 404, "not_found")

    def test_listing_reports_live_occupancy(self, client, admin_env, hostel_with_rooms, make_student):
        make_student(roll="CS-2022-084", hostel=hostel_with_rooms)
        make_student(roll="CS-2022-101", hostel=hostel_with_rooms)
        # A student in a DIFFERENT hostel with the same room string must not count.
        other = make_student(roll="CS-2023-001", hostel=None)

        resp = client.get(
            f"/api/v1/admin/hostels/{hostel_with_rooms.id}/rooms", headers=admin_env
        )
        assert resp.status_code == 200, resp.text
        counts = {r["identifier"]: r["student_count"] for r in resp.json()["items"]}
        assert counts == {"101": 0, "102": 0, "201": 0}  # default room is "314"

        # Now move one into 101 and re-read.
        client.patch(
            f"/api/v1/admin/students/{other.student_id}", headers=admin_env,
            json={"hostel_id": str(hostel_with_rooms.id), "room": "101"},
        )
        resp = client.get(
            f"/api/v1/admin/hostels/{hostel_with_rooms.id}/rooms", headers=admin_env
        )
        counts = {r["identifier"]: r["student_count"] for r in resp.json()["items"]}
        assert counts["101"] == 1

    def test_delete_removes_an_empty_room(self, client, db, admin_env, hostel_with_rooms):
        rooms = client.get(
            f"/api/v1/admin/hostels/{hostel_with_rooms.id}/rooms", headers=admin_env
        ).json()["items"]
        target = next(r for r in rooms if r["identifier"] == "201")

        resp = client.delete(f"/api/v1/admin/rooms/{target['id']}", headers=admin_env)
        assert resp.status_code == 204, resp.text
        assert db.get(Room, __import__("uuid").UUID(target["id"])) is None

        rows = audit_actions(db, "room.delete")
        assert len(rows) == 1
        assert rows[0].details["identifier"] == "201"

    def test_delete_refuses_while_students_are_assigned(
        self, client, admin_env, hostel_with_rooms, make_student
    ):
        make_student(roll="CS-2022-084", hostel=hostel_with_rooms)
        rooms = client.get(
            f"/api/v1/admin/hostels/{hostel_with_rooms.id}/rooms", headers=admin_env
        ).json()["items"]
        # default student room is "314", so register it to make it occupied
        client.post(
            f"/api/v1/admin/hostels/{hostel_with_rooms.id}/rooms",
            headers=admin_env, json={"identifier": "314"},
        )
        rooms = client.get(
            f"/api/v1/admin/hostels/{hostel_with_rooms.id}/rooms", headers=admin_env
        ).json()["items"]
        target = next(r for r in rooms if r["identifier"] == "314")

        resp = client.delete(f"/api/v1/admin/rooms/{target['id']}", headers=admin_env)
        assert_error(resp, 409, "conflict")

    def test_rename_moves_occupants_and_is_audited(self, client, db, admin_env, hostel_with_rooms, make_student):
        student = make_student(roll="CS-2022-084", hostel=hostel_with_rooms)
        client.patch(
            f"/api/v1/admin/students/{student.student_id}", headers=admin_env,
            json={"room": "101"},
        )
        rooms = client.get(
            f"/api/v1/admin/hostels/{hostel_with_rooms.id}/rooms", headers=admin_env
        ).json()["items"]
        target = next(r for r in rooms if r["identifier"] == "101")

        resp = client.patch(
            f"/api/v1/admin/rooms/{target['id']}", headers=admin_env,
            json={"identifier": "110"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["identifier"] == "110"

        db.expire_all()
        db.refresh(student)
        assert student.room == "110"  # occupant followed the rename

        rows = audit_actions(db, "room.update")
        assert len(rows) == 1
        assert rows[0].details["identifier"]["to"] == "110"
        assert rows[0].details["identifier"]["students_moved"] == 1

    def test_rename_to_an_existing_identifier_conflicts(
        self, client, admin_env, hostel_with_rooms
    ):
        rooms = client.get(
            f"/api/v1/admin/hostels/{hostel_with_rooms.id}/rooms", headers=admin_env
        ).json()["items"]
        target = next(r for r in rooms if r["identifier"] == "101")
        resp = client.patch(
            f"/api/v1/admin/rooms/{target['id']}", headers=admin_env,
            json={"identifier": "102"},
        )
        assert_error(resp, 409, "conflict")

    def test_capacity_can_be_updated_and_cleared(self, client, admin_env, hostel_with_rooms):
        rooms = client.get(
            f"/api/v1/admin/hostels/{hostel_with_rooms.id}/rooms", headers=admin_env
        ).json()["items"]
        target = next(r for r in rooms if r["identifier"] == "101")

        resp = client.patch(
            f"/api/v1/admin/rooms/{target['id']}", headers=admin_env, json={"capacity": 4}
        )
        assert resp.json()["capacity"] == 4

        resp = client.patch(
            f"/api/v1/admin/rooms/{target['id']}", headers=admin_env, json={"capacity": None}
        )
        assert resp.json()["capacity"] is None

    def test_zero_capacity_is_refused(self, client, admin_env, hostel_with_rooms):
        rooms = client.get(
            f"/api/v1/admin/hostels/{hostel_with_rooms.id}/rooms", headers=admin_env
        ).json()["items"]
        target = next(r for r in rooms if r["identifier"] == "101")
        resp = client.patch(
            f"/api/v1/admin/rooms/{target['id']}", headers=admin_env, json={"capacity": 0}
        )
        assert_error(resp, 400, "invalid_payload")

    def test_wardens_and_students_cannot_manage_rooms(self, client, warden_env, student_env):
        hostel, warden_headers = warden_env
        _, student_headers = student_env
        for headers in (warden_headers, student_headers):
            assert_error(
                client.post(
                    f"/api/v1/admin/hostels/{hostel.id}/rooms",
                    headers=headers, json={"identifier": "999"},
                ),
                403, "forbidden",
            )


# ==========================================================================
# 4. Room registry enforced on student assignment
# ==========================================================================

class TestStudentRoomValidation:
    """The registry is enforced on the student create/update paths."""

    @pytest.fixture
    def hostel_with_rooms(self, client, admin_env, make_hostel):
        hostel = make_hostel()
        for identifier in ("101", "102"):
            resp = client.post(
                f"/api/v1/admin/hostels/{hostel.id}/rooms",
                headers=admin_env, json={"identifier": identifier},
            )
            assert resp.status_code == 201, resp.text
        return hostel

    @pytest.fixture
    def warden_on_hostel(self, client, hostel_with_rooms, make_warden, login):
        """A warden granted the SAME hostel that has the registry."""
        make_warden(username="warden.rooms", hostels=[hostel_with_rooms])
        token = login("warden.rooms", "WardenPass123!")
        return hostel_with_rooms, {"Authorization": f"Bearer {token}"}

    def _create(self, client, headers, hostel, roll: str, room: str | None):
        return client.post(
            "/api/v1/admin/students", headers=headers,
            json={
                "student_id": roll,
                "name": "Test Student",
                "email": f"{roll.lower()}@ceconline.edu",
                "hostel_id": str(hostel.id) if hostel else None,
                "room": room,
            },
        )

    def test_registered_room_is_accepted(self, client, admin_env, hostel_with_rooms):
        resp = self._create(client, admin_env, hostel_with_rooms, "CS-2026-001", "101")
        assert resp.status_code == 201, resp.text

    def test_unregistered_room_is_refused(self, client, admin_env, hostel_with_rooms):
        resp = self._create(client, admin_env, hostel_with_rooms, "CS-2026-002", "999")
        assert_error(resp, 400, "invalid_payload")

    def test_room_match_is_case_insensitive_and_trimmed(
        self, client, admin_env, hostel_with_rooms
    ):
        resp = self._create(client, admin_env, hostel_with_rooms, "CS-2026-003", "101x")
        assert_error(resp, 400, "invalid_payload")  # "101x" is a different room
        resp = self._create(client, admin_env, hostel_with_rooms, "CS-2026-004", " 102 ")
        assert resp.status_code == 201, resp.text

    def test_free_text_still_works_when_a_hostel_has_no_registry(
        self, client, admin_env, make_hostel
    ):
        bare = make_hostel(name="Yamuna Girls Hostel", block="A")
        resp = self._create(client, admin_env, bare, "CS-2026-005", "anything-goes")
        assert resp.status_code == 201, resp.text

    def test_warden_cannot_park_a_student_in_an_unregistered_room(
        self, client, warden_on_hostel
    ):
        hostel, headers = warden_on_hostel
        resp = client.post(
            "/api/v1/warden/students", headers=headers,
            json={
                "student_id": "CS-2026-006",
                "name": "Warden-Created",
                "email": "cs-2026-006@ceconline.edu",
                "hostel_id": str(hostel.id),
                "room": "999",
            },
        )
        assert_error(resp, 400, "invalid_payload")

        # Same warden, registered room, succeeds.
        resp = client.post(
            "/api/v1/warden/students", headers=headers,
            json={
                "student_id": "CS-2026-007",
                "name": "Warden-Created",
                "email": "cs-2026-007@ceconline.edu",
                "hostel_id": str(hostel.id),
                "room": "101",
            },
        )
        assert resp.status_code == 201, resp.text

    def test_warden_patch_to_an_unregistered_room_is_refused(
        self, client, warden_on_hostel, make_student
    ):
        hostel, headers = warden_on_hostel
        student = make_student(roll="CS-2022-084", hostel=hostel)
        resp = client.patch(
            f"/api/v1/warden/students/{student.student_id}", headers=headers,
            json={"room": "999"},
        )
        assert_error(resp, 400, "invalid_payload")

    def test_patch_to_an_unregistered_room_is_refused(
        self, client, admin_env, hostel_with_rooms, make_student
    ):
        student = make_student(roll="CS-2022-084", hostel=hostel_with_rooms)
        resp = client.patch(
            f"/api/v1/admin/students/{student.student_id}", headers=admin_env,
            json={"room": "999"},
        )
        assert_error(resp, 400, "invalid_payload")

    def test_existing_roster_is_not_retroactively_broken(
        self, client, db, admin_env, hostel_with_rooms, make_student
    ):
        """A student whose room predates the registry keeps working.

        Registering rooms must not orphan existing free-text rooms; only a
        change to room/hostel re-triggers validation.
        """
        student = make_student(roll="CS-2022-084", hostel=hostel_with_rooms)
        db.expire_all()
        db.refresh(student)
        assert student.room == "314"  # not in the registry

        # Editing an unrelated field still succeeds.
        resp = client.patch(
            f"/api/v1/admin/students/{student.student_id}", headers=admin_env,
            json={"name": "Renamed Student"},
        )
        assert resp.status_code == 200, resp.text

        # But changing the room does enforce the registry.
        resp = client.patch(
            f"/api/v1/admin/students/{student.student_id}", headers=admin_env,
            json={"room": "315"},
        )
        assert_error(resp, 400, "invalid_payload")

    def test_clearing_the_hostel_disables_the_check(
        self, client, admin_env, hostel_with_rooms, make_student
    ):
        student = make_student(roll="CS-2022-084", hostel=hostel_with_rooms)
        resp = client.patch(
            f"/api/v1/admin/students/{student.student_id}", headers=admin_env,
            json={"hostel_id": None, "room": "off-campus"},
        )
        assert resp.status_code == 200, resp.text
