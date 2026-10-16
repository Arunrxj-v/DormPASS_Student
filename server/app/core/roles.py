"""Role and enrollment-lifecycle constants.

Single source of truth for the strings stored in ``users.role`` and
``students.enrollment_status`` so no module invents its own spelling.
"""

from __future__ import annotations

# --- roles (users.role) -----------------------------------------------------
ROLE_ADMIN = "admin"
ROLE_WARDEN = "warden"
ROLE_STUDENT = "student"

VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_WARDEN, ROLE_STUDENT})

# Roles allowed to reach warden-scoped management endpoints.
STAFF_ROLES = frozenset({ROLE_ADMIN, ROLE_WARDEN})


# --- account status (users.account_status) ---------------------------------
ACCOUNT_ACTIVE = "active"
ACCOUNT_INACTIVE = "inactive"


# --- enrollment lifecycle (students.enrollment_status) ----------------------
# CREATED -> DETAILS_VERIFIED -> FACE_ENROLLED -> ACCOUNT_PROVISIONED -> ACTIVE
# (SUSPENDED can be entered from ACTIVE and reversed by an admin/warden.)
STATUS_CREATED = "created"
STATUS_DETAILS_VERIFIED = "details_verified"
STATUS_FACE_ENROLLED = "face_enrolled"
STATUS_ACCOUNT_PROVISIONED = "account_provisioned"
STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"

#: Ordered forward transitions. Nothing may skip a stage except the explicit
#: activation step, which is the only transition that also flips the login
#: account to ``active``.
FORWARD_TRANSITIONS: dict[str, str] = {
    STATUS_CREATED: STATUS_DETAILS_VERIFIED,
    STATUS_DETAILS_VERIFIED: STATUS_FACE_ENROLLED,
    STATUS_FACE_ENROLLED: STATUS_ACCOUNT_PROVISIONED,
    STATUS_ACCOUNT_PROVISIONED: STATUS_ACTIVE,
}

VALID_ENROLLMENT_STATUSES = frozenset(
    {
        STATUS_CREATED,
        STATUS_DETAILS_VERIFIED,
        STATUS_FACE_ENROLLED,
        STATUS_ACCOUNT_PROVISIONED,
        STATUS_ACTIVE,
        STATUS_SUSPENDED,
    }
)

#: Statuses from which a student may NOT authenticate.
#: Only ACTIVE students sign in; everything else is "contact your warden".
LOGINABLE_STATUSES = frozenset({STATUS_ACTIVE})

#: Statuses a warden/admin may set directly through activate/suspend controls.
SUSPENDABLE_FROM = frozenset(
    {STATUS_DETAILS_VERIFIED, STATUS_FACE_ENROLLED, STATUS_ACCOUNT_PROVISIONED, STATUS_ACTIVE}
)
