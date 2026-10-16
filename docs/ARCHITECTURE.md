# HostelPass — Architecture

Smart hostel attendance: **GPS geofence + on-device face recognition + on-device
passive anti-spoofing**, with the **backend as the single authoritative decision maker**.

## Repository layout

```
docs/            architecture, API contract, security notes, deployment, model provenance
design_assets/   Stitch source-of-truth exports: logo, avatar photos, bundled TFLite models
app/             Flutter Android application (feature-based, Riverpod, go_router)
server/          FastAPI + PostgreSQL backend (Docker Compose, Alembic migrations)
```

## Trust model (core principle)

A client boolean is never trusted. `POST /attendance/verify` carries *evidence*
(location fix + face embedding + liveness score), and the server re-derives
every decision: window, freshness, accuracy, geofence (server-stored coordinates),
identity similarity (server-computed cosine against the stored template), liveness
policy, and duplicate prevention (DB unique constraint). A tampered APK can at
worst submit forged *evidence*; see `SECURITY.md` for the honest limits of that
guarantee and the mitigations (attestation hook, rate limiting, audit trail,
anomaly review, warden approval path).

### Why on-device face recognition

The home server (Ryzen 3, 4 GB RAM, no GPU) cannot run a face-recognition stack
at attendance-window scale, and uploading raw face frames maximizes biometric
exposure. Instead:

- **Device** runs ML Kit face detection (quality gating) + bundled TFLite
  MobileFaceNet (128-d embedding) + bundled TFLite passive anti-spoof model
  (256×256, documented scoring rule).
- Device sends a ~0.5 KB embedding + liveness score, never raw frames.
- **Server** stores the enrolled template AES-GCM encrypted, recomputes cosine
  similarity, applies the threshold, and decides.

Both TFLite models are bundled in-app (no runtime download), permissive licenses
(MIT / Apache-2.0), verified locally — see `MODEL_PROVENANCE.md`.

### Liveness, honestly

Passive PAD uses a real bundled model (Deep-Tree anti-spoof, MIT) with its
published decision rule (`Σ|pred|·mask ≤ 0.2 ⇒ live`). It is a genuine model, not
a hardcoded success or a blink heuristic. It has **not** been calibrated against a
real attack dataset in this repo; until a calibration report exists, hostel policy
can set `require_liveness=false`, in which case attendance is recorded as
`pending_review` (warden confirms) — never auto-`verified`. The app never claims
spoofing is impossible.

## Attendance flow (client)

```
Home ── Mark Attendance
   ──► [Step 1] Location: permission → GPS fix (accuracy gate) → local pre-check
        (haversine vs server-provided geofence; outside ⇒ failure screen, camera locked)
   ──► [Step 2] Face: camera permission → ML Kit detection gates (single face,
        eyes open, size, lighting) → capture → anti-spoof score → embedding
   ──► POST /attendance/verify (evidence)
   ──► server response is the ONLY success source ⇒ success / failure screen
```
The local geofence check is a UX courtesy only; the server re-checks everything.
A local success screen is never shown before the server confirms.

## Backend

- FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 16 (Compose, health checks,
  persistent volume, no Redis/broker — single API container keeps the 4 GB box sane).
- JWT (HS256, 30 min) access tokens, jti denylist for logout, bcrypt passwords.
- Rate limiting in-process (documented single-process limitation).
- Biometric templates encrypted at rest (Fernet/AES-GCM via `cryptography`);
  embeddings and raw coordinates of attempts are never logged.
- Attendance rows are immutable for students; corrections are admin-only with
  audit logs.

### Roles and account provisioning

Three roles live in `users.role`: `admin`, `warden`, `student`. Authorization
runs server-side on every request: the JWT's `sub` identifies the row, and the
**database** supplies the role — a token carrying `role: admin` for a student
account grants nothing. Wardens are further limited to the hostels listed in
`warden_hostels`; admins are implicitly global.

Provisioning is deliberately one-directional. There is no public registration
endpoint (the routes do not exist), and the first administrator is created by
`scripts/create_admin.py` over shell access on the server. Wardens come from
`POST /admin/wardens`. Students come from `POST /warden/students`, which writes
an unusable placeholder password hash — so `students.enrollment_status` must
reach `active` through `created → details_verified → face_enrolled →
account_provisioned → active` before the account can authenticate at all.

Face enrollment is a **warden action** (`PUT /warden/students/{id}/face-enrollment`);
the student-facing equivalents return `403`. The rationale: an enrollment that
the account holder performs on their own device is self-attestation, and the
template is only as trustworthy as the person who captured it.

Password setting happens exclusively by redeeming a single-use,
time-limited activation token (`POST /auth/activate`). Tokens are generated
with `secrets.token_urlsafe(32)`, stored SHA-256-hashed, bound to one account,
and revoked when superseded. Neither the warden nor the server logs ever see a
student password. If no email transport is configured, the console reports the
link as *issued* rather than *sent* — see `DEPLOYMENT.md` §1a.

Google Sign-In, when configured, verifies the ID token in-process (JWKS fetch,
RS256 signature, issuer, audience, expiry, `email_verified`, exact
`ceconline.edu` address) and signs in existing accounts only: it never creates
a user and never attaches a Google identity to a local one.

## Geofence math

Haversine (R = 6 371 000 m). Conservative policy: the *whole* uncertainty circle
must fit inside the permitted radius:
`inside ⇔ distance + accuracy_m ≤ permitted_radius_m`.
Readings with `accuracy_m > max_location_accuracy_m` or older than 90 s are
rejected as unusable/stale — the UI asks for a fresh fix. Extensible to polygon
boundaries later: the policy object is the single decision point.

## Schema (summary)

`users(role ∈ admin|warden|student, username UNIQUE, bcrypt password) ·
students(roll UNIQUE, email UNIQUE @ceconline.edu, enrollment_status, hostel_id, room) ·
warden_hostels(user_id + hostel_id UNIQUE — warden scope) ·
account_activation_tokens(token_hash SHA-256 UNIQUE, user_id, expires_at, used_at, created_by) ·
hostels(geofence+policy) ·
face_enrollments(student_id UNIQUE, encrypted template) ·
attendance_records(student_id + attendance_date UNIQUE, reference, outcome) ·
attendance_attempts(rejected/accepted evidence, no raw coords) · audit_logs ·
revoked_tokens`

## Known v1 gaps (documented, not hidden)

- Outpass / late-pass module, gate QR pass, push notifications: not implemented;
  UI routes these to honest "not available yet" states instead of fake screens.
- Face recognition thresholds (`face_match_threshold` default 0.75) must be
  calibrated on real genuine/impostor samples before real deployment
  (observed on smoke tests: genuine ≈ 0.99, similar-demographic impostor ≈ 0.65
  on naive crops — margin exists but is crop-quality dependent).
- Play Integrity attestation is wired as an optional field, not enforced.
