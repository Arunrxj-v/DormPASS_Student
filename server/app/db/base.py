"""Declarative ORM base (SQLAlchemy 2.0 typed style)."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all HostelPass ORM models."""
