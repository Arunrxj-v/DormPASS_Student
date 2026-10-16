# HostelPass server

Backend for HostelPass (a.k.a. DormPASS): GPS-geofence + face-recognition
curfew attendance API. Implements `docs/API.md` exactly — paths, field names,
the `{"error":{"code","message","details"}}` envelope, and the verify pipeline
order.

## Stack

- FastAPI 0.115.12 / Uvicorn 0.34.0 / Pydantic 2.11.4
- SQLAlchemy 2.0.41 + Alembic 1.15.2 + psycopg 3.2.9 (PostgreSQL 16)
- PyJWT 2.10.1 (HS256), bcrypt 4.3.0, cryptography 45.0.3 (Fernet templates)
- numpy 2.2.5 for cosine similarity
- dev: pytest 8.3.5, httpx 0.28.1 — no Redis, Celery, or vector DB

## Quick start (host machine)

```bash
cd server

# 1. Database (compose, loopback-only on 127.0.0.1:5433)
docker compose up -d db

# 2. Python env (Python 3.13 via Homebrew)
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# 3. Configure + migrate + seed
cp .env.example .env          # then set JWT_SECRET / FACE_TEMPLATE_KEY
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed.py

# 4. Run locally
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Seeded credentials: `admin` / `AdminPass123!` (warden), `CS-2022-084` and
`CS-2022-101` / `student123!` (students), Ganga Boys Hostel block B with the
20:30–22:30 IST window.

## Tests (real PostgreSQL)

```bash
docker compose up -d db       # required
.venv/bin/pytest -q           # 63 passed
```

The suite drops/creates a dedicated `hostelpass_test` database, runs
`alembic upgrade head`, truncates all tables between tests, and freezes the
attendance decision clock at `2026-10-13T15:12:19Z` (20:42:19 IST, inside the
seeded window) for determinism.

## Full stack in Docker

```bash
docker compose up -d --build   # db + api (api health: GET /api/v1/health)
```

The `api` service runs as a non-root user on `python:3.12-slim` with
`--workers 1`, `mem_limit 512m`, `cpus 1.0`, and a curl healthcheck against
`/api/v1/health`. Inside the compose network it reaches Postgres as
`db:5432`; on the host it is `127.0.0.1:5433`.

## Smoke test

```bash
BASE=http://localhost:8000/api/v1

curl -s $BASE/health
TOKEN=$(curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"student_id":"CS-2022-084","password":"student123!"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s $BASE/attendance/status -H "Authorization: Bearer $TOKEN"
curl -s $BASE/hostels/me/geofence -H "Authorization: Bearer $TOKEN"
```

`POST /attendance/verify` needs a fresh fix (≤90 s old), a point inside
`distance + accuracy <= permitted_radius_m`, an enrolled face, and an open
window — see `docs/API.md` §verify.

## Layout

```
app/
  main.py            FastAPI app, router mounting, error handlers
  core/              config, clock, security (JWT/bcrypt), errors, rate limit
  db/                engine, session, declarative base
  models/            users, students, hostels, face_enrollments,
                     attendance_records, attendance_attempts, audit_logs,
                     revoked_tokens
  schemas/           request/response models per docs/API.md
  api/               auth, students, hostels, face_enrollment, attendance,
                     admin, health, config, deps
  services/          geofence, similarity, template_crypto, audit,
                     attendance pipeline, students
migrations/          Alembic (0001_initial)
scripts/seed.py      idempotent dev seed
tests/               pytest suite (8 modules, real Postgres)
Dockerfile           python:3.12-slim, non-root
docker-compose.yml   db (16-alpine, healthcheck) + api
```

## Notes

- Every verify attempt (accepted or rejected) is logged to
  `attendance_attempts` with distance/accuracy only — never raw coordinates.
- Face templates are L2-normalized, Fernet-encrypted at rest, and never logged.
- Rate limits: verify 10/min/student, login 5/min per (ip, student_id) →
  429 `rate_limited`.
