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
    "authenticate_api_key",
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


def authenticate_api_key(api_key: str) -> dict[str, Any] | None:
    """Look up an API key in the database via the data-access service layer.

    Lazy-imports from ``backend.database.service`` to avoid circular
    dependencies at module-load time.
    """
    from backend.database.service import authenticate_api_key as _auth

    return _auth(api_key)
