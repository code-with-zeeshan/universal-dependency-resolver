"""Database operations service — wraps DB access for API consumption.

This module is the single point of contact between the API layer and
the database layer, enforcing the import architecture rule that
api/ must not import from database/ directly.
"""

from typing import Any

from backend.database.compatibility_db import CompatibilityDB
from backend.database.models import (
    APIKey,
    User,
    check_db_health,
    db_session,
    get_engine,
)

__all__ = [
    "APIKey",
    "CompatibilityDB",
    "User",
    "check_health",
    "db_session",
    "get_db_engine",
]


def get_db_engine():
    """Get the SQLAlchemy engine instance."""
    return get_engine()


def check_health() -> dict[str, Any]:
    """Check database health."""
    return check_db_health()
