"""Role enforcement: students never reach admin routes; public shapes."""

from __future__ import annotations

from conftest import assert_error


def test_unauthenticated_admin_access(client):
    assert_error(client.get("/api/v1/admin/students"), 401, "token_invalid")
    assert_error(client.get("/api/v1/admin/hostels"), 401, "token_invalid")
    assert_error(client.get("/api/v1/admin/audit-logs"), 401, "token_invalid")


def test_student_cannot_read_admin_routes(student_env):
    env = student_env
    for path in ("/api/v1/admin/students", "/api/v1/admin/hostels",
                 "/api/v1/admin/attendance", "/api/v1/admin/audit-logs"):
        assert_error(env.client.get(path, headers=env.headers), 403, "forbidden")


def test_student_cannot_mutate_admin_routes(student_env, make_hostel):
    env = student_env
    hostel = make_hostel(name="Other Hostel", block="A")
    assert_error(
        env.client.post("/api/v1/admin/students", headers=env.headers,
                        json={"student_id": "CS-2023-001", "name": "New Kid",
                              "password": "password123"}),
        403, "forbidden",
    )
    assert_error(
        env.client.put(f"/api/v1/admin/hostels/{hostel.id}", headers=env.headers,
                       json={"permitted_radius_m": 1.0}),
        403, "forbidden",
    )
    assert_error(
        env.client.delete(f"/api/v1/admin/students/{env.student.id}/face-enrollment",
                          headers=env.headers),
        403, "forbidden",
    )


def test_admin_can_access_admin_routes(client, make_admin, login):
    make_admin(username="admin")
    token = login("admin", "AdminPass123!")
    resp = client.get("/api/v1/admin/students",
                      headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


def test_geofence_shape_and_source_of_truth(student_env):
    """GET /hostels/me/geofence returns exactly the contract fields."""
    env = student_env
    resp = env.client.get("/api/v1/hostels/me/geofence", headers=env.headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    expected_keys = {
        "hostel_id", "name", "block", "anchor_label", "latitude", "longitude",
        "permitted_radius_m", "max_location_accuracy_m", "boundary_policy",
        "timezone", "window_start", "window_end", "require_liveness",
        "face_match_threshold", "warden_name", "warden_extension",
    }
    assert set(data.keys()) == expected_keys, data.keys()
    assert data["hostel_id"] == str(env.hostel.id)
    assert data["latitude"] == 12.9716
    assert data["longitude"] == 79.1585
    assert data["permitted_radius_m"] == 120.0
    assert data["max_location_accuracy_m"] == 50.0
    assert data["boundary_policy"] == "conservative"
    assert data["timezone"] == "Asia/Kolkata"
    assert data["window_start"] == "20:30"
    assert data["window_end"] == "22:30"
    assert data["require_liveness"] is True
    assert data["face_match_threshold"] == 0.75


def test_geofence_without_hostel_raises(client, make_student, login):
    make_student(roll="CS-2022-077")  # no hostel assigned
    token = login("CS-2022-077", "student123!")
    resp = client.get("/api/v1/hostels/me/geofence",
                      headers={"Authorization": f"Bearer {token}"})
    assert_error(resp, 403, "hostel_not_configured")


def test_health_and_public_config(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["version"] == "1.0.0"
    assert body["database"] == "up"

    config = client.get("/api/v1/config/public")
    assert config.status_code == 200
    cfg = config.json()
    assert set(cfg.keys()) == {
        "google_sso_enabled",
        "app_min_version",
        "support_extension",
        "curfew_window_start",
        "curfew_window_end",
        "curfew_timezone",
    }
    assert cfg["google_sso_enabled"] is False
    assert cfg["app_min_version"] == "1.0.0"
    assert cfg["support_extension"] == "#442"
    # Unset institution defaults are null — the app shows its honest
    # "set by your hostel" fallback rather than inventing a window.
    assert cfg["curfew_window_start"] is None
    assert cfg["curfew_window_end"] is None
    assert cfg["curfew_timezone"] is None


def test_public_config_surfaces_configured_curfew_window(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "curfew_window_start", "20:30")
    monkeypatch.setattr(settings, "curfew_window_end", "22:30")
    monkeypatch.setattr(settings, "curfew_timezone", "Asia/Kolkata")

    cfg = client.get("/api/v1/config/public").json()
    assert cfg["curfew_window_start"] == "20:30"
    assert cfg["curfew_window_end"] == "22:30"
    assert cfg["curfew_timezone"] == "Asia/Kolkata"


def test_public_config_google_flag_is_derived_from_the_real_capability(
    client, monkeypatch
):
    """`google_sso_enabled` must track GOOGLE_OAUTH_CLIENT_ID, not a second flag.

    Two independent switches would let a deployment advertise a "Continue with
    Google" button the backend answers with 503 google_signin_not_configured —
    or hide one that would actually work.
    """
    from app.core.config import settings

    assert settings.google_oauth_client_id == ""
    assert client.get("/api/v1/config/public").json()["google_sso_enabled"] is False

    monkeypatch.setattr(
        settings, "google_oauth_client_id", "12345.apps.googleusercontent.com"
    )
    assert (
        client.get("/api/v1/config/public").json()["google_sso_enabled"] is True
    )

    # Empty / whitespace-only must both read as disabled, never truthy.
    for blank in ("", "   "):
        monkeypatch.setattr(settings, "google_oauth_client_id", blank)
        assert client.get("/api/v1/config/public").json()["google_sso_enabled"] is False
