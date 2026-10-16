"""Activation email delivery — render and send, with an EXPLICIT mode.

Why this exists: issuing an activation token only stores a hash in the
database; nothing ever reached the student's inbox. This module is the single
transport used by the warden activation endpoints, and it reports the REAL
outcome of the attempt — "sent" is only returned when an SMTP provider
accepted the message. An activation record alone never claims a send.

Modes (``EMAIL_MODE``):
  * ``off``  — no attempt; callers get ``not_configured``.
  * ``log``  — development: the rendered ``.eml`` (with the activation link)
               is written to ``EMAIL_LOG_DIR`` for local inspection. The
               token is never written to application logs or audit entries.
  * ``smtp`` — production: delivered through SMTP (STARTTLS; implicit TLS on
               port 465).

No background worker or queue is required (and none is deployed): the send is
performed inline in the request with a short timeout, which keeps the single
API container honest — the warden sees "sent" only if the provider accepted
the mail during that request.

Security notes:
  * The plaintext token exists only in this process, only for the duration of
    the send; it is never logged, never persisted, never audited.
  * SMTP credentials come from the environment only, never from source.
"""

from __future__ import annotations

import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from ..core import clock
from ..core.config import settings

log = logging.getLogger("hostelpass.email")

# Delivery outcomes reported to callers (and surfaced honestly in the app).
STATUS_SENT = "sent"
STATUS_LOGGED = "logged"
STATUS_FAILED = "failed"
STATUS_NOT_CONFIGURED = "not_configured"

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ActivationEmailResult:
    """Outcome of one delivery attempt. ``detail`` is human-readable and
    guaranteed token-free (error summaries / outbox filename only)."""

    status: str
    detail: str | None = None


def build_activation_links(plaintext_token: str) -> tuple[str, str]:
    """Return ``(deep_link, web_link)`` for the token.

    * Deep link: opens the Student app's activation screen directly.
    * Web link: built from APP_BASE_URL (the deployment's PUBLIC url —
      localhost only ever appears if the operator configured it that way).
      The token travels in the URL **fragment** (``#token=``): browsers never
      transmit fragments to the server, so opening the page cannot write the
      token into an access log. The landing page's own script hands the token
      back to the Student app via the ``hostelpass://`` deep link.
    """
    deep_link = f"hostelpass://activate?token={plaintext_token}"
    base = settings.app_base_url.rstrip("/")
    web_link = f"{base}/activate#token={plaintext_token}"
    return deep_link, web_link


def _render_activation_email(
    *,
    to_email: str,
    student_name: str,
    roll: str,
    plaintext_token: str,
    expires_at: datetime,
) -> tuple[EmailMessage, str, str]:
    """Build the activation email. Returns ``(message, deep_link, web_link)``."""
    deep_link, web_link = build_activation_links(plaintext_token)
    expires = expires_at.strftime("%d %b %Y, %H:%M UTC")
    sender_name = settings.smtp_from_name or "HostelPass"
    sender_addr = settings.smtp_from_email or "no-reply@localhost"

    subject = "HostelPass — set up your student account"
    body = (
        f"Hello {student_name},\n"
        f"\n"
        f"Your hostel warden has set up your HostelPass account (roll {roll}).\n"
        f"Use the link below to set your password and activate your account.\n"
        f"The link is single-use and expires on {expires}.\n"
        f"\n"
        f"Open in the HostelPass Student app:\n"
        f"{deep_link}\n"
        f"\n"
        f"Or open this page on a device with the app installed:\n"
        f"{web_link}\n"
        f"\n"
        f"If neither link opens the app, open the HostelPass Student app,\n"
        f"choose Activate, and paste this code:\n"
        f"{plaintext_token}\n"
        f"\n"
        f"If you did not expect this message, contact your hostel office.\n"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_addr}>"
    msg["To"] = to_email
    msg.set_content(body)
    return msg, deep_link, web_link


def _write_outbox_file(msg: EmailMessage, roll: str) -> str:
    """email_mode=log: persist the rendered email to the local outbox.

    Returns the filename (token-free). This is a development convenience —
    the file contains the activation link and must live OUTSIDE application
    logs.
    """
    outbox = Path(settings.email_log_dir)
    outbox.mkdir(parents=True, exist_ok=True)
    stamp = clock.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_roll = _SAFE_FILENAME_RE.sub("-", roll)[:40] or "student"
    path = outbox / f"activation-{stamp}-{safe_roll}.eml"
    path.write_bytes(bytes(msg))
    return path.name


def _send_smtp(msg: EmailMessage) -> None:
    """Deliver through the configured SMTP provider. Raises on failure."""
    host = settings.smtp_host
    port = settings.smtp_port
    timeout = settings.email_timeout_seconds
    context = ssl.create_default_context()

    if port == 465:
        client = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=timeout)
    try:
        if port != 465 and settings.smtp_use_tls:
            client.starttls(context=context)
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(msg)
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001 - close best-effort after failure
            pass


def send_activation_email(
    *,
    to_email: str,
    student_name: str,
    roll: str,
    plaintext_token: str,
    expires_at: datetime,
) -> ActivationEmailResult:
    """Attempt one activation-email delivery. Never raises; the outcome —
    including misconfiguration — is returned so the API can report it
    honestly. The token is never logged.
    """
    mode = settings.email_mode

    if mode == "off":
        return ActivationEmailResult(
            STATUS_NOT_CONFIGURED,
            "Email delivery is not configured on this deployment "
            "(EMAIL_MODE=off).",
        )

    if mode == "smtp" and (not settings.smtp_host or not settings.smtp_from_email):
        return ActivationEmailResult(
            STATUS_FAILED,
            "SMTP is not fully configured: SMTP_HOST and SMTP_FROM_EMAIL "
            "must both be set when EMAIL_MODE=smtp.",
        )

    try:
        msg, _, _ = _render_activation_email(
            to_email=to_email,
            student_name=student_name,
            roll=roll,
            plaintext_token=plaintext_token,
            expires_at=expires_at,
        )
    except Exception as exc:  # noqa: BLE001 - rendering must not 500 the API
        log.exception("activation email rendering failed")
        return ActivationEmailResult(
            STATUS_FAILED, f"Email rendering failed ({type(exc).__name__})."
        )

    if mode == "log":
        try:
            filename = _write_outbox_file(msg, roll)
        except Exception as exc:  # noqa: BLE001
            log.exception("activation email outbox write failed")
            return ActivationEmailResult(
                STATUS_FAILED,
                f"Outbox write failed ({type(exc).__name__}: {exc})"[:200],
            )
        # Filename only — never the rendered email, never the token.
        log.info(
            "activation email for roll %s written to outbox file %s "
            "(EMAIL_MODE=log; no real email was sent)",
            roll,
            filename,
        )
        return ActivationEmailResult(STATUS_LOGGED, filename)

    # mode == "smtp"
    try:
        _send_smtp(msg)
    except Exception as exc:  # noqa: BLE001 - provider/network errors
        # str(exc) carries the provider's (token-free) diagnostics; never the
        # message body, which we deliberately keep out of exception text.
        log.error(
            "activation email delivery to the SMTP provider failed for roll "
            "%s: %s: %s",
            roll,
            type(exc).__name__,
            exc,
        )
        return ActivationEmailResult(
            STATUS_FAILED, f"{type(exc).__name__}: {exc}"[:200]
        )

    log.info(
        "activation email accepted by SMTP provider for roll %s (to=%s)",
        roll,
        to_email,
    )
    return ActivationEmailResult(STATUS_SENT)
