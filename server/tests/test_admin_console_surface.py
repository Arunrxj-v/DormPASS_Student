"""Admin Console support surface: stats, filtered rosters, hostel detail.

These are the read endpoints the new React Admin Console depends on. They are
asserted here against the live database so the console cannot be built against
an invented contract.
"""

from __future__ import annotations

import pytest

from conftest import assert_error

HOSTEL_BODY = {
    "name": "Yamuna Girls Hostel",
    "block": "A",
    "anchor_label": "Yamuna Block A",
    "latitude": 12.9716,
    "longitude": 79.1585,
    "permitted_radius_m": 120.0,
    "max_location_accuracy_m": 50.0,
}


@pytest.fixture
def admin_env(client, make_admin, login):
    make_admin(username="admin")
    token = login("admin", "AdminPass123!")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seeded(client, admin_env, make_hostel, make_warden, make_student):
    """One hostel, one active warden, students across lifecycle states."""
    hostel = make_hostel()
    make_warden(username="warden.one", hostels=[hostel])
    make_student(roll="CS-2022-084", hostel=hostel)  # active
    make_student(roll="CS-2022-101", hostel=hostel,
                 enrollment_status="details_verified")  # pending
    return hostel


class TestAdminStats:
    def test_counts_reflect_the_database(self, client, admin_env, seeded):
        resp = client.get("/api/v1/admin/stats", headers=admin_env)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["hostels"] == 1
        assert body["rooms"] == 0
        assert body["wardens"]["total"] == 1
        assert body["wardens"]["active"] == 1
        assert body["wardens"]["inactive"] == 0
        assert body["students"]["total"] == 2
        assert body["students"]["active"] == 1
        assert body["students"]["suspended"] == 0
        # details_verified is neither active nor suspended -> pending.
        assert body["students"]["pending_enrollment"] == 1
        assert body["students"]["by_status"] == {"active": 1, "details_verified": 1}

    def test_rooms_are_counted_once_registered(self, client, admin_env, seeded):
        hostel_id = client.post(
            "/api/v1/admin/hostels", headers=admin_env, json=HOSTEL_BODY
        ).json()["hostel_id"]
        for identifier in ("101", "102"):
            client.post(
                f"/api/v1/admin/hostels/{hostel_id}/rooms",
                headers=admin_env, json={"identifier": identifier},
            )
        body = client.get("/api/v1/admin/stats", headers=admin_env).json()
        assert body["rooms"] == 2
        assert body["hostels"] == 2  # seeded + created

    def test_suspended_wardens_are_reported_separately(
        self, client, admin_env, make_hostel, make_warden
    ):
        hostel = make_hostel()
        make_warden(username="warden.off", hostels=[hostel])
        client.patch(
            "/api/v1/admin/wardens/warden.off",
            headers=admin_env, json={"account_status": "inactive"},
        )
        body = client.get("/api/v1/admin/stats", headers=admin_env).json()
        assert body["wardens"] == {"total": 1, "active": 0, "inactive": 1}

    def test_requires_admin(self, client, make_hostel, make_warden, make_student, login):
        hostel = make_hostel()
        make_warden(username="warden.one", hostels=[hostel])
        student = make_student(roll="CS-2022-084", hostel=hostel)

        warden_token = login("warden.one", "WardenPass123!")
        assert_error(
            client.get("/api/v1/admin/stats",
                       headers={"Authorization": f"Bearer {warden_token}"}),
            403, "forbidden",
        )

        student_token = login(student.student_id, "student123!")
        assert_error(
            client.get("/api/v1/admin/stats",
                       headers={"Authorization": f"Bearer {student_token}"}),
            403, "forbidden",
        )
        assert_error(client.get("/api/v1/admin/stats"), 401, "token_invalid")


class TestFilteredRosters:
    def test_student_search_matches_roll_name_and_email(
        self, client, admin_env, make_hostel, make_student
    ):
        hostel = make_hostel()
        make_student(roll="CS-2022-084", name="Rohan Sharma", hostel=hostel)
        make_student(roll="CS-2022-101", name="Priya Nair", hostel=hostel)

        for query, expected in (
            ("CS-2022-084", "CS-2022-084"),
            ("rohan", "CS-2022-084"),
            ("Priya", "CS-2022-101"),
            ("cs-2022-101@ceconline.edu", "CS-2022-101"),
        ):
            body = client.get(
                "/api/v1/admin/students", headers=admin_env, params={"q": query}
            ).json()
            rolls = [s["student_id"] for s in body["items"]]
            assert rolls == [expected], f"q={query!r} -> {rolls}"

    def test_student_filters_by_hostel_and_status(
        self, client, admin_env, make_hostel, make_student
    ):
        hostel_a = make_hostel()
        hostel_b = make_hostel(name="Yamuna Girls Hostel", block="A")
        make_student(roll="CS-2022-084", hostel=hostel_a)
        make_student(roll="CS-2022-101", hostel=hostel_b, enrollment_status="details_verified")

        body = client.get("/api/v1/admin/students", headers=admin_env,
                          params={"hostel_id": str(hostel_a.id)}).json()
        assert [s["student_id"] for s in body["items"]] == ["CS-2022-084"]

        body = client.get("/api/v1/admin/students", headers=admin_env,
                          params={"enrollment_status": "details_verified"}).json()
        assert [s["student_id"] for s in body["items"]] == ["CS-2022-101"]

    def test_warden_search_and_status_filter(
        self, client, admin_env, make_hostel, make_warden
    ):
        hostel = make_hostel()
        make_warden(username="warden.alpha", hostels=[hostel])
        make_warden(username="warden.beta", hostels=[hostel])
        client.patch("/api/v1/admin/wardens/warden.beta", headers=admin_env,
                     json={"account_status": "inactive"})

        body = client.get("/api/v1/admin/wardens", headers=admin_env,
                          params={"q": "alpha"}).json()
        assert [w["username"] for w in body["items"]] == ["warden.alpha"]

        body = client.get("/api/v1/admin/wardens", headers=admin_env,
                          params={"account_status": "inactive"}).json()
        assert [w["username"] for w in body["items"]] == ["warden.beta"]

    def test_rosters_still_require_admin(self, client, make_hostel, make_warden, login):
        hostel = make_hostel()
        make_warden(username="warden.one", hostels=[hostel])
        token = login("warden.one", "WardenPass123!")
        headers = {"Authorization": f"Bearer {token}"}
        assert_error(client.get("/api/v1/admin/students", headers=headers), 403, "forbidden")
        assert_error(client.get("/api/v1/admin/wardens", headers=headers), 403, "forbidden")
