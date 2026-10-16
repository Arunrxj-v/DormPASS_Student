"""Attendance status, history pagination/absent synthesis, summary math."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core import clock
from app.models import AttendanceRecord
from conftest import assert_error, enroll, verify_body


def seed_records(db, student, hostel, days: list[int], month: tuple[int, int] = (2026, 10)):
    """Directly insert verified records for the given days of a month."""
    year, mon = month
    for day in days:
        db.add(AttendanceRecord(
            reference=f"HP-{year:04d}-{mon:02d}{day:02d}-2042",
            student_id=student.id,
            hostel_id=hostel.id,
            attendance_date=datetime(year, mon, day).date(),
            recorded_at=datetime(year, mon, day, 15, 12, 19, tzinfo=timezone.utc),
            outcome="verified",
            distance_m=21.0,
            accuracy_m=5.0,
            face_similarity=0.92,
            liveness_score=0.01,
            liveness_method="antispoof_model_v1",
        ))
    db.commit()


def test_history_pagination_and_absent_synthesis(student_env, db):
    """Days 1-11 present, day 12 absent (elapsed), day 13 = today (not yet)."""
    env = student_env
    seed_records(db, env.student, env.hostel, list(range(1, 12)))

    resp = env.client.get("/api/v1/attendance/history?month=2026-10&page_size=5&page=1",
                          headers=env.headers)
    assert resp.status_code == 200, resp.text
    page1 = resp.json()
    assert page1["page"] == 1
    assert page1["page_size"] == 5
    assert len(page1["items"]) == 5
    assert page1["total_pages"] == 3
    assert page1["has_more"] is True

    # Newest first: the synthesized absent day 2026-10-12 leads the list.
    first = page1["items"][0]
    assert first["status"] == "absent"
    assert first["reason"] == "curfew_window_missed"
    assert first["id"] is None
    assert first["reference"] is None
    assert first["date"] == "2026-10-12"
    assert first["recorded_at"] is None

    page2 = env.client.get("/api/v1/attendance/history?month=2026-10&page_size=5&page=2",
                           headers=env.headers).json()
    assert len(page2["items"]) == 5
    assert page2["has_more"] is True

    page3 = env.client.get("/api/v1/attendance/history?month=2026-10&page_size=5&page=3",
                           headers=env.headers).json()
    assert len(page3["items"]) == 2
    assert page3["has_more"] is False

    page4 = env.client.get("/api/v1/attendance/history?month=2026-10&page_size=5&page=4",
                           headers=env.headers).json()
    assert page4["items"] == []
    assert page4["total_pages"] == 3
    assert page4["has_more"] is False

    # Real records keep their full contract shape.
    present = [i for i in page3["items"] if i["status"] == "present"]
    assert present
    item = present[0]
    assert item["reference"].startswith("HP-2026-10")
    assert item["outcome"] == "verified"
    assert item["recorded_at"].endswith("Z")
    assert item["recorded_at_local"].endswith("+05:30")


def test_history_status_filter(student_env, db):
    env = student_env
    seed_records(db, env.student, env.hostel, list(range(1, 12)))  # day 12 absent

    absent = env.client.get(
        "/api/v1/attendance/history?month=2026-10&status=absent",
        headers=env.headers).json()
    assert len(absent["items"]) == 1
    assert absent["items"][0]["date"] == "2026-10-12"

    present = env.client.get(
        "/api/v1/attendance/history?month=2026-10&status=present",
        headers=env.headers).json()
    assert len(present["items"]) == 11

    pending = env.client.get(
        "/api/v1/attendance/history?month=2026-10&status=pending",
        headers=env.headers).json()
    assert pending["items"] == []
    assert pending["total_pages"] == 0


def test_history_invalid_month_and_status(student_env):
    env = student_env
    assert_error(env.client.get("/api/v1/attendance/history?month=2026-13",
                                headers=env.headers), 400, "invalid_payload")
    assert_error(env.client.get("/api/v1/attendance/history?status=banana",
                                headers=env.headers), 400, "invalid_payload")
    assert_error(env.client.get("/api/v1/attendance/history?page=0",
                                headers=env.headers), 400, "invalid_payload")


def test_summary_math_with_absent_day(student_env, db):
    """11 present + 1 absent (day 12) of 31 October days."""
    env = student_env
    seed_records(db, env.student, env.hostel, list(range(1, 12)))

    resp = env.client.get("/api/v1/attendance/summary?month=2026-10",
                          headers=env.headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["month"] == "2026-10"
    assert data["present"] == 11
    assert data["absent"] == 1
    assert data["outpass"] == 0  # outpass module not in v1
    assert data["days_accounted"] == 12
    assert data["total_days"] == 31
    assert data["rate_percent"] == 38.7  # round(100 * 12 / 31, 1)
    assert data["pass_threshold_percent"] == 85
    assert data["eligibility_safe"] is False


def test_summary_matches_docs_example(student_env, db, monkeypatch):
    """Reproduce the worked example from docs/API.md exactly.

    Feb 2028 (29 days), frozen at Feb 28 17:30 IST: days 1-27 elapsed,
    26 present + 1 absent => days_accounted 27, rate 93.1, safe >= 85.
    """
    env = student_env
    monkeypatch.setattr(clock, "utcnow",
                        lambda: datetime(2028, 2, 28, 12, 0, 0, tzinfo=timezone.utc))
    present_days = [d for d in range(1, 28) if d != 15]  # 26 present, day 15 absent
    seed_records(db, env.student, env.hostel, present_days, month=(2028, 2))

    data = env.client.get("/api/v1/attendance/summary?month=2028-02",
                          headers=env.headers).json()
    assert data["present"] == 26
    assert data["absent"] == 1
    assert data["outpass"] == 0
    assert data["rate_percent"] == 93.1
    assert data["days_accounted"] == 27
    assert data["total_days"] == 29
    assert data["pass_threshold_percent"] == 85
    assert data["eligibility_safe"] is True


def test_attendance_status_shape_and_flow(student_env):
    env = student_env

    resp = env.client.get("/api/v1/attendance/status", headers=env.headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["date"] == "2026-10-13"  # today in hostel tz (frozen clock)
    assert data["marked"] is False
    assert data["outcome"] is None
    assert data["record"] is None
    assert set(data["window"].keys()) == {
        "open", "opens_at", "closes_at", "minutes_remaining", "timezone"}
    assert data["window"]["open"] is True
    assert data["window"]["opens_at"] == "20:30"
    assert data["window"]["closes_at"] == "22:30"
    assert data["window"]["timezone"] == "Asia/Kolkata"
    assert 0 < data["window"]["minutes_remaining"] <= 108
    assert data["face_enrolled"] is False
    assert data["can_mark"] is False  # not enrolled

    # Enroll -> can_mark becomes true.
    enroll(env.client, env.headers)
    data = env.client.get("/api/v1/attendance/status", headers=env.headers).json()
    assert data["face_enrolled"] is True
    assert data["can_mark"] is True

    # Verify -> marked, no longer can_mark.
    resp = env.client.post("/api/v1/attendance/verify", headers=env.headers,
                           json=verify_body())
    assert resp.status_code == 200, resp.text
    data = env.client.get("/api/v1/attendance/status", headers=env.headers).json()
    assert data["marked"] is True
    assert data["outcome"] == "verified"
    assert data["record"]["reference"] == "HP-2026-1013-2042"
    assert data["can_mark"] is False

    # History now shows today as present (record exists even before close).
    history = env.client.get("/api/v1/attendance/history?month=2026-10",
                             headers=env.headers).json()
    statuses = [i["date"] for i in history["items"]]
    assert "2026-10-13" in statuses


def test_status_invalid_date(student_env):
    resp = student_env.client.get("/api/v1/attendance/status?date=13-10-2026",
                                  headers=student_env.headers)
    assert_error(resp, 400, "invalid_payload")
