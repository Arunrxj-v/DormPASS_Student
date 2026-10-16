"""FastAPI application factory.

Startup performs a DB connectivity check only — schema management is
exclusively Alembic's job (never ``create_all``).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .api import (
    admin_router,
    attendance_router,
    auth_router,
    config_router,
    face_enrollment_router,
    health_router,
    hostels_router,
    students_router,
    warden_router,
)
from .core.config import settings
from .core.errors import add_exception_handlers
from .db.session import db_up

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("hostelpass")


# Landing page for the activation link embedded in emails
# ({APP_BASE_URL}/activate#token=…). The token exists ONLY in the URL
# fragment: browsers never transmit fragments to the server, so this handler
# cannot see it, cannot echo it, and it can never appear in an access log.
# The page's own script hands the token straight to the Student app through
# the hostelpass:// deep link; without a fragment it shows the
# paste-the-code fallback. There is deliberately no server-side token
# processing here — activation itself is POST /api/v1/auth/activate.
_ACTIVATION_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HostelPass &mdash; activate your account</title>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center;
         justify-content:center; background:#f4f6f8; color:#1c2430;
         font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  main { background:#fff; border-radius:12px; width:calc(100% - 2.5rem);
         max-width:26rem; padding:1.75rem;
         box-shadow:0 4px 18px rgba(0,0,0,.08); }
  h1 { margin:0 0 .5rem; font-size:1.35rem; }
  p { line-height:1.5; font-size:.95rem; }
  .btn { display:block; width:100%; box-sizing:border-box; margin:.4rem 0;
         padding:.7rem 1rem; border:0; border-radius:8px; cursor:pointer;
         background:#1a62e6; color:#fff; font-size:1rem; font-weight:600;
         text-align:center; text-decoration:none; }
  .btn.secondary { background:#eef1f5; color:#1c2430; }
  .help { color:#5b6675; font-size:.85rem; margin-top:1rem; }
</style>
</head>
<body>
<main>
  <h1>HostelPass</h1>
  <p id="status">Checking your activation link&hellip;</p>
  <p id="actions" hidden>
    <a id="openApp" class="btn" href="#">Open in the HostelPass Student app</a>
    <button id="copyCode" class="btn secondary" type="button">Copy my activation code</button>
  </p>
  <p class="help">If nothing opens, launch the HostelPass Student app on your
  phone, choose <strong>Activate</strong>, and paste the code from your
  activation email.</p>
</main>
<script>
(function () {
  // Read the code from the URL fragment only — it never left the browser.
  var token = "";
  if (location.hash.length > 1) {
    token = new URLSearchParams(location.hash.slice(1)).get("token") || "";
  }
  if (!token) {
    document.getElementById("status").textContent =
      "This page was opened without an activation code. Open the link from " +
      "your activation email, or paste that email's code into the app.";
    return;
  }
  document.getElementById("status").textContent =
    "Activation code found. Continue in the HostelPass Student app:";
  document.getElementById("openApp").href =
    "hostelpass://activate?token=" + encodeURIComponent(token);
  document.getElementById("actions").hidden = false;
  document.getElementById("copyCode").addEventListener("click", function () {
    if (navigator.clipboard) { navigator.clipboard.writeText(token); }
    this.textContent = "Code copied";
  });
})();
</script>
</body>
</html>
"""


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup connectivity check — logs status, never mutates the schema."""
    if db_up():
        logger.info("Database connectivity: up (%s)", settings.database_url.rsplit("@", 1)[-1])
    else:
        logger.warning(
            "Database connectivity: DOWN — the API will start but requests will fail "
            "until the database is reachable."
        )
    yield


def create_app() -> FastAPI:
    """Build the FastAPI app with CORS, routers and the error envelope."""
    app = FastAPI(
        title="HostelPass API",
        version=settings.app_version,
        description="Smart hostel attendance: GPS geofence + on-device face recognition.",
        lifespan=lifespan,
    )
    add_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (
        health_router,
        config_router,
        auth_router,
        students_router,
        hostels_router,
        face_enrollment_router,
        attendance_router,
        admin_router,
        warden_router,
    ):
        app.include_router(router, prefix="/api/v1")

    # Public hand-off page for the link inside activation emails. It is NOT an
    # API route and performs no server-side token handling: the token only ever
    # exists in the browser's URL fragment, so it can never leak into logs or
    # responses from this handler.
    @app.get("/activate", response_class=HTMLResponse, include_in_schema=False)
    def activation_landing_page() -> HTMLResponse:
        """Serve the client-side activation hand-off page (fragment-based)."""
        return HTMLResponse(_ACTIVATION_PAGE)

    return app


app = create_app()
