"""College email validation and normalization.

The ONLY permitted student email domain is ``ceconline.edu`` — matched on the
exact hostname, never a substring test. Addresses are lowercased and trimmed
before uniqueness checks so ``A@ceconline.edu`` and ``a@ceconline.edu`` cannot
both be registered.
"""

from __future__ import annotations

import re

#: Exact permitted hostname (no subdomain wildcards, no partial matches).
PERMITTED_EMAIL_DOMAIN = "ceconline.edu"

# Pragmatic address shape: one @, non-empty local part, no whitespace, dots
# allowed but not leading/trailing/consecutive in the local part.
_ADDRESS_RE = re.compile(
    r"^(?=.{1,64}$)(?!\.)[A-Za-z0-9._%+\-]+(?<!\.)@"
    r"(?=.{1,253}$)(?!\.)[A-Za-z0-9.\-]+(?<!\.)$"
)


class EmailValidationError(ValueError):
    """Raised for any address that is not a valid @ceconline.edu address."""


def normalize_email(raw: str) -> str:
    """Canonical form used for storage and uniqueness comparisons."""
    return raw.strip().lower()


def validate_college_email(raw: str) -> str:
    """Validate + normalize a college email, or raise ``EmailValidationError``.

    Exact-domain rule: the part after the final ``@`` must equal
    ``ceconline.edu`` exactly. This rejects look-alikes such as
    ``a@ceconline.com``, ``a@ceconline.edu.example.com`` and ``a@xceconline.edu``.
    """
    if not isinstance(raw, str):
        raise EmailValidationError("Email must be text.")
    email = normalize_email(raw)
    if not email:
        raise EmailValidationError("Email is required.")
    if not _ADDRESS_RE.match(email):
        raise EmailValidationError("Enter a valid email address.")

    local, _, hostname = email.rpartition("@")
    if not local or not hostname:
        raise EmailValidationError("Enter a valid email address.")
    if hostname != PERMITTED_EMAIL_DOMAIN:
        raise EmailValidationError(
            f"Only @{PERMITTED_EMAIL_DOMAIN} college email addresses are accepted."
        )
    return email
