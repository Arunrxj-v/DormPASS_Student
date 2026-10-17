"""Application settings loaded from environment / .env (pydantic-settings)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Development-only fallback so a missing FACE_TEMPLATE_KEY never bricks local
# runs silently. Production deployments MUST set their own key via .env.
# NOTE: the value MUST be urlsafe-base64 of exactly 32 bytes (a valid Fernet
# key) — Fernet() rejects anything else. An earlier ASCII-phrase constant here
# caused 500s on every face enrollment in production once .env lost its key.
_DEV_FERNET_KEY = "ZG9ybXBhc3MtZGV2LWZhY2UtdGVtcGxhdGUta2V5ISE="


class Settings(BaseSettings):
    """Typed application configuration.

    Environment variables override .env values (pydantic-settings priority).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "HostelPass"
    app_version: str = "1.0.0"
    support_extension: str = "#442"

    database_url: str = "postgresql+psycopg://hostelpass:hostelpass@127.0.0.1:5433/hostelpass"

    jwt_secret: str = "dev-insecure-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_seconds: int = 1800  # 30 minutes

    # Google Sign-In (ID-token verification). The audience MUST be the OAuth
    # client id issued for this app; when empty, /auth/google returns 503 and
    # GET /config/public reports google_sso_enabled=false (derived from this,
    # so the app never shows a button the backend would reject).
    google_oauth_client_id: str = ""
    # Lifetime of a warden-issued password-setup link.
    activation_token_ttl_seconds: int = 7 * 24 * 3600  # 7 days
    # Warden hand-off (WhatsApp workflow): the RESPONSE to
    # POST /warden/students/{id}/activate and .../resend-activation carries the
    # freshly issued plaintext key so the issuing warden can copy it and send
    # it to the student directly. The key is returned ONLY at the issuance
    # moment, ONLY to the already-authorized issuer — never by any read
    # endpoint, never in logs or audit rows (only its SHA-256 hash is stored).
    # Set false to withhold it (email-only deployments); the warden app then
    # shows the email delivery outcome instead. PRODUCTION email-only
    # deployments (EMAIL_MODE=resend) MUST set this to false: the activation
    # link must travel by email, never in API responses.
    allow_inline_activation_token: bool = True

    # --- Email delivery (activation links) ----------------------------------
    # Explicit mode — behavior is never inferred from whether variables happen
    # to be set:
    #   off    -> no delivery attempted; the API reports
    #              email_status="not_configured" and never claims a send.
    #   log    -> development: the fully rendered email (including the
    #              activation link) is written to email_log_dir as an .eml file
    #              ("outbox" for local inspection). The token is NEVER written
    #              to application logs.
    #   resend -> PRODUCTION: delivered through the Resend Email API over
    #              HTTPS with the official Python SDK (RESEND_API_KEY +
    #              RESEND_FROM_EMAIL). "sent" is returned only when Resend
    #              accepts the message; the provider message id is recorded.
    #   smtp   -> alternative production backend (STARTTLS; implicit TLS on
    #              port 465). Kept for operators who already run an SMTP
    #              relay; the recommended production path is "resend".
    email_mode: str = "off"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "HostelPass"
    smtp_use_tls: bool = True
    # --- Resend Email API (EMAIL_MODE=resend) --------------------------------
    # Secrets come from the environment ONLY, never from source, never from
    # git-tracked files, never into logs.
    resend_api_key: str = ""
    # Sender — MUST be a sender/domain verified in the Resend account.
    resend_from_email: str = ""
    resend_from_name: str = "DormPASS"
    email_timeout_seconds: int = 10
    # Dev-only outbox directory for email_mode=log (relative to server dir).
    email_log_dir: str = "var/outbox"

    # Public base URL of this deployment (no trailing slash), e.g.
    # "https://hostelpass.example.edu" in production. Used to build the
    # activation link that goes INTO emails — students must never receive a
    # localhost URL. ACTIVATION_BASE_URL is accepted as an alias for the same
    # setting (reuse, not duplication: whichever of the two names the
    # deployment uses, it lands here).
    app_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices("APP_BASE_URL", "ACTIVATION_BASE_URL"),
    )

    @field_validator("email_mode")
    @classmethod
    def _validate_email_mode(cls, value: str) -> str:
        allowed = {"off", "log", "resend", "smtp"}
        if value not in allowed:
            raise ValueError(
                f"EMAIL_MODE must be one of {sorted(allowed)}, got {value!r}."
            )
        return value

    face_template_key: str = _DEV_FERNET_KEY

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"

    # In-process sliding-window rate limits (single API worker by design).
    rate_limit_verify_per_minute: int = 10
    rate_limit_login_per_minute: int = 5

    location_max_age_seconds: int = 90
    pass_threshold_percent: int = 85
    default_face_dim: int = 128

    # Institution-level curfew window shown on the sign-in screen (public
    # config). Hostel-specific windows in the DB are authoritative for
    # verification; these are display-only defaults, None => client shows its
    # honest "set by your hostel" fallback.
    curfew_window_start: str | None = None
    curfew_window_end: str | None = None
    curfew_timezone: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins parsed from the comma-separated setting."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
