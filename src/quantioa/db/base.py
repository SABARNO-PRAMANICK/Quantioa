"""
Declarative base for all ORM models.

All models inherit from this Base to share table metadata
and enable Alembic auto-detection.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(DeclarativeBase):
    """Base class for all Quantioa ORM models."""

    pass
