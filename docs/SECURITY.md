# Security

What HostelPass actually guarantees, what it does not, and how each claim is
tested. Where a control is procedural rather than technical, it says so.

## Trust model in one paragraph

The phone is an untrusted evidence collector. `POST /attendance/verify` submits
*claims about the world* (a GPS fix, a face embedding, a liveness score) and the
server re-derives every decision itself: curfew window in the hostel's own
timezone, fix freshness, accuracy ceiling, geofence against coordinates it
stores, cosine similarity against a template it holds, liveness policy, and
same-day duplicate prevention enforced by a database unique constraint. A
tampered APK can at worst submit forged evidence — it cannot flip a result flag,
because no result flag is ever read from the request.

Identity comes from the JWT's `sub`, resolved against the database. The `role`
claim inside the token is decorative: a token minted with `"role": "admin"` for a
student account grants nothing, because the role used for authorization is read
from the `users` row.

## Guarantees

| Property | How it is enforced | Test |
| --- | --- | --- |
| No self-registration | The routes do not exist (`POST /auth/register`, `POST /students` → 404). Accounts are created only by a warden (`/warden/students`) or an admin (`/admin/wardens`) | `test_no_public_registration_route_exists` |
| Students cannot reach staff APIs | `require_staff` on every `/warden/*` route, role read from the DB | `test_student_cannot_create_student`, `test_student_cannot_enroll_any_face` |
| Warden hostel scoping | `warden_hostels` join table; ungranted hostel → 403, out-of-scope student → 404 | `test_warden_cannot_manage_hostel_outside_grant` |
| Students cannot edit their own role / read others | `role`, `account_status` and `enrollment_status` simply do not exist on the PATCH schema (never writable), the route itself requires a staff role, and `/students/me` returns only the caller | `test_student_cannot_change_own_role`, `test_students_me_only_returns_self` |
| Face enrollment is warden-performed | Student `PUT`/`DELETE /face-enrollment` return 403; only `/warden/students/{id}/face-enrollment` writes | `test_student_cannot_enroll_any_face` |
| Client booleans are ignored | Enrollment state lives in `students.enrollment_status` + a real `face_enrollments` row; a request body claiming otherwise is never read | `test_client_boolean_cannot_fake_enrollment` |
| Exact `@ceconline.edu` domain | Hostname after the final `@` must equal `ceconline.edu`, then normalize → lowercase → unique check | `test_email_domain_validation` (parametrized), `test_duplicate_email_rejected_and_normalized` |
| Activation tokens are unusable if leaked | `secrets.token_urlsafe(32)`, stored SHA-256, single-use, TTL-bound, revoked when superseded | `test_activation_token_flow_single_use_and_bounded`, `test_activation_token_expires`, `test_issuing_a_new_token_revokes_the_previous` |
| Passwords are never staff-visible | Warden creates an unusable placeholder bcrypt hash; the student sets their own by redeeming a token | `test_activation_requires_provisioning_first` |
| No account enumeration | Password verified before lifecycle checks, so an unknown address and a placeholder-password account return the identical 401 | `test_active_student_signs_in_with_valid_credentials` (paired negative cases) |
| Google Sign-In cannot create accounts | Server verifies the token itself (JWKS RS256, issuer, audience, expiry, `email_verified`, exact domain) and maps onto an *existing* row only | `test_google_never_creates_or_links`, `test_google_rejects_wrong_domain`, `test_google_rejects_invalid_token`, `test_google_rejects_unprovisioned_account` |
| Attendance rules unchanged by this feature | Geofence, duplicate and face-mismatch paths re-asserted after the provisioning work | `test_geofence_and_duplicate_protection_still_enforced`, `test_verify_rejects_mismatched_face`, `test_face_mismatch_does_not_create_record` |
| Sensitive actions are auditable | `audit_logs` rows carry acting staff **and** affected student; no passwords, raw tokens or biometrics | `test_audit_covers_sensitive_actions` |

Full run: `server/tests/test_security_enrollment.py` carries **40 tests**
covering the scenarios above (the email case is parametrized); the whole suite —
including every pre-existing attendance, geofence, admin and concurrency test —
is **107 passing**.

## Honest limits

### A warden can enroll the wrong person

The enrollment screen shows a persistent identity banner with the selected
student's name and roll, plus an explicit "you are enrolling *them*, not
yourself" warning — but software cannot verify that the person in front of the
camera is the student on file. **This is a procedural control.** Treat it like a
photo-ID check: the warden is the witness, and the audit row records who did it.

### GPS can be spoofed

A rooted phone with a mock-location provider can feed arbitrary coordinates.
The conservative rule (`distance + accuracy ≤ radius`) bounds how *sloppy* a fix
can be, not how *false* one is. Location is a strong signal, not proof.

### Liveness is real but not certified

Passive PAD uses a bundled anti-spoof model with its published decision rule —
not a blink heuristic. It has **not** been tested against ISO 30107-3; a
high-quality replay may pass. When `require_liveness=false`, attendance is
recorded as `pending_review`, never auto-`verified`.

### The face threshold is a starting point

`face_match_threshold` (default 0.75) was calibrated once against a small local
smoke set (genuine ≈ 0.99, similar-demographic impostor ≈ 0.65). Calibrate per
hostel before relying on it. The threshold is server-controlled.

### Google Sign-In is verified only on its rejection paths

The backend verifier is exercised with an injected fake because no real OAuth
client id exists in this environment. Signature/issuer/audience acceptance
against Google's live JWKS has been sanity-checked outside the test suite, but
an end-to-end sign-in with real credentials is **not tested here**. Without
`GOOGLE_OAUTH_CLIENT_ID` the endpoint returns `503` and the app disables the
button with a stated reason.

### Email delivery does not exist

Activation links are generated, hashed and consumed correctly, but nothing in
this repository sends mail. `delivered: true` means *the API recorded the
issuance*. The warden console says exactly that instead of claiming a send.
See `DEPLOYMENT.md` §1a.

### Secrets have development fallbacks

`JWT_SECRET` and `FACE_TEMPLATE_KEY` default to values printed in
`app/core/config.py` so a local run never bricks. Anyone who reads the source
can decrypt face templates signed with the fallback key. **Both must be set for
anything beyond local use** (`DEPLOYMENT.md` §1).

### Rate limits are per-process, and the login key is a pair

Login and verify limits are in-process sliding windows. The Compose stack runs
one uvicorn worker deliberately; scaling workers without moving the limiter to a
shared store multiplies the effective budget. The login limiter is keyed on
`(IP, identifier)`, so rotating source addresses resets it — useful against
accidental lockout and naive brute force, not a substitute for lockout policy.

### Not implemented at all

Outpass requests, gate-entry QR and push notifications do not exist. Their UI
shows explicit "not available" states rather than simulating a workflow.
