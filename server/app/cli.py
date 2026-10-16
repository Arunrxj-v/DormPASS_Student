"""Server-side CLI for privileged one-off operations.

    python -m app.cli create-admin --username admin          # prompts (no echo)
    python -m app.cli create-admin --username admin --password-stdin

There is deliberately NO HTTP endpoint that creates an administrator: bootstrap
needs direct database access, so it can only be run by someone who already has
a shell on the server. There is no default password, no "first login promotes
you to admin" path, and the password is never accepted as a command-line
argument (so it never lands in shell history or ``ps`` output).

Password handling:
  * interactive terminal -> prompted twice with getpass (never echoed),
  * ``--password-stdin``  -> read one line from stdin, never echoed, never
    printed (for one-time scripted bootstrap over ``ssh``/``docker exec``),
  * anything else        -> refused; we never print a generated password.

Warden accounts are NOT created here. They come from an authenticated admin
via ``POST /api/v1/admin/wardens`` (Admin Console), which records an audit row
naming the acting administrator.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .core.security import hash_password
from .db.session import SessionFactory
from .models import User
from .services.audit import write_audit

MIN_PASSWORD = 12
MAX_USERNAME = 64


class CliError(Exception):
    """A refusal the CLI should print verbatim, without a traceback."""


# --------------------------------------------------------------------------
# Pure(ish) core: takes an already-read password so tests can drive it
# --------------------------------------------------------------------------


def create_admin_account(
    db: Session,
    *,
    username: str,
    password: str,
    force: bool = False,
) -> tuple[str, User]:
    """Create the first administrator, or reset one account when ``force``.

    Returns ``(action, user)`` where action is ``admin.bootstrap`` or
    ``admin.password_reset``. Raises :class:`CliError` on any refusal; the
    caller is responsible for committing.

    Safety properties (all enforced here, not in the argument parser):
      * refuses whenever ANY administrator already exists, so a second
        bootstrap can never silently produce a parallel admin,
      * ``--force`` only resets the password of an *existing* admin account --
        it never promotes a warden/student and never touches other admins,
      * an already-used username belonging to a different role is never
        overwritten,
      * the password is hashed (bcrypt) before it ever reaches the database,
        and no part of it is returned.
    """
    username = username.strip()
    if not username:
        raise CliError("Username must not be empty.")
    if len(username) > MAX_USERNAME:
        raise CliError(f"Username must be at most {MAX_USERNAME} characters.")
    if any(ch.isspace() for ch in username):
        raise CliError("Username must not contain whitespace.")
    if len(password) < MIN_PASSWORD:
        raise CliError(f"Password must be at least {MIN_PASSWORD} characters.")

    admins = list(db.scalars(select(User).where(func.lower(User.role) == "admin")).all())
    by_name = next(
        (u for u in admins if u.username.lower() == username.lower()), None
    )

    if not admins:
        # First bootstrap: nothing to preserve, but still refuse a username
        # already used by a non-admin account.
        clash = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
        if clash is not None:
            raise CliError(
                f"Username '{username}' already belongs to a {clash.role} account "
                "and will not be overwritten. Pick another username."
            )
        user = User(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            account_status="active",
        )
        db.add(user)
        db.flush()
        return "admin.bootstrap", user

    if not force:
        names = ", ".join(u.username for u in admins)
        raise CliError(
            f"An administrator already exists ({names}).\n"
            "Refusing to create another. Re-run with --force to reset the "
            "password of the named existing admin."
        )

    if by_name is None:
        # --force must name an account that exists.
        clash = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
        if clash is not None:
            raise CliError(
                f"'{username}' is a {clash.role} account, not an administrator. "
                "--force only resets an existing admin's password; it will not "
                "promote another role."
            )
        existing_names = ", ".join(u.username for u in admins)
        raise CliError(
            f"No administrator named '{username}'. Existing: {existing_names}. "
            "--force only resets an existing admin's password."
        )

    by_name.password_hash = hash_password(password)
    by_name.account_status = "active"
    by_name.role = "admin"
    return "admin.password_reset", by_name


def run_create_admin(
    db: Session,
    *,
    username: str,
    password: str,
    force: bool,
) -> str:
    """Create/reset + audit + commit. Returns the human-readable result line."""
    action, user = create_admin_account(
        db, username=username, password=password, force=force
    )
    write_audit(
        db,
        actor_user_id=user.id,
        actor_label=user.username,
        action=action,
        target_type="user",
        target_id=str(user.id),
        details={"source": "cli"},
    )
    db.commit()
    if action == "admin.bootstrap":
        return f"Administrator '{user.username}' is ready."
    return f"Administrator '{user.username}' password reset and reactivated."


# --------------------------------------------------------------------------
# I/O layer (never echoes or prints a password)
# --------------------------------------------------------------------------


def _read_password(*, password_stdin: bool, prompt: str) -> str:
    """Read a password without ever writing it back out.

    * ``--password-stdin``: one line from stdin (scripted bootstrap over ssh).
    * interactive: prompted twice with ``getpass``.
    * non-interactive without the flag: refused, because the alternative the
      old script used -- printing a generated password -- violates the rule
      that passwords are never printed.
    """
    if password_stdin:
        line = sys.stdin.readline()
        if not line:
            raise CliError("--password-stdin was given but stdin was empty.")
        return line.rstrip("\n")

    if not sys.stdin.isatty():
        raise CliError(
            "stdin is not a terminal. Re-run interactively, or pipe the "
            "password with --password-stdin (it is never echoed or logged)."
        )

    import getpass

    first = getpass.getpass(prompt)
    second = getpass.getpass("Repeat password: ")
    if first != second:
        raise CliError("Passwords do not match.")
    return first


def _cmd_create_admin(args: argparse.Namespace) -> int:
    session = SessionFactory()
    try:
        password = _read_password(
            password_stdin=args.password_stdin, prompt="New admin password: "
        )
        try:
            print(run_create_admin(
                session, username=args.username, password=password, force=args.force
            ))
        except CliError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 1
        return 0
    finally:
        session.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="HostelPass server-side administrative commands.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser(
        "create-admin",
        help="create (or --force reset) the initial administrator account",
        description=(
            "One-time server-side bootstrap for the FIRST administrator. "
            "There is no HTTP endpoint for this. Refuses if an administrator "
            "already exists unless --force resets that named account's "
            "password. The password is never accepted as an argument, echoed, "
            "or printed."
        ),
    )
    p_admin.add_argument("--username", default="admin", help="login name for the admin")
    p_admin.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from stdin instead of prompting (never echoed)",
    )
    p_admin.add_argument(
        "--force",
        action="store_true",
        help="reset the password of an EXISTING admin instead of refusing",
    )
    p_admin.set_defaults(func=_cmd_create_admin)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
