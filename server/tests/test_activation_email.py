"""Activation email delivery — the sender must ACTUALLY run when a warden
issues an activation link, and the API must report the REAL outcome.

Regression cover for the original defect: an activation record was created
(and ``delivered`` claimed true in production) while no transport ever sent
anything. A token row must never masquerade as a delivered email.

Security properties asserted here:
  * the plaintext token reaches the transport in-process only — never the
    application logs, never the audit trail, never the HTTP response
    (unless the dev-only inline switch is on).
  * SMTP credentials come from settings/env, never from source.
  * emails carry the PUBLIC APP_BASE_URL link, not localhost.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from conftest import staff_headers as _admin_headers

from app.core.config import settings
from app.models import AccountActivationToken, AuditLog
from app.services import email as email_service
from app.services.email import ActivationEmailResult

W_STUDENTS = "/api/v1/warden/students"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def enrolling_student(db, make_hostel, make_student):
    """A face-enrolled student, ready for the activation step.

    Mirrors production creation: the account carries the unusable placeholder
    hash (``!not-activated:<roll>``), never a staff-chosen password.
    """
    from app.core.security import hash_password
    from app.services.enrollment import _UNSET_PASSWORD_MARKER

    hostel = make_hostel()
    student = make_student(
        roll="CS-2022-084",
        name="Rohan Sharma",
        hostel=hostel,
        account_status="inactive",
        enrollment_status="face_enrolled",
        email="cs-2022-084@ceconline.edu",
    )
    student.user.password_hash = hash_password(
        _UNSET_PASSWORD_MARKER + student.student_id
    )
    db.commit()
    return student


@pytest.fixture
def capture_sender(monkeypatch):
    """Replace the transport with a recorder that reports success."""
    calls: list[dict] = []

    def _fake(**kwargs) -> ActivationEmailResult:
        calls.append(kwargs)
        return ActivationEmailResult(email_service.STATUS_SENT)

    monkeypatch.setattr(email_service, "send_activation_email", _fake)
    return calls


@pytest.fixture
def reset_email_settings(monkeypatch):
    """Force deterministic email settings for one test."""
    monkeypatch.setattr(settings, "email_mode", "off")
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", "")
    monkeypatch.setattr(settings, "smtp_password", "")
    monkeypatch.setattr(settings, "smtp_from_email", "")
    monkeypatch.setattr(settings, "smtp_use_tls", True)
    monkeypatch.setattr(settings, "app_base_url", "http://localhost:8000")


# --------------------------------------------------------------------------
# Endpoint: the sender is invoked exactly when a link is issued
# --------------------------------------------------------------------------

def test_activate_invokes_email_sender(client, enrolling_student,
                                       capture_sender):
    """Issuing an activation link must actually hand the email to a sender."""
    roll = enrolling_student.student_id
    resp = client.post(f"{W_STUDENTS}/{roll}/activate",
                       headers=_admin_headers(client))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(capture_sender) == 1
    sent = capture_sender[0]
    assert sent["to_email"] == "cs-2022-084@ceconline.edu"
    assert sent["student_name"] == "Rohan Sharma"
    assert sent["roll"] == roll
    assert len(sent["plaintext_token"]) >= 40  # secrets.token_urlsafe(32)

    # Honest outcome reporting: sent => delivered true. The response ALSO
    # carries the freshly issued key (warden WhatsApp hand-off); the email is
    # an ADDITIONAL delivery path, never the only way to obtain the key.
    assert body["email_status"] == "sent"
    assert body["delivered"] is True
    assert body["activation_token"] == sent["plaintext_token"]
    assert sent["plaintext_token"] in body["setup_url"]
    assert body["activation_pending"] is True


def test_resend_activation_also_sends_email(client, enrolling_student,
                                            capture_sender):
    """Resend is a delivery path too — and it reissues, never reuses."""
    roll = enrolling_student.student_id
    headers = _admin_headers(client)
    first = client.post(f"{W_STUDENTS}/{roll}/activate", headers=headers)
    assert first.status_code == 200, first.text
    second = client.post(f"{W_STUDENTS}/{roll}/resend-activation",
                         headers=headers)
    assert second.status_code == 200, second.text

    assert len(capture_sender) == 2
    assert (capture_sender[0]["plaintext_token"]
            != capture_sender[1]["plaintext_token"])
    assert second.json()["email_status"] == "sent"
    assert second.json()["delivered"] is True


def test_failed_delivery_never_claims_sent(client, enrolling_student, db,
                                           monkeypatch):
    """A transport failure is reported as failed; the link survives."""
    def _boom(**kwargs) -> ActivationEmailResult:
        return ActivationEmailResult(
            email_service.STATUS_FAILED, "ConnectionRefusedError: relay down"
        )

    monkeypatch.setattr(email_service, "send_activation_email", _boom)
    roll = enrolling_student.student_id
    resp = client.post(f"{W_STUDENTS}/{roll}/activate",
                       headers=_admin_headers(client))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["email_status"] == "failed"
    assert body["delivered"] is False
    assert "relay down" in body["email_detail"]
    assert body["activation_pending"] is True
    # The token was committed BEFORE the send: still redeemable, resendable.
    assert db.scalar(select(AccountActivationToken.token_hash)) is not None


def test_email_off_reports_not_configured(client, enrolling_student,
                                          reset_email_settings):
    """EMAIL_MODE=off: no send is attempted and the API says exactly that."""
    roll = enrolling_student.student_id
    resp = client.post(f"{W_STUDENTS}/{roll}/activate",
                       headers=_admin_headers(client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email_status"] == "not_configured"
    assert body["delivered"] is False
    assert body["activation_pending"] is True


def test_resend_never_fakes_password_set(client, enrolling_student, db,
                                         monkeypatch):
    """Regression: revoking predecessors stamps ``used_at`` — that must NEVER
    be reported as ``password_set`` ("link redeemed"). A real (non-placeholder)
    password hash is the only proof of redemption.

    Full truth chain: issue -> resend -> redeem -> password_set flips ONCE,
    exactly when the student actually sets their password.
    """
    from conftest import staff_headers

    # Dev-only: return the plaintext so the test can exercise redemption.
    monkeypatch.setattr(settings, "allow_inline_activation_token", True)
    roll = enrolling_student.student_id
    headers = staff_headers(client)

    # 1. Issue a link: not redeemed yet.
    resp = client.post(f"{W_STUDENTS}/{roll}/activate", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["email_status"] == "not_configured"
    got = client.get(f"{W_STUDENTS}/{roll}", headers=headers).json()
    assert got["password_set"] is False
    assert got["activation_pending"] is True

    # 2. Resend: the predecessor is revoked via used_at — STILL not redeemed.
    resp = client.post(f"{W_STUDENTS}/{roll}/resend-activation", headers=headers)
    assert resp.status_code == 200, resp.text
    token = resp.json()["activation_token"]
    got = client.get(f"{W_STUDENTS}/{roll}", headers=headers).json()
    assert got["password_set"] is False, (
        "a reissued (revoked) link must not be reported as a redemption"
    )
    assert got["activation_pending"] is True

    # 3. The student actually redeems the NEWEST link -> NOW it is true.
    assert token, "dev inline token needed to exercise redemption"
    resp = client.post("/api/v1/auth/activate", json={
        "token": token, "password": "SetByStudent!42",
    })
    assert resp.status_code == 200, resp.text
    got = client.get(f"{W_STUDENTS}/{roll}", headers=headers).json()
    assert got["password_set"] is True
    assert got["enrollment_status"] == "active"


def test_audit_records_status_but_never_the_token(client, enrolling_student,
                                                  db, monkeypatch):
    """The audit trail records the delivery status — never the token."""
    # Inline mode ON so a token exists in the response and the "never in
    # audit" assertion is meaningful.
    monkeypatch.setattr(settings, "allow_inline_activation_token", True)
    roll = enrolling_student.student_id
    resp = client.post(f"{W_STUDENTS}/{roll}/activate",
                       headers=_admin_headers(client))
    assert resp.status_code == 200, resp.text
    token = resp.json()["activation_token"]
    assert token, "inline mode must return the plaintext token"

    entry = db.scalar(
        select(AuditLog).where(AuditLog.action == "student.activate_issue")
    )
    assert entry is not None
    details = str(entry.details)
    assert "email_status" in details
    assert token not in details


# --------------------------------------------------------------------------
# Service: real modes (off / log / smtp)
# --------------------------------------------------------------------------

def test_log_mode_writes_outbox_but_never_application_logs(
    reset_email_settings, monkeypatch, caplog, tmp_path,
):
    """EMAIL_MODE=log: the rendered email lands in the outbox FILE only."""
    monkeypatch.setattr(settings, "email_mode", "log")
    monkeypatch.setattr(settings, "email_log_dir", str(tmp_path))

    caplog.set_level(logging.INFO, logger="hostelpass.email")
    result = email_service.send_activation_email(
        to_email="cs-2022-084@ceconline.edu",
        student_name="Rohan Sharma",
        roll="CS-2022-084",
        plaintext_token="SECRET-TOKEN-VALUE-FOR-TEST",
        expires_at=_now(),
    )
    assert result.status == email_service.STATUS_LOGGED

    files = list(tmp_path.glob("*.eml"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "SECRET-TOKEN-VALUE-FOR-TEST" in content          # outbox has it
    assert "hostelpass://activate?token=" in content         # deep link

    # ...but the APPLICATION LOG carries no token.
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "SECRET-TOKEN-VALUE-FOR-TEST" not in logged


def test_off_mode_never_touches_transport(reset_email_settings, monkeypatch):
    """EMAIL_MODE=off attempts nothing and reports not_configured."""
    def _should_not_run(**kwargs):
        raise AssertionError("transport must not be invoked in off mode")

    monkeypatch.setattr(email_service, "_send_smtp", _should_not_run)
    result = email_service.send_activation_email(
        to_email="x@ceconline.edu", student_name="X", roll="R",
        plaintext_token="t", expires_at=_now(),
    )
    assert result.status == email_service.STATUS_NOT_CONFIGURED
    assert result.detail is not None


class _FakeSMTP:
    """Minimal in-memory stand-in for smtplib.SMTP."""

    instances: list = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.tls_started = False
        self.login_args = None
        self.sent_message = None
        self.quit_called = False
        _FakeSMTP.instances.append(self)

    def starttls(self, context=None):
        self.tls_started = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.sent_message = message

    def quit(self):
        self.quit_called = True


def _enable_smtp(monkeypatch, *, port=587):
    monkeypatch.setattr(settings, "email_mode", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.edu")
    monkeypatch.setattr(settings, "smtp_port", port)
    monkeypatch.setattr(settings, "smtp_username", "mailer@example.edu")
    monkeypatch.setattr(settings, "smtp_password", "provider-secret")
    monkeypatch.setattr(settings, "smtp_from_email", "no-reply@example.edu")
    monkeypatch.setattr(
        settings, "app_base_url", "https://hostelpass.example.edu"
    )
    _FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)


def test_smtp_mode_delivers_through_provider(reset_email_settings,
                                             monkeypatch):
    """EMAIL_MODE=smtp: STARTTLS, provider login, real send_message."""
    _enable_smtp(monkeypatch)
    result = email_service.send_activation_email(
        to_email="cs-2022-084@ceconline.edu",
        student_name="Rohan Sharma",
        roll="CS-2022-084",
        plaintext_token="SECRET-TOKEN-VALUE-FOR-TEST",
        expires_at=_now(),
    )
    assert result.status == email_service.STATUS_SENT

    assert len(_FakeSMTP.instances) == 1
    inst = _FakeSMTP.instances[0]
    assert (inst.host, inst.port) == ("smtp.example.edu", 587)
    assert inst.tls_started is True
    assert inst.login_args == ("mailer@example.edu", "provider-secret")
    assert inst.quit_called is True

    msg = inst.sent_message
    assert msg["To"] == "cs-2022-084@ceconline.edu"
    assert "no-reply@example.edu" in msg["From"]
    body = msg.get_content()
    # Item 11: the emailed link uses the PUBLIC app URL, never localhost.
    # The token rides in the fragment so a click can never log it server-side.
    assert "https://hostelpass.example.edu/activate#token=" in body
    assert "localhost" not in body
    assert "SECRET-TOKEN-VALUE-FOR-TEST" in body  # the email IS the channel


def test_smtp_provider_failure_is_reported_failed(reset_email_settings,
                                                  monkeypatch):
    """Provider rejection surfaces as failed with a token-free reason."""
    _enable_smtp(monkeypatch)

    def _raise(self, *args, **kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(_FakeSMTP, "send_message", _raise)
    result = email_service.send_activation_email(
        to_email="x@ceconline.edu", student_name="X", roll="R",
        plaintext_token="UNIQUE-TOKEN-X", expires_at=_now(),
    )
    assert result.status == email_service.STATUS_FAILED
    assert result.detail and "SMTPAuthenticationError" in result.detail
    assert "UNIQUE-TOKEN-X" not in result.detail  # never echoes the token


def test_smtp_mode_without_host_reports_configuration_failure(
    reset_email_settings, monkeypatch,
):
    """EMAIL_MODE=smtp with no host is a config error, reported as failed."""
    monkeypatch.setattr(settings, "email_mode", "smtp")
    result = email_service.send_activation_email(
        to_email="x@ceconline.edu", student_name="X", roll="R",
        plaintext_token="t", expires_at=_now(),
    )
    assert result.status == email_service.STATUS_FAILED
    assert "SMTP_HOST" in (result.detail or "")


def test_activation_links_prefer_configured_base_url(reset_email_settings,
                                                     monkeypatch):
    """APP_BASE_URL drives the web link; the deep link is stable."""
    monkeypatch.setattr(
        settings, "app_base_url", "https://hostelpass.example.edu/"
    )
    deep, web = email_service.build_activation_links("TOKEN123")
    assert deep == "hostelpass://activate?token=TOKEN123"
    # Fragment, not query: the browser never sends #token= to the server, so
    # clicking the web link can never write the token into an access log.
    assert web == "https://hostelpass.example.edu/activate#token=TOKEN123"


# --------------------------------------------------------------------------
# The email's web link: fragment-based hand-off page at GET /activate
# --------------------------------------------------------------------------


def test_activation_landing_page_serves_handoff(client):
    """GET /activate answers 200 with the client-side hand-off page.

    The web link inside the email points here; the page hands the token from
    the URL FRAGMENT to the Student app via the hostelpass:// deep link, so
    the server never needs (and never receives) the token for this step.
    """
    resp = client.get("/activate")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    html = resp.text
    assert "hostelpass://activate?token=" in html   # deep-link hand-off
    assert "location.hash" in html                 # reads the fragment only
    # No server-side token endpoint lives on this page (activation itself is
    # POST /api/v1/auth/activate — unchanged).
    assert "auth/activate" not in html


def test_landing_page_never_reflects_query_input(client):
    """Whatever appears in the query string is never echoed back.

    Real links carry the token in the fragment (never transmitted); this
    pins the response side too, so even a hand-edited ?token= URL cannot get
    its value reflected by the server.
    """
    secret = "QUERY-VALUE-MUST-NOT-BE-REFLECTED"
    resp = client.get("/activate", params={"token": secret})
    assert resp.status_code == 200
    assert secret not in resp.text


# --------------------------------------------------------------------------
# Service: resend mode (production — Resend Email API over HTTPS)
# --------------------------------------------------------------------------

class _FakeResendAPI:
    """Recorder standing in for ``resend.Emails`` (send only)."""

    calls: list = []
    raise_with: Exception | None = None
    return_id: str = "msg_test_123"

    @classmethod
    def send(cls, params, options=None):
        if cls.raise_with is not None:
            raise cls.raise_with
        cls.calls.append(dict(params))
        return {"id": cls.return_id}


def _enable_resend(monkeypatch, *, with_key=True,
                   from_email="noreply@example.edu"):
    """EMAIL_MODE=resend with a fake Resend API boundary.

    Everything EXCEPT the HTTP call itself is real: payload rendering, link
    construction, configuration checks, status mapping and the API contract.
    The live-network path is exercised against the real provider in the
    deployment E2E, never in the unit suite.
    """
    monkeypatch.setattr(settings, "email_mode", "resend")
    monkeypatch.setattr(
        settings, "resend_api_key", "re_test_key" if with_key else ""
    )
    monkeypatch.setattr(settings, "resend_from_email", from_email)
    monkeypatch.setattr(settings, "resend_from_name", "DormPASS")
    monkeypatch.setattr(
        settings, "app_base_url", "https://hostelpass.example.edu"
    )
    _FakeResendAPI.calls = []
    _FakeResendAPI.raise_with = None
    assert email_service.resend is not None, "resend SDK must be installed"
    monkeypatch.setattr(email_service.resend.Emails, "send", _FakeResendAPI.send)


def test_resend_mode_delivers_through_resend_api(reset_email_settings,
                                                 monkeypatch):
    """EMAIL_MODE=resend: real payload through the Resend API boundary."""
    _enable_resend(monkeypatch)
    result = email_service.send_activation_email(
        to_email="cs-2022-084@ceconline.edu",
        student_name="Rohan Sharma",
        roll="CS-2022-084",
        plaintext_token="SECRET-TOKEN-VALUE-FOR-TEST",
        expires_at=_now(),
    )
    assert result.status == email_service.STATUS_SENT
    assert result.provider_id == "msg_test_123"
    assert "msg_test_123" in (result.detail or "")
    assert "SECRET-TOKEN-VALUE-FOR-TEST" not in (result.detail or "")

    assert len(_FakeResendAPI.calls) == 1
    params = _FakeResendAPI.calls[0]
    assert params["from"] == "DormPASS <noreply@example.edu>"
    assert params["to"] == ["cs-2022-084@ceconline.edu"]
    assert params["subject"] == "Activate your DormPASS account"

    # The email IS the channel: the token must be present in the payload —
    # over the PUBLIC https base, never localhost, and with the fragment
    # form so a click can never write the token into a server access log.
    assert (
        "https://hostelpass.example.edu/activate#token="
        "SECRET-TOKEN-VALUE-FOR-TEST" in params["html"]
    )
    assert (
        "https://hostelpass.example.edu/activate#token="
        "SECRET-TOKEN-VALUE-FOR-TEST" in params["text"]
    )
    assert "localhost" not in params["html"]
    assert "hostelpass://activate?token=SECRET-TOKEN-VALUE-FOR-TEST" in params["text"]
    # Paste-code fallback (Student app's manual Activate screen).
    assert "SECRET-TOKEN-VALUE-FOR-TEST" in params["html"]


def test_resend_mode_requires_api_key_and_sender(reset_email_settings,
                                                 monkeypatch):
    """EMAIL_MODE=resend without configuration is a reported config error —
    never a fake send."""
    _enable_resend(monkeypatch, with_key=False)
    result = email_service.send_activation_email(
        to_email="x@ceconline.edu", student_name="X", roll="R",
        plaintext_token="t", expires_at=_now(),
    )
    assert result.status == email_service.STATUS_FAILED
    assert "RESEND_API_KEY" in (result.detail or "")
    assert _FakeResendAPI.calls == []


def test_resend_provider_failure_is_reported_failed(reset_email_settings,
                                                    monkeypatch):
    """A Resend/network failure surfaces as failed, token-free."""
    _enable_resend(monkeypatch)
    _FakeResendAPI.raise_with = RuntimeError("simulated Resend outage")
    result = email_service.send_activation_email(
        to_email="x@ceconline.edu", student_name="X", roll="R",
        plaintext_token="UNIQUE-TOKEN-Y", expires_at=_now(),
    )
    assert result.status == email_service.STATUS_FAILED
    assert "RuntimeError" in (result.detail or "")
    assert "outage" in (result.detail or "")
    assert "UNIQUE-TOKEN-Y" not in (result.detail or "")


def test_activate_endpoint_with_resend_reports_sent_without_inline_token(
    client, enrolling_student, monkeypatch,
):
    """Production posture end-to-end: EMAIL_MODE=resend + inline token
    withheld -> the response reports the REAL send and never carries the
    key; the audit records the status, never the token."""
    _enable_resend(monkeypatch)
    monkeypatch.setattr(settings, "allow_inline_activation_token", False)
    roll = enrolling_student.student_id
    resp = client.post(f"{W_STUDENTS}/{roll}/activate",
                       headers=_admin_headers(client))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["email_status"] == "sent"
    assert body["delivered"] is True
    assert body["activation_token"] is None
    assert body["setup_url"] is None
    assert body["activation_pending"] is True
    assert "msg_test_123" in (body["email_detail"] or "")

    assert len(_FakeResendAPI.calls) == 1
    assert _FakeResendAPI.calls[0]["to"] == ["cs-2022-084@ceconline.edu"]


def test_activation_base_url_env_alias(monkeypatch):
    """ACTIVATION_BASE_URL is accepted as an alias of APP_BASE_URL."""
    from app.core.config import Settings

    monkeypatch.setenv("ACTIVATION_BASE_URL", "https://hostels.example.edu")
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    assert Settings(_env_file=None).app_base_url == "https://hostels.example.edu"

    monkeypatch.setenv("APP_BASE_URL", "https://primary.example.edu")
    # When both are present the canonical name wins.
    assert Settings(_env_file=None).app_base_url == "https://primary.example.edu"
