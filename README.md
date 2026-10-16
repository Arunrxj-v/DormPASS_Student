# HostelPass

Evening curfew attendance for college hostels: the backend — not the phone —
decides whether a check-in counts. The app captures evidence (GPS fix + face
embedding + passive liveness score); the server enforces the curfew window, the
geofence, face match, and duplicate prevention, and returns the only record the
student ever sees.

**Stack:** Flutter (Android) · FastAPI · PostgreSQL · Docker Compose, designed
to run on a home server (Ryzen 3 / 4 GB RAM / no GPU) and reachable in dev over
Tailscale.

## Repository layout

| Path | What it is |
| --- | --- |
| `app/` | Flutter Android app (package `hostelpass`) |
| `server/` | FastAPI backend + PostgreSQL compose stack + pytest suite |
| `docs/API.md` | Binding API contract (endpoints, schemas, error envelope) |
| `docs/ARCHITECTURE.md` | System design, trust boundaries, data flow |
| `docs/SECURITY.md` | Guarantees, test coverage, and honest limits |
| `docs/MODEL_PROVENANCE.md` | Bundled face models: sources, licenses, validation |
| `docs/DEPLOYMENT.md` | Running the stack at home, backups, HTTPS/Tailscale |
| `design_assets/` | Exports from the Google Stitch source designs (do not edit) |

### Sibling applications

This repository sits inside a workspace with two further front-ends. All three
talk to the **same** backend and database in `server/` — there is no second
backend, no second database, and no business rule enforced only in a client.

| Path | What it is |
| --- | --- |
| `../DormPASS_Student/` | This repository — the student app |
| `../DormPASS_Warden/app/` | **HostelPass Warden** — standalone Flutter app for wardens (roster, face enrollment, activation) |
| `../DormPASS_Admin/` | **HostelPass Admin Console** — React + TypeScript web app (wardens, hostels, rooms, audit) |

The account hierarchy is provisioned only downwards, and each arrow is a real
server-side authorization check:

```
SECURE INITIAL ADMIN      python -m app.cli create-admin   (server shell only)
        |
        v
ADMIN CONSOLE             POST /admin/wardens              (role admin)
        |
        v
WARDEN APP                POST /warden/students, face enrollment, activate
        |
        v
STUDENT APP               POST /auth/activate, then /auth/login
```

## How a check-in works

1. **Sign in** — `POST /api/v1/auth/login`; the JWT is stored in Android
   Keystore-backed secure storage. Identity comes from the token, never from
   anything the body claims.
2. **Location step** — the app gets a fresh GPS fix and runs a local Haversine
   pre-check (`distance + accuracy ≤ radius`) purely for UX. It then sends the
   fix to `POST /api/v1/attendance/verify`.
3. **Face step** — on-device: ML Kit finds the face, a bundled anti-spoofing
   TFLite model scores the tight crop for liveness, and MobileFaceNet produces a
   128-d embedding. Only the embedding, the liveness score, and metadata go to
   the server — no photos leave the phone and none are stored.
4. **Server decision** — the backend independently re-checks window, freshness,
   accuracy, geofence (server-stored coordinates), face similarity against the
   encrypted stored template, liveness policy, and same-day duplicates (a DB
   unique constraint included). The response is the single source of truth:
   `verified`, `pending_review`, or a typed failure like `outside_geofence` or
   `duplicate_attendance`.

Local checks in the app are conveniences; they can be bypassed, and the server
assumes they are.

## Development

Backend (Python 3.13, Postgres on `127.0.0.1:5433`):

```bash
cd server
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
docker compose up -d db
alembic upgrade head
uvicorn app.main:app --reload --port 8000
pytest            # full suite, including a concurrent-duplicate test
python scripts/e2e_activation.py   # live warden→enroll→activate lifecycle over HTTP
```

Or the whole stack in containers: `docker compose up --build` (see
`docs/DEPLOYMENT.md` for `.env` setup — never commit secrets).

App (Android):

```bash
cd app
flutter pub get
flutter test                      # unit + widget tests, no device needed
flutter run --dart-define=API_BASE_URL=http://<tailscale-or-lan-ip>:8000
```

Android 9+ refuses cleartext HTTP to arbitrary hosts. The emulator's host alias
(`10.0.2.2`) is allow-listed in
`android/app/src/main/res/xml/network_security_config.xml`; a Tailscale or LAN
address passed via `API_BASE_URL` must be added to that same file (exact host,
no wildcards — deliberate). See `docs/DEPLOYMENT.md` §3.

Android refuses plain `http://` to arbitrary hosts (API 28+). The emulator's
`10.0.2.2` and loopback are allow-listed in
`android/app/src/main/res/xml/network_security_config.xml`; a Tailscale or LAN
address passed via `API_BASE_URL` must be added there too — one `<domain>` line,
exact host, no wildcards. For anything beyond a trusted network, terminate TLS
at a reverse proxy and build with `https://`.

Seed logins (dev only): students `CS-2022-084` / `student123!`,
admin `admin` / `AdminPass123!`, warden `warden` / `WardenPass123!`.
Two further seeded students (`CS-2022-117` at *awaiting face enrollment*,
`CS-2022-132` at *details incomplete*) have no password at all — that is the
point; they can only sign in after walking the warden flow below.

## Getting students onto the system

There is **no self-registration** anywhere — not in the app, not over HTTP.
Accounts are provisioned in one direction:

```
admin creates warden (or CLI creates the first admin)
        │
        ▼
warden creates student record  ──►  verifies details
        │
        ▼
warden enrolls the student's face (front camera, warden holding the phone)
        │
        ▼
warden issues a single-use activation link  ──►  student redeems it,
                                                  sets their own password
        │
        ▼
ACTIVE — the student can now sign in and mark attendance
```

Nothing moves forward on the client's say-so. `students.enrollment_status`
lives in the database, and every gate (sign-in, face check, attendance) reads
it there. A student who edits the app to claim `face_enrolled: true` gets
`face_not_enrolled` from the server anyway.

Wardens never choose or see a student password — the placeholder hash written
at creation is unusable until the student redeems their own link.

## Honest limitations

- **Passive liveness is a real anti-spoofing model, not a gimmick — but it is
  not strong PAD.** It detects printed photos and flat screens well; it has not
  been certified (no ISO 30107-3 testing) and a high-quality replay may pass.
  When the hostel policy sets `require_liveness=false`, attendance is recorded
  as `pending_review`, never auto-verified.
- **GPS can be spoofed.** The server enforces a conservative uncertainty rule
  (`distance + accuracy ≤ radius`), but a rooted phone with a mock-location
  provider can fake coordinates. Treat location as a strong signal, not proof.
- **Face match threshold 0.75 is a starting point** (validated once against a
  small local smoke set: genuine 0.992 vs impostor 0.651). Calibrate per hostel
  before relying on it; the threshold is server-controlled and can be tightened.
- **Modules not implemented** — outpass requests, gate-entry QR, push
  notifications — show explicit "not available" states instead of pretending
  to work.
- **Email delivery is implemented via SMTP and is config-driven.**
  `EMAIL_MODE=off|log|smtp` decides: `off` reports `not_configured`, `log`
  (dev) renders `.eml` files to a local outbox, `smtp` delivers for real and
  reports the *observed* outcome — `delivered: true` only ever means the
  provider accepted the message, never merely that an activation record was
  created. No worker/queue: the send is synchronous with a short timeout, so
  the Warden App shows the actual result. Tokens are never logged or audited.
  See `docs/DEPLOYMENT.md` §1a.
- **Google Sign-In is implemented server-side but needs credentials.** The
  backend verifies the ID token itself (JWKS signature, issuer, audience,
  expiry, `email_verified`, exact `ceconline.edu` address) and signs in
  *existing* accounts only — no account is ever created or linked. Without
  `GOOGLE_OAUTH_CLIENT_ID` and the Android SHA-1 configuration it returns
  `503 google_signin_not_configured` and the app says so rather than showing a
  broken button. End-to-end behaviour with real Google credentials is
  **not tested here**; only the rejection paths are (with an injected verifier).
- **The warden face-enrollment flow enrolls whoever is in front of the
  camera.** The screen shows a persistent identity banner and an explicit
  warning, but software cannot verify that the person is the student on file.
  This is a procedural control, not a technical one.

## Security posture

- No secrets in the repo; configuration comes from `.env` (git-ignored).
  `JWT_SECRET` and `FACE_TEMPLATE_KEY` have documented development fallbacks —
  both must be set for anything beyond local use.
- Three roles (`admin` / `warden` / `student`) checked server-side on every
  request from the database row, not the JWT's `role` claim. Wardens are
  further scoped to `warden_hostels` grants; admins are global.
- Facial embeddings are Fernet-encrypted at rest and deletable
  (`DELETE /api/v1/warden/students/{id}/face-enrollment`, audit-logged).
  Students get `403` for both self-enroll and self-delete.
- Raw facial images are never stored or logged, on either side; audit rows
  carry no passwords, raw tokens or biometrics.
- Rate limits: login 5/min per (IP, identifier) pair, verify 10/min/student
  (in-memory; see deployment doc for the multi-process caveat, and note that
  the login key being a pair means rotating source addresses resets it).
- Identity always derives from the JWT's `sub`; a forged `role: admin` token is
  ignored in favour of the DB row (covered by a test).
- Registration routes do not exist — `POST /auth/register` and `POST /students`
  both 404. First admin comes from `server/scripts/create_admin.py` on the
  server itself.

## Documentation

- [docs/API.md](docs/API.md) — full request/response contract
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components and trust model
- [docs/SECURITY.md](docs/SECURITY.md) — what is guaranteed, what is tested, what is not
- [docs/MODEL_PROVENANCE.md](docs/MODEL_PROVENANCE.md) — model sources/licenses
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — running it for real
