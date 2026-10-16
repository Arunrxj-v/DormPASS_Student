"""Audit log writer — every admin mutation and accepted verify leaves a row."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditLog


def write_audit(
    db: Session,
    *,
    actor_user_id: Any,
    actor_label: str | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Append an audit row inside the caller's transaction (no commit here).

    ``details`` must never contain embeddings, passwords or tokens.
    """
    entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
    db.add(entry)
    return entry
