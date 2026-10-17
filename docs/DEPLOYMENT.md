# Deployment

HostelPass is designed to run on a small home server (tested shape: Ryzen 3,
4 GB RAM, no GPU) with PostgreSQL in Docker and the API either in Docker or as
a plain uvicorn process. Development access goes over Tailscale.

## 1. Configure secrets (required)

The server reads a `.env` file next to `server/docker-compose.yml`
(git-ignored — copy `server/.env.example` if present, or create it):

```bash
# server/.env
JWT_SECRET=<openssl rand -hex 32 output>
FACE_TEMPLATE_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
DATABASE_URL=postgresql+psycopg://hostelpass:<db-password>@db:5432/hostelpass
```

**Both `JWT_SECRET` and `FACE_TEMPLATE_KEY` have development fallbacks in
`app/core/config.py` so local runs never brick silently. In any real
deployment you must set both yourself** — the fallback Fernet key means anyone
who reads the source could decrypt stored face templates.

Also change the Postgres password in `docker-compose.yml` (or override via
environment) before exposing anything beyond your own devices.

### 1a. Account provisioning & activation email (required before real students can join)

The warden console issues a **single-use activation link** that the student
redeems to choose their own password. Whether that link ever reaches the
student depends entirely on configuration:

| Setting | Default | What it does |
|---------|---------|--------------|
| `ACTIVATION_TOKEN_TTL_SECONDS` | `604800` (7 days) | how long an unused link stays valid |
| `ALLOW_INLINE_ACTIVATION_TOKEN` | `true` | the issuance response (`POST …/activate`, `…/resend-activation`) carries the freshly issued plaintext key so the warden can copy it and send it to the student (WhatsApp workflow). Returned **only** at issuance, **only** to the authorized issuer; reads and logs never contain it (hash-only storage). Set `false` to withhold it (email-only delivery). |
| `EMAIL_MODE` | `off` | explicit delivery mode: `off` / `log` / `smtp` (see below). Behavior is never inferred from which variables happen to be set. |
| `SMTP_HOST`, `SMTP_PORT` | `""`, `587` | SMTP provider (e.g. `smtp.gmail.com`, `smtp.office365.com`, a local relay). Port `465` uses implicit TLS automatically. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | `""` | provider credentials — **environment only**, never source, never committed. |
| `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME` | `""`, `HostelPass` | envelope sender; must be accepted by your provider. |
| `SMTP_USE_TLS` | `true` | STARTTLS on non-465 ports. Set `false` only for a trusted local dev relay. |
| `EMAIL_TIMEOUT_SECONDS` | `10` | SMTP connect/send timeout — a slow relay fails honestly instead of hanging the request. |
| `APP_BASE_URL` | `http://localhost:8000` | **public** base URL of the deployment, no trailing slash. The activation link built INTO emails is `{APP_BASE_URL}/activate#token=…` — the token rides in the URL *fragment*, which browsers never transmit to the server, so clicking it can never put the token into an access log; the page at `/activate` hands the code to the Student app via its `hostelpass://` deep link. Students must never receive a localhost URL. |
| `EMAIL_LOG_DIR` | `var/outbox` | `EMAIL_MODE=log` only: where rendered `.eml` files are written inside the container. |

**The three modes:**

- **`off` (default)** — no delivery is attempted. The API responds
  `email_status: "not_configured"`, `delivered: false`. It does **not** claim
  an email was sent just because an activation record was created.
- **`log` (development)** — the fully rendered email (with the activation
  link) is written to `EMAIL_LOG_DIR` as an `.eml` file for local inspection;
  the API responds `email_status: "logged"`, `delivered: false`. The
  activation token is **never** written to application logs or audit rows —
  only the outbox *filename* is logged.
- **`smtp` (production / home server)** — the message is delivered through
  SMTP inline in the request (STARTTLS, or implicit TLS on 465). The API
  responds `email_status: "sent"` / `delivered: true` **only** when the
  provider accepted the message; provider or network errors come back as
  `email_status: "failed"` with a token-free reason in `email_detail`, and the
  warden can simply resend (the token was committed before the send, so a
  provider outage never invalidates the link).

**No background worker or queue is required** (and none is deployed): the send
happens synchronously with a short timeout inside the single API container,
which is what lets the Warden App report the *actual* outcome instead of an
optimistic "queued". The Compose file passes every `SMTP_*` / `APP_BASE_URL` /
`EMAIL_MODE` variable from the project `.env` into the `api` service — the
only service that ever sends email.

**Home-server example** (`server/.env` — never commit it):

```bash
EMAIL_MODE=smtp
SMTP_HOST=smtp.example.edu
SMTP_PORT=587
SMTP_USERNAME=hostelpass@example.edu
SMTP_PASSWORD=...            # from your provider; do not commit
SMTP_FROM_EMAIL=no-reply@example.edu
SMTP_FROM_NAME=HostelPass
SMTP_USE_TLS=true
APP_BASE_URL=https://hostelpass.your-domain.edu
```

**Resend example** (transactional email via Resend SMTP — same variable names,
no separate code path):

```bash
EMAIL_MODE=smtp
SMTP_HOST=smtp.resend.com
SMTP_PORT=465                # implicit TLS (== SMTP_SECURE=true): automatic on 465
SMTP_USERNAME=resend         # Resend's SMTP username is literally "resend"
SMTP_PASSWORD=               # your Resend API key (re_…) — untracked .env only,
                             #   or keep it as RESEND_API_KEY= in the same file:
                             #   compose falls back to it automatically
SMTP_FROM_EMAIL=noreply@your-verified-domain      # bare address, no display name
SMTP_FROM_NAME=DormPASS                          # display name is a separate var
SMTP_USE_TLS=true            # only consulted on non-465 ports
APP_BASE_URL=https://your-public-dormpass-url     # what goes INSIDE the email
```

Resend requirements before real delivery:

- The sending domain must be **verified in Resend** (add the DNS records
  Resend shows you). Unverified domains are rejected at send time; the API
  reports `email_status: "failed"` with the provider reason and the warden can
  resend — nothing is faked.
- `SMTP_PASSWORD` / `RESEND_API_KEY` live only in the untracked `.env`
  (gitignored) and are read by the `api` container only. They never reach the
  Flutter clients or any API response.
- From the running stack, the transport path can be pre-checked without any
  credentials: inside the container, connect to `smtp.resend.com:465` and read
  the `220 Resend SMTP Relay` banner (DNS → TCP → TLS).

**How to test that sending actually works:**

1. **Dev (no relay needed):** set `EMAIL_MODE=log`, `docker compose up -d api`,
   issue/resend an activation link from the Warden App, then
   `docker compose exec api ls var/outbox/` and inspect the `.eml`.
2. **Real SMTP:** set `EMAIL_MODE=smtp` + `SMTP_*` + `APP_BASE_URL`, restart,
   resend a link, and confirm `email_status: "sent"` in the response (and the
   message in the recipient's inbox). A local debugging relay works too:
   `python -m aiosmtpd -n -l 0.0.0.0:2525` on the host with
   `SMTP_HOST=host.docker.internal`, `SMTP_PORT=2525`, `SMTP_USE_TLS=false`.
3. Either way, check `docker compose logs api` — you will see a token-free
   status line, never the activation link itself.

**How the Warden App decides what to show** — it renders exactly what the API
reported for that request: "Activation email sent to …" (`sent`), "written to
the server's local outbox… no real email left the server" (`logged`),
"Email delivery FAILED: …" (`failed`, link still valid + Resend offered), or
"email delivery is not configured… (`EMAIL_MODE=off`)" (`not_configured`).
`delivered: true` is displayed only for an observed `sent`.

### 1b. First admin (one-time, server-side)

There is no public registration endpoint and no admin bootstrap HTTP route.
Create the first administrator by shell access on the server:

```bash
cd server
docker compose exec api python -m app.cli create-admin
# prompts for the password twice, with no echo
```

The script refuses to run twice unless `--force` is passed. Wardens are then
created from the app by that admin (`POST /admin/wardens`, or the Admin
Console).

The password is **never** accepted as a command-line argument (so it never
lands in shell history or `ps` output) and is **never printed.** For a
scripted bootstrap over `ssh`/`docker exec`, pipe it in — it is still never
echoed or logged:

```bash
printf '%s' "$NEW_ADMIN_PW" | docker compose exec -T api \
  python -m app.cli create-admin --username admin --password-stdin
```

`scripts/create_admin.py` still works and delegates to the same code. One
behaviour change from the original: a non-interactive run **refuses** instead of
printing a generated password, so a secret can never end up in a build log or
CI output. `--force` only ever resets the password of an *existing* admin
account — it will not create a second admin and will not promote a warden or
student.

### 1c. Google Sign-In (optional)

Google sign-in authenticates **existing** accounts only — it never creates or
links an account. Enabling it needs both halves:

1. Google Cloud Console → OAuth 2.0 credentials: a **Web** client id (the
   server's audience) and an **Android** client id with the app's SHA-1
   registered (`cd android && ./gradlew signingReport`), plus
   `default_web_client_id` in `android/app/res/values/strings.xml`.
2. Server: `GOOGLE_OAUTH_CLIENT_ID=<web client id>`.

Without (2), `POST /auth/google` returns `503 google_signin_not_configured`
and the app shows an honest "not configured" message instead of a broken
button. The verified email must also be an exact `@ceconline.edu` address.

## 2. Run the stack

```bash
cd server
docker compose up -d --build
docker compose exec api alembic upgrade head     # schema migrations
docker compose exec api python scripts/seed.py   # dev/demo seed data only
```

Compose resources are deliberately capped (`mem_limit: 512m`, `cpus: 1.0` for
the API) so a 4 GB box stays comfortable. Postgres binds to
`127.0.0.1:5433` only — it is never exposed to the network.

Health check: `curl http://<server>:8000/api/v1/health`.

### Verifying a deployment

`server/scripts/e2e_activation.py` walks the whole provisioning lifecycle over
real HTTP — warden sign-in, student creation, exact-domain email rejection,
details verification, face enrollment, activation-link issuance, redemption,
single-use replay rejection, suspend/restore, and the student-denied paths
(self-enroll, self-delete, `/warden/*`). It creates a uniquely-numbered
`E2E-<stamp>` student each run, so it is safe to repeat.

```bash
python scripts/e2e_activation.py                        # whatever BASE you pass
python scripts/e2e_activation.py http://<host>:8000/api/v1
```

With `ALLOW_INLINE_ACTIVATION_TOKEN=false` it stops after issuing the link and
reports `activation_token=None`; with the default (`true`) it continues
through redemption and the suspend/restore cycle.

### Single API worker (important)

The login/verify rate limits are **in-process sliding windows**. The compose
setup runs one uvicorn worker on purpose. If you scale workers or replicas,
move rate limiting to a shared store (e.g. Redis) or terminate it at a reverse
proxy — otherwise each worker gets its own budget.

## 3. Networking: Tailscale (dev) / HTTPS (anything else)

For development, put the server and the phone on the same Tailscale network
and point the app at the Tailscale IP:

```bash
flutter run --dart-define=API_BASE_URL=http://<tailscale-ip>:8000/api
```

Tailscale traffic is already encrypted end-to-end (WireGuard), so plain HTTP
inside the tailnet is acceptable for development.

**The app will refuse that URL until you allow-list it.** Android 9+ blocks
cleartext HTTP by default, and HostelPass keeps that default (a global
`usesCleartextTraffic="true"` would let a typo'd `API_BASE_URL` silently
downgrade a real deployment). Add one exact-host line to
`app/android/app/src/main/res/xml/network_security_config.xml`:

```xml
<domain includeSubdomains="false">100.x.y.z</domain>   <!-- your Tailscale IP -->
```

The emulator alias `10.0.2.2` and loopback are already permitted. There is no
CIDR or wildcard form — exact hosts only, deliberately.

For anything beyond your own devices, put the API behind a reverse proxy with a
real certificate (Caddy, nginx + Let's Encrypt, or Tailscale Serve) and build
with `https://`; no cleartext entry is then needed.

For any deployment beyond your own tailnet, terminate TLS at a reverse proxy
(Caddy, nginx, or Traefik) in front of port 8000 and serve the API only over
HTTPS — the camera, geolocation, and secure-storage features are fine over the
app's HTTP client, but JWTs and face embeddings must never cross plaintext.
Android 9+ blocks cleartext by default; the debug manifest currently permits
it for the emulator/dev flow — a release build should restrict
`networkSecurityConfig` to HTTPS plus an explicit domain allowlist.

## 4. Backups

All state lives in the Postgres volume (`pgdata`). A consistent dump:

```bash
docker compose exec db pg_dump -U hostelpass -Fc hostelpass > hostelpass-$(date +%F).dump
```

Restore:

```bash
docker compose exec -T db pg_restore -U hostelpass -d hostelpass --clean --if-exists < hostelpass-YYYY-MM-DD.dump
```

Nightly dumps + `cron` + an off-machine copy (e.g. rsync over Tailscale) is
enough for a hostel-sized deployment. The face-template encryption key is part
of the backup story: without `FACE_TEMPLATE_KEY`, encrypted templates are
unreadable after restore — store the key in a password manager, not only in
`.env`.

## 5. Updating the app binary

```bash
cd app
flutter build apk --release --dart-define=API_BASE_URL=https://attendance.example.edu/api
```

The API base URL is compile-time; a wrong URL means the app simply cannot reach
its backend, so bake the real hostname in for release builds.

## 6. Known operational caveats

- **GPS spoofing** — a rooted device with a mock-location provider can fake
  coordinates. The server's conservative rule (`distance + accuracy ≤ radius`)
  narrows accidental false positives but cannot detect deliberate mocking.
  Combine with the face check and review `pending_review` records.
- **Liveness strength** — the bundled passive PAD model catches photos and
  screen replays but is not ISO 30107-3 certified. For higher assurance, keep
  `require_liveness=true` and review pending records rather than lowering
  thresholds.
- **Rate limits reset on restart** — in-memory state; acceptable for a single
  box, but do not rely on them as a security boundary.
- **4 GB RAM** — the API is CPU-light (cosine similarity over 128 floats); the
  Postgres shared_buffers default is fine at this scale. No GPU is needed
  anywhere: face recognition and liveness run on the *phone*.
