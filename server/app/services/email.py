"""Activation email delivery — render and send, with an EXPLICIT mode.

Why this exists: issuing an activation token only stores a hash in the
database; nothing ever reached the student's inbox. This module is the single
transport used by the warden activation endpoints, and it reports the REAL
outcome of the attempt — "sent" is only returned when an SMTP provider
accepted the message. An activation record alone never claims a send.

Modes (``EMAIL_MODE``):
  * ``off``    — no attempt; callers get ``not_configured``.
  * ``log``    — development: the rendered ``.eml`` (with the activation
                 link) is written to ``EMAIL_LOG_DIR`` for local inspection.
                 The token is never written to application logs or audit
                 entries.
  * ``resend`` — PRODUCTION: delivered through the Resend Email API over
                 HTTPS using the official Python SDK (``RESEND_API_KEY``,
                 ``RESEND_FROM_EMAIL``). "sent" is only returned when Resend
                 accepts the message; the provider message id is recorded
                 (never the token).
  * ``smtp``   — alternative production backend: delivered through SMTP
                 (STARTTLS; implicit TLS on port 465).

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

import html
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

try:  # Official Resend SDK (EMAIL_MODE=resend). Optional at import time so
    # off/log/smtp deployments keep working even if the package is missing;
    # the resend mode reports a clear configuration failure in that case.
    import resend  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on installed extras
    resend = None

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
    guaranteed token-free (error summaries / outbox filename only).
    ``provider_id`` carries the email provider's message id when the
    transport reported one (Resend: the ``id`` returned at acceptance) —
    useful for delivery tracking, never sensitive."""

    status: str
    detail: str | None = None
    provider_id: str | None = None


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


def _render_resend_payload(
    *,
    to_email: str,
    student_name: str,
    roll: str,
    plaintext_token: str,
    expires_at: datetime,
) -> tuple[str, str, str, str, str, str]:
    """Build the production activation email for the Resend transport.

    Returns ``(from_header, subject, text_body, html_body, deep_link,
    web_link)``. The clickable button targets the HTTPS hand-off page
    (``<base>/activate#token=…`` — the fragment never reaches server logs);
    that page hands the token to the Student app via the ``hostelpass://``
    deep link. The app's manual paste-code fallback is included as well.
    """
    deep_link, web_link = build_activation_links(plaintext_token)
    expires = expires_at.strftime("%d %b %Y, %H:%M UTC")
    sender_name = settings.resend_from_name or "DormPASS"
    sender_addr = settings.resend_from_email
    from_header = f"{sender_name} <{sender_addr}>"

    subject = "Activate your DormPASS account"

    text_body = (
        f"Hello {student_name},\n"
        f"\n"
        f"Your DormPASS account has been created (roll {roll}).\n"
        f"\n"
        f"Click the link below to activate your DormPASS account:\n"
        f"{web_link}\n"
        f"\n"
        f"This activation link expires on {expires} and can be used only\n"
        f"once.\n"
        f"\n"
        f"If the button does not work, open the DormPASS Student app,\n"
        f"choose Activate, and paste this code:\n"
        f"{plaintext_token}\n"
        f"\n"
        f"On a phone with the Student app installed this opens it directly:\n"
        f"{deep_link}\n"
        f"\n"
        f"If you did not expect this account, contact your hostel\n"
        f"administrator.\n"
    )

    esc = html.escape
    html_body = (
        '<!doctype html><html><body style="margin:0;padding:24px;'
        'background:#f4f5f7;font-family:-apple-system,Segoe UI,Roboto,'
        'Helvetica,Arial,sans-serif;">'
        '<table role="presentation" width="100%" cellpadding="0" '
        'cellspacing="0" style="max-width:520px;margin:0 auto;'
        'background:#ffffff;border-radius:12px;border:1px solid #e5e7eb;">'
        '<tr><td style="padding:28px;">'
        '<p style="margin:0;font-size:12px;letter-spacing:.08em;'
        'color:#6b7280;text-transform:uppercase;">DormPASS</p>'
        '<h1 style="margin:10px 0 18px 0;font-size:20px;color:#111827;">'
        'Activate your DormPASS account</h1>'
        f'<p style="margin:0 0 12px 0;font-size:15px;color:#374151;">'
        f'Hello {esc(student_name)},</p>'
        '<p style="margin:0 0 22px 0;font-size:15px;color:#374151;">'
        'Your hostel warden has created your DormPASS account. '
        'Click the button below to set your password and activate it.</p>'
        '<p style="margin:0 0 24px 0;">'
        f'<a href="{esc(web_link)}" style="display:inline-block;'
        'background:#1d4ed8;color:#ffffff;text-decoration:none;'
        'font-weight:600;font-size:15px;padding:12px 22px;border-radius:8px;">'
        'Activate DormPASS</a></p>'
        '<p style="margin:0 0 10px 0;font-size:13px;color:#6b7280;">'
        f'This activation link expires on {esc(expires)} and can be used '
        'only once.</p>'
        '<p style="margin:0 0 10px 0;font-size:13px;color:#6b7280;">'
        'Button not working? Open the DormPASS Student app, choose '
        'Activate, and paste this code:</p>'
        '<p style="margin:0 0 20px 0;font-size:13px;color:#111827;'
        'font-family:ui-monospace,Menlo,Consolas,monospace;'
        f'word-break:break-all;">{esc(plaintext_token)}</p>'
        '<p style="margin:0;font-size:13px;color:#6b7280;">'
        'If you did not expect this account, contact your hostel '
        'administrator.</p>'
        '</td></tr></table></body></html>'
    )
    return from_header, subject, text_body, html_body, deep_link, web_link


def _send_resend_email(
    *, from_header: str, to_email: str, subject: str,
    text_body: str, html_body: str,
) -> str:
    """Deliver through the Resend Email API (official SDK).

    Returns the provider message id ("" when Resend returned none). Raises
    on rejection — the caller maps that to ``failed`` with a token-free
    reason. The API key is set from settings and never logged; the request
    body (which contains the activation link) is never logged either.
    """
    if resend is None:
        raise RuntimeError(
            "the 'resend' package is not installed on this deployment "
            "(pip install resend)"
        )
    resend.api_key = settings.resend_api_key
    response = resend.Emails.send({  # type: ignore[arg-type]
        "from": from_header,
        "to": [to_email],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    })
    message_id = getattr(response, "id", None)
    if message_id is None and isinstance(response, dict):
        message_id = response.get("id")
    return str(message_id or "")


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

    if mode == "resend" and (
        not settings.resend_api_key or not settings.resend_from_email
    ):
        return ActivationEmailResult(
            STATUS_FAILED,
            "Resend is not fully configured: RESEND_API_KEY and "
            "RESEND_FROM_EMAIL must both be set when EMAIL_MODE=resend.",
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

    if mode == "resend":
        # The production path: Resend Email API over HTTPS. "sent" is
        # returned only when Resend ACCEPTS the message; the provider
        # message id is recorded for delivery tracking. The rendered
        # payload (which contains the activation link) and the API key
        # are never logged.
        try:
            from_header, subject, text_body, html_body, _, _ = (
                _render_resend_payload(
                    to_email=to_email,
                    student_name=student_name,
                    roll=roll,
                    plaintext_token=plaintext_token,
                    expires_at=expires_at,
                )
            )
            message_id = _send_resend_email(
                from_header=from_header,
                to_email=to_email,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
            )
        except Exception as exc:  # noqa: BLE001 - provider/network errors
            log.error(
                "activation email delivery via Resend failed for roll "
                "%s: %s: %s",
                roll,
                type(exc).__name__,
                exc,
            )
            return ActivationEmailResult(
                STATUS_FAILED, f"{type(exc).__name__}: {exc}"[:200]
            )
        log.info(
            "activation email for roll %s accepted by Resend (message "
            "id=%s, to=%s)",
            roll,
            message_id or "unknown",
            to_email,
        )
        return ActivationEmailResult(
            STATUS_SENT,
            (
                f"Accepted by Resend (message id {message_id})."
                if message_id
                else "Accepted by Resend."
            ),
            provider_id=message_id or None,
        )

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
