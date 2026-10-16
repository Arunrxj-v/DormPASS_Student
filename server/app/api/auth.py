"""Auth endpoints: login, google, activate, refresh, logout, me (docs/API.md).

Identity always comes from the server's verified context. There is NO
registration endpoint here — student accounts are created exclusively by an
authenticated warden via ``/warden/students``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import AppError, invalid_credentials
from ..core.roles import LOGINABLE_STATUSES, ROLE_STUDENT
from ..core.security import create_access_token, hash_password, verify_password
from ..db.session import get_session
from ..models import RevokedToken, Student, User
from ..schemas import (
    ActivateAccountRequest,
    GoogleLoginRequest,
    LoginRequest,
    LoginResponse,
    StudentPublic,
)
from ..services import activation as activation_service
from ..services import google_auth
from ..services.audit import write_audit
from ..services.students import build_student_public, find_login_user, get_student_by_user
from .deps import get_auth_context, login_rate_limit

router = APIRouter(tags=["auth"])


def _issue_login(db: Session, user: User, student: Student | None,
                 *, method: str) -> LoginResponse:
    """Shared token issuance after a credential has been fully verified."""
    token, _jti, expires_in = create_access_token(str(user.id), user.role)
    write_audit(
        db,
        actor_user_id=user.id,
        actor_label=user.username,
        action="auth.login",
        target_type="user",
        target_id=str(user.id),
        details={"method": method, "role": user.role},
    )
    db.commit()
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        student=build_student_public(user, student),
    )


def _assert_signin_allowed(user: User, student: Student | None) -> None:
    """Enforce account status + enrollment lifecycle before any token is minted."""
    if user.role == ROLE_STUDENT and student is not None:
        # Specific lifecycle states are reported ahead of the generic flag so
        # a suspended student sees the real reason.
        if student.enrollment_status == "suspended":
            raise AppError(403, "account_suspended",
                           "This account is suspended. Contact your hostel warden.")
        if student.enrollment_status not in LOGINABLE_STATUSES:
            raise AppError(403, "account_not_activated",
                           "Your HostelPass account has not been activated. "
                           "Please contact your hostel warden.")
    if user.account_status != "active":
        # A deactivated staff account has no "warden" to contact; that copy is
        # only correct for students, so name the right office for each role.
        contact = "your hostel warden" if user.role == ROLE_STUDENT else "an administrator"
        raise AppError(403, "account_inactive",
                       f"Account is inactive. Contact {contact}.")
    if user.role == ROLE_STUDENT and student is None:
        raise AppError(403, "account_not_activated",
                       "Your HostelPass account has not been activated. "
                       "Please contact your hostel warden.")


@router.post("/auth/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_session),
) -> LoginResponse:
    """Exchange (college email | roll number, password) for a 30-min HS256 token.

    A single generic error covers unknown user, wrong password and
    unprovisioned accounts, so the endpoint cannot enumerate addresses.
    """
    identifier = payload.identifier
    login_rate_limit(request, identifier)

    user = find_login_user(db, identifier)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise invalid_credentials()

    student = get_student_by_user(db, user)
    _assert_signin_allowed(user, student)
    return _issue_login(db, user, student, method="password")


@router.post("/auth/google", response_model=LoginResponse)
def google_login(
    payload: GoogleLoginRequest,
    request: Request,
    db: Session = Depends(get_session),
) -> LoginResponse:
    """Sign in an EXISTING provisioned student via a Google ID token.

    The server verifies the token itself (signature/issuer/audience/expiry/
    verified-email/domain). It never creates or links an account: an
    unrecognised Google identity is rejected with the same message as an
    unprovisioned one.
    """
    identity = google_auth.verify_google_id_token(payload.id_token)
    login_rate_limit(request, identity.email)
    user, student = google_auth.authenticate_google_user(db, identity)
    return _issue_login(db, user, student, method="google")


@router.post("/auth/activate", response_model=LoginResponse)
def activate(
    payload: ActivateAccountRequest,
    request: Request,
    db: Session = Depends(get_session),
) -> LoginResponse:
    """Redeem a warden-issued, single-use activation token and set a password.

    The token — not the request body — determines which account is activated,
    and only a student already at ``account_provisioned`` may pass.
    """
    login_rate_limit(request, "activate")
    record = activation_service.redeem_activation_token(db, payload.token)
    password_hash = hash_password(payload.password)
    user, student = activation_service.activate_student_account(
        db, record=record, password_hash=password_hash
    )
    write_audit(
        db,
        actor_user_id=user.id,
        actor_label=student.student_id,
        action="auth.activate",
        target_type="student",
        target_id=str(student.id),
        details={"method": "activation_token"},
    )
    db.commit()
    return _issue_login(db, user, student, method="activation")


@router.post("/auth/refresh", response_model=LoginResponse)
def refresh(
    request: Request,
    db: Session = Depends(get_session),
    ctx: Any = Depends(get_auth_context),
) -> LoginResponse:
    """Mint a fresh access token from a still-valid, unrevoked one (sliding).

    Logout still invalidates the presented jti; role/status are re-read from
    the database, never from the token payload.
    """
    user = ctx.user
    login_rate_limit(request, user.username)
    student = get_student_by_user(db, user)
    _assert_signin_allowed(user, student)
    return _issue_login(db, user, student, method="refresh")


@router.post("/auth/logout", status_code=204)
def logout(
    db: Session = Depends(get_session),
    ctx: Any = Depends(get_auth_context),
) -> Response:
    """Revoke the presented token's jti until its natural expiry."""
    existing = db.scalar(select(RevokedToken.id).where(RevokedToken.jti == ctx.claims.jti))
    if existing is None:
        db.add(
            RevokedToken(
                jti=ctx.claims.jti,
                expires_at=datetime.fromtimestamp(ctx.claims.expires_at, tz=timezone.utc),
            )
        )
        db.commit()
    return Response(status_code=204)


@router.get("/auth/me", response_model=StudentPublic)
def me(
    db: Session = Depends(get_session),
    ctx: Any = Depends(get_auth_context),
) -> StudentPublic:
    """The authenticated identity, re-read from the database."""
    student = get_student_by_user(db, ctx.user)
    return build_student_public(ctx.user, student)
