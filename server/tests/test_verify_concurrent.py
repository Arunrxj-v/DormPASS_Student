"""Concurrent duplicate prevention: UNIQUE(student_id, attendance_date) holds
under parallel verify calls from separate sessions/clients."""

from __future__ import annotations

import concurrent.futures as cf

from sqlalchemy import select

from app.models import AttendanceRecord
from conftest import enroll, verify_body

VERIFY = "/api/v1/attendance/verify"


def test_concurrent_duplicates_exactly_one_200(student_env, app, db):
    """5 threads race the same student/day: exactly one 200, rest 409."""
    env = student_env
    emb = enroll(env.client, env.headers)
    body = verify_body(emb)

    def attempt() -> int:
        from fastapi.testclient import TestClient

        with TestClient(app) as client:  # separate client (own sessions)
            resp = client.post(VERIFY, headers=env.headers, json=body)
            return resp.status_code

    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        statuses = [future.result() for future in [pool.submit(attempt) for _ in range(5)]]

    assert statuses.count(200) == 1, statuses
    assert statuses.count(409) == 4, statuses

    rows = db.scalars(select(AttendanceRecord).where(
        AttendanceRecord.student_id == env.student.id)).all()
    assert len(rows) == 1
    assert rows[0].outcome == "verified"
