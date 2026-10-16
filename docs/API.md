# HostelPass API Contract (v1)

Base path: `/api/v1`. All request/response bodies are JSON (UTF-8).
All timestamps are RFC 3339 UTC (e.g. `2026-10-13T15:12:19Z`) unless stated otherwise.
Authentication: `Authorization: Bearer <access_token>` (JWT HS256).

## Error envelope

Every non-2xx response uses:

```json
{ "error": { "code": "machine_code", "message": "Human readable.", "details": {} } }
```

Machine codes used across the API:
`invalid_credentials`, `invalid_payload`, `token_invalid`, `token_revoked`,
`account_inactive`, `account_not_activated`, `account_suspended`,
`hostel_not_configured`, `face_not_enrolled`,
`location_stale`, `location_unusable`, `outside_geofence`, `face_mismatch`,
`liveness_failed`, `duplicate_attendance`, `attendance_window_closed`,
`rate_limited`, `not_found`, `forbidden`, `conflict`, `internal_error`,
`google_signin_not_configured`, `activation_token_invalid`,
`activation_not_permitted`, `already_active`, `not_provisioned`,
`not_ready_to_provision`, `invalid_transition`.

HTTP status mapping: 400 payload/validation · 401 auth · 403 policy/authorization ·
404 not found · 409 duplicate/conflict · 422 semantically unusable input ·
429 rate limited · 500 internal.

## Roles and authorization

| Role | Who creates it | Can do |
|------|----------------|--------|
| `admin` | one-time server CLI (`scripts/create_admin.py`) | everything below + app/hostel/policy config, warden accounts, global audit |
| `warden` | `POST /admin/wardens` (admin only) | manage students **in granted hostels only**, face enrollment, activation, view own-hostel attendance |
| `student` | `POST /warden/students` (warden) + activation | sign in, read own data, mark own attendance |

Enforced **server-side on every request** from the verified JWT's `sub` claim —
the `role` claim in the token is informational only; the authoritative role is
read from the `users` row. Hiding a button in the app is not authorization.

Hostel scoping: `warden_hostels` grants. Admins are implicitly global. A warden
with no grants sees an empty roster (not everything). A warden filtering by a
hostel they do not hold gets `403 forbidden`; a student outside their scope gets
`404 not_found` (anti-enumeration).

## Account lifecycle

```
CREATED → DETAILS_VERIFIED → FACE_ENROLLED → ACCOUNT_PROVISIONED → ACTIVE
                (any state except CREATED may go to SUSPENDED, and back)
```

`students.enrollment_status` holds one of
`created | details_verified | face_enrolled | account_provisioned | active | suspended`.
A student may only sign in when the status is `active` **and** `users.account_status`
is `active`. Accounts created by a warden carry an unusable placeholder password
hash until the activation link is redeemed — nobody, including the warden, ever
sets or sees a student password.

**Email rule.** `students.email` must be a college address: the hostname after the
final `@` must equal `ceconline.edu` *exactly*. No substring matching —
`a@xceconline.edu`, `a@sub.ceconline.edu`, `a@ceconline.edu.example.com`,
`a@ceconline.com` are all rejected. Emails are trimmed + lowercased before the
unique check.

## Public endpoints

### GET /api/v1/health
No auth. Used by Docker health checks and app connectivity diagnostics.
`200 {"status":"ok","version":"1.0.0","database":"up"}`

### GET /api/v1/config/public
No auth. Feature flags + minimal branding. The curfew fields are optional
institution-level display defaults for the sign-in banner (24h `HH:MM`); each
hostel's DB window is authoritative for verification. Null => app fallback.
```json
{
  "google_sso_enabled": false, "app_min_version": "1.0.0",
  "support_extension": "#442",
  "curfew_window_start": "20:30", "curfew_window_end": "22:30",
  "curfew_timezone": "Asia/Kolkata"
}
```

### POST /api/v1/auth/login
No auth. Accepts a college email **or** a legacy roll number / staff username:
```json
{ "email": "cs-2022-084@ceconline.edu", "password": "..." }
{ "student_id": "CS-2022-084", "password": "..." }
```
`200`:
```json
{
  "access_token": "<jwt>", "token_type": "bearer", "expires_in": 1800,
  "student": { <StudentPublic> }
}
```
Order of checks: password verified first, then lifecycle — so a placeholder-password
account gets the same generic `401 invalid_credentials` as an unknown address
(no account enumeration). Only after a valid password do these surface:
`403 account_suspended`, `403 account_not_activated`
("Your HostelPass account has not been activated. Please contact your hostel warden."),
`403 account_inactive`. Rate limited to `RATE_LIMIT_LOGIN_PER_MINUTE`
(default 5) per **(IP, identifier)** pair. Honest caveat: because the key is
the pair, an attacker who rotates source addresses resets the counter — this
dampens accidental lockouts and naive brute force, it is not an account lockout.

### POST /api/v1/auth/google
No auth. `{ "id_token": "<google id token>" }`. Same response shape as login.
The backend independently verifies the token — signature against Google's JWKS,
`iss` ∈ {`accounts.google.com`, `https://accounts.google.com`}, `aud` ==
`google_oauth_client_id`, `exp`, `email_verified == true` and an exact
`ceconline.edu` email. **Existing accounts only**: it never creates an account
and never links a Google identity to a local one; an unprovisioned Google user
gets `403 account_not_activated` and a signed-in-but-suspended user is refused.
`503 google_signin_not_configured` when `GOOGLE_OAUTH_CLIENT_ID` is unset.
A malformed/expired/mis-audience token gets the same generic
`401 invalid_credentials`.

### POST /api/v1/auth/activate
No auth. `{ "token": "<activation token>", "password": "<new password>" }`.
Redeems the single-use, time-limited link issued by a warden
(`POST /warden/students/{id}/activate`) and sets the student's own password.
The token — not the body — determines which account is activated. Tokens are
`secrets.token_urlsafe(32)`, stored **hashed** (SHA-256), bound to the account,
single-use, TTL `activation_token_ttl_seconds`; issuing a new one revokes any
unused predecessor. Success → `200` login response. Failure:
`400 activation_token_invalid` (unknown / used / expired / wrong account),
`409 activation_not_permitted`, `409 already_active`, `403 not_provisioned`.

### POST /api/v1/auth/refresh  (auth)
Sliding-session refresh of a valid, unrevoked token. Returns a new token.

### POST /api/v1/auth/logout  (auth)
Revokes the presented token (jti denylist). `204`.

### GET /api/v1/auth/me  (auth)
The caller's own `<StudentPublic>` (includes `role` and `enrollment_status`).

## Authenticated: student

### GET /auth/me, GET /students/me → `<StudentPublic>`
```json
{
  "id": "uuid", "student_id": "CS-2022-084", "name": "Rohan Sharma",
  "email": "cs-2022-084@ceconline.edu", "enrollment_status": "active",
  "department": "Computer Science & Engg", "cohort": "3rd Year (B.Tech 22–26)",
  "role": "student", "account_status": "active",
  "hostel": { "id": "uuid", "name": "Ganga Boys Hostel", "block": "B", "room": "314" }
}
```

### GET /hostels/me/geofence → `<GeofencePublic>`
Server is the single source of truth for coordinates, radius and policy.
```json
{
  "hostel_id": "uuid", "name": "Ganga Boys Hostel", "block": "B",
  "anchor_label": "Ganga Block B",
  "latitude": 12.9716, "longitude": 79.1585,
  "permitted_radius_m": 120.0,
  "max_location_accuracy_m": 50.0,
  "boundary_policy": "conservative",
  "timezone": "Asia/Kolkata",
  "window_start": "20:30", "window_end": "22:30",
  "require_liveness": true,
  "face_match_threshold": 0.75,
  "warden_name": "Dr. K. Raman", "warden_extension": "204"
}
```
`boundary_policy: conservative` ⇒ accepted iff `haversine(pos, anchor) + accuracy_m <= permitted_radius_m`.
Client coordinates/radius can never widen this rule.

### GET /face-enrollment → `{ "enrolled": bool, "model_version": "...", "updated_at": "..." }`
Read-only status of the caller's own template. Students may always read it.

### PUT /face-enrollment — **students: 403 forbidden**
Face enrollment is *warden-initiated*. A student calling this gets
`403 forbidden` ("Face enrollment is performed by your hostel warden…").
There is deliberately no self-enrollment path: enrolling your own face from
your own phone defeats the purpose of an independent witness.
Wardens enroll on behalf of a student via `PUT /warden/students/{id}/face-enrollment`.

### DELETE /face-enrollment — **students: 403 forbidden**
Same rule; deletion is an authorized warden/admin action and is audit-logged.

### GET /attendance/status?date=YYYY-MM-DD
Defaults to today in the hostel timezone.
```json
{
  "date": "2026-10-13",
  "marked": true, "outcome": "verified",
  "record": { <AttendancePublic> },
  "window": { "open": true, "opens_at": "20:30", "closes_at": "22:30",
              "minutes_remaining": 38, "timezone": "Asia/Kolkata" },
  "can_mark": true,
  "face_enrolled": true
}
```

### GET /attendance/summary?month=YYYY-MM
```json
{ "month": "2026-10", "present": 26, "absent": 1, "outpass": 0,
  "rate_percent": 93.1, "days_accounted": 27, "total_days": 29,
  "pass_threshold_percent": 85, "eligibility_safe": true }
```
`absent` = elapsed attendance days (window fully past, today included only after
window close) with no record and no approved outpass. Outpass module is not in v1 ⇒ `outpass` is always 0.

### GET /attendance/history?month=YYYY-MM&status=present|pending|absent&page=1&page_size=20
```json
{ "items": [ <AttendancePublic> ], "page": 1, "page_size": 20,
  "total_pages": 3, "has_more": true }
```
`<AttendancePublic>`:
```json
{
  "id": "uuid", "reference": "HP-2026-1013-0842", "date": "2026-10-13",
  "recorded_at": "2026-10-13T15:12:19Z", "recorded_at_local": "2026-10-13T20:42:19+05:30",
  "status": "present", "outcome": "verified",
  "distance_m": 24.0, "accuracy_m": 4.0, "face_similarity": 0.83,
  "liveness_method": "antispoof_model_v1", "liveness_score": 0.01,
  "gate": null
}
```
`status` ∈ `present | pending | absent`. `outcome` ∈ `verified | pending_review`.
Absent days are synthesized (no id) with `{"status":"absent","reason":"curfew_window_missed"}`.

### POST /attendance/verify  (auth) — the authoritative endpoint
```json
{
  "location": { "latitude": 12.97162, "longitude": 79.15851,
                "accuracy_m": 4.0, "timestamp_utc": "2026-10-13T15:12:00Z" },
  "face": {
    "embedding": [0.01, ...], "embedding_dim": 128,
    "model_version": "mobilefacenet_tflite_128_v1",
    "liveness": { "method": "antispoof_model_v1", "score": 0.012, "passed": true },
    "captured_at_utc": "2026-10-13T15:12:05Z"
  },
  "device": { "app_version": "1.0.0", "platform": "android",
              "device_model": "OnePlus 11R", "integrity_verdict": null }
}
```
Enforced server-side, in order:
1. Authenticated, active account, assigned hostel with geofence configured.
2. Attendance window open (hostel local timezone) → else `attendance_window_closed`.
3. Location freshness ≤ 90 s vs server receipt time → else `location_stale`.
4. `0 < accuracy_m <= max_location_accuracy_m` → else `location_unusable`.
5. Geofence (server coordinates, conservative policy) → else `outside_geofence`
   (details include `distance_m`, `permitted_radius_m`).
6. Enrollment exists → else `face_not_enrolled`.
7. `embedding_dim` matches stored dim, all finite, cosine similarity ≥ hostel
   `face_match_threshold` → else `face_mismatch` (details include `similarity`).
8. Liveness: hostel `require_liveness` ⇒ `liveness.passed == true`,
   `method == "antispoof_model_v1"`, `0 <= score <= 0.2` → else `liveness_failed`.
   If `require_liveness == false`, record is created as `outcome: "pending_review"`
   (status `pending`) instead of `verified` — never silently "verified".
9. Duplicate check + `UNIQUE(student_id, attendance_date)` insert in one
   transaction → else `duplicate_attendance` (409), incl. concurrent races.
10. Success `200` with `<AttendancePublic>`; attempt + audit rows written.
Every rejected attempt is persisted in `attendance_attempts` (no raw coordinates).

Rate limit: 10 verify calls / student / minute.

## Authenticated: warden / admin (role check)

### Warden — `/api/v1/warden/*` (role `warden` or `admin`)

Scoped to the caller's `warden_hostels` grants on every call.

| Endpoint | Notes |
|----------|-------|
| `GET /warden/dashboard` | counts by enrollment status, hostel summary, recent enrollment activity, today's attendance |
| `GET /warden/hostels` | granted hostels with geofence + window |
| `GET /warden/students` | `?q=&hostel_id=&room=&enrollment_status=&status=&page=&page_size=` — `q` matches name, email, student id, room |
| `POST /warden/students` | create record — body `{ student_id, name, email, hostel_id, room?, department?, cohort? }`. **No password field.** `409 conflict` on duplicate id or email, `400 invalid_payload` on a non-`ceconline.edu` email |
| `GET /warden/students/{ref}` | `ref` = UUID or roll → `<EnrollmentStatusPublic>` |
| `PATCH /warden/students/{ref}` | `{ name?, email?, room?, hostel_id?, department?, cohort? }` — cannot change role, account_status or enrollment_status |
| `POST /warden/students/{ref}/verify-details` | `created → details_verified` |
| `PUT /warden/students/{ref}/face-enrollment` | `{ embedding, embedding_dim, model_version, quality? }` — server validates dims + finiteness, L2-renormalizes, encrypts at rest, never logs |
| `DELETE /warden/students/{ref}/face-enrollment` | authorized biometric deletion, audit-logged, rolls status back recoverably |
| `POST /warden/students/{ref}/activate` | `face_enrolled → account_provisioned` + issues a single-use activation token |
| `POST /warden/students/{ref}/resend-activation` | revokes the unused predecessor and issues a fresh token |
| `POST /warden/students/{ref}/suspend` | → `suspended` (login refused) |
| `POST /warden/students/{ref}/unsuspend` | restores the prior active/pending state |
| `GET /warden/attendance` | own-hostel roster / records |

`<EnrollmentStatusPublic>` — every field derived from real rows:
```json
{
  "student_id": "uuid", "roll": "CS-2022-117", "name": "Ishaan Verma",
  "email": "cs-2022-117@ceconline.edu",
  "enrollment_status": "details_verified", "account_status": "inactive",
  "details_complete": true, "face_enrolled": false,
  "password_set": false, "activation_pending": false,
  "hostel_id": "uuid", "room": "316"
}
```
`face_enrolled` reflects an actual `face_enrollments` row — a client claiming
`face_enrolled: true` changes nothing.

`<ActivationIssue>` (activate / resend-activation):
```json
{ "enrollment_status": "account_provisioned", "activation_pending": true,
  "delivered": true, "email_status": "sent", "email_detail": null,
  "expires_at": "2026-10-20T15:00:00Z",
  "activation_token": "<43-char single-use key>",
  "setup_url": "hostelpass://activate?token=<key>" }
```
`activation_token` is the freshly issued key, returned **only** by these two
issuance endpoints, **only** to the authorized issuer, so the warden can copy it
and send it to the student (WhatsApp workflow); `setup_url` wraps it as a deep
link. Only the SHA-256 hash is stored, and the plaintext never appears in logs
or audit rows. Set `ALLOW_INLINE_ACTIVATION_TOKEN=false` to withhold both
(fields become `null`, email-only delivery).

`email_status` is the **real** outcome of the activation-email attempt for this
request — an activation record alone never claims a send:

| `email_status` | meaning | `delivered` |
|---|---|---|
| `sent` | an SMTP provider accepted the message (`EMAIL_MODE=smtp`) | `true` |
| `logged` | dev only: rendered to the server's local outbox (`EMAIL_MODE=log`); **no** real email | `false` |
| `failed` | attempted but failed; `email_detail` holds a token-free reason | `false` |
| `not_configured` | `EMAIL_MODE=off`; no delivery attempted | `false` |

`delivered` is `true` **only** when `email_status == "sent"`. See
`docs/DEPLOYMENT.md` for `SMTP_*` / `APP_BASE_URL` configuration.

### Admin — `/api/v1/admin/*` (role `admin`)

- `GET/POST /admin/students`, `PATCH /admin/students/{id}`,
  `POST /admin/students/{id}/suspend`, `POST /admin/students/{id}/unsuspend`
  — same enrollment service as `/warden`, but global (not hostel-scoped)

  `GET /admin/students` supports filters the Admin Console roster uses:
  `?q=` (substring over roll / name / email), `?hostel_id=`,
  `?enrollment_status=`, `?account_status=`, plus `?page=&page_size=`.
- `DELETE /admin/students/{id}/face-enrollment` — audit-logged biometric deletion
- `GET /admin/stats` — live operational counts for the console dashboard:
  `{ "hostels", "rooms", "wardens": {total, active, inactive},
  "students": {total, active, pending_enrollment, suspended, by_status} }`.
  Every figure is a server-side aggregate; the console never invents a number.
- `GET/POST /admin/wardens`, `PATCH/DELETE /admin/wardens/{username}` —
  provision and manage warden accounts. There is **no public registration
  endpoint of any kind**; wardens can only be created by an admin here, and the
  first admin only by the one-time server CLI.

  | Endpoint | Body / behaviour |
  |----------|------------------|
  | `GET /admin/wardens` | paged `<WardenListResponse>` with each warden's hostel grants. Filters: `?q=` (username substring), `?account_status=active\|inactive` |
  | `POST /admin/wardens` | `{ username, password, hostel_ids: [uuid] }` — `409 conflict` on a taken username, `404` for an unknown hostel. The admin sets the *staff* password here (students never get one from staff) |
  | `PATCH /admin/wardens/{username}` | `{ password?, hostel_ids?, account_status? }` — changing grants re-scopes the warden immediately. **No `role` field: roles are never client-writable**, so a warden can never self-promote |
  | `DELETE /admin/wardens/{username}` | removes the staff account (audit-logged) |

  `<WardenPublic>`: `{ "id", "username", "role": "warden", "account_status",\n  "hostel_ids": [...], "hostel_names": [...], "created_at" }`
- `GET /admin/hostels` — all geofence configs. `GET /admin/hostels/{id}` — one.
- `POST /admin/hostels` — **create a hostel block.** Body: `{ name, block?,
  anchor_label?, latitude, longitude, permitted_radius_m,
  max_location_accuracy_m, timezone?, window_start?, window_end?,
  require_liveness?, face_match_threshold?, warden_name?, warden_extension? }`.
  `latitude`/`longitude`/`permitted_radius_m`/`max_location_accuracy_m` are
  **required** — the server refuses to create a hostel without a usable geofence,
  because an unusable anchor would silently deny attendance for every student in
  it. `window_*` are `HH:MM` (24h); `timezone` must be a real IANA name; a
  duplicate name+block is `409 conflict`. Action `hostel.create` is audited.
- `PUT /admin/hostels/{id}` — geofence & policy config only (unchanged).
- `GET/POST /admin/hostels/{id}/rooms`, `PATCH/DELETE /admin/rooms/{id}` —
  the room registry.

  | Endpoint | Body / behaviour |
  |----------|------------------|
  | `GET /admin/hostels/{id}/rooms` | paged `{ id, hostel_id, identifier, capacity, student_count, created_at, updated_at }`. `student_count` is live occupancy; `capacity` may be `null` (advisory only) |
  | `POST /admin/hostels/{id}/rooms` | `{ identifier, capacity? }` — identifier is trimmed; `409` if that identifier already exists **in this hostel** (case-insensitive). Same identifier in another hostel is fine |
  | `PATCH /admin/rooms/{id}` | `{ identifier?, capacity? }`. Renaming **moves current occupants** to the new identifier in the same transaction (`students_moved` is audited), so a rename never orphans a roster entry |
  | `DELETE /admin/rooms/{id}` | `204`, but `409 conflict` while students are still assigned — delete can never strand a roster row |

  **Enforcement:** when a hostel has rooms registered, `POST /admin/students`,
  `POST /warden/students` and both `PATCH` paths reject a `room` that is not one
  of the registered identifiers (`400 invalid_payload`, case-insensitive,
  trimmed). A hostel with **no** registered rooms keeps accepting free-text
  rooms, so pre-existing rosters are never retroactively broken — only a change
  to `room`/`hostel_id` re-triggers the check. Audit actions: `room.create`,
  `room.update`, `room.delete`.
- `GET /admin/attendance?student_id=&date=&status=` — includes `pending_review`
- `POST /admin/attendance/{id}/approve`, `POST /admin/attendance/{id}/reject` — pending workflow
- `POST /admin/attendance/{id}/correction` `{ "new_status": "...", "reason": "..." }` — audit-logged
- `GET /admin/audit-logs?page=`

All admin and warden mutations write `audit_logs` rows recording the acting
staff member **and** the affected student. Audit rows never contain passwords,
raw activation tokens or biometric data.

Students can never create records, enroll faces, change role/hostel/email,
modify attendance, or read another student's data — every one of those paths
returns `401`/`403`/`404` from the server regardless of what the client sends.
