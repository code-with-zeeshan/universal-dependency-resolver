"""Data-access service layer — mediates between API and database models."""

from datetime import datetime
from typing import Any

from backend.database.models import APIKey, db_session


def authenticate_api_key(api_key: str) -> dict[str, Any] | None:
    """Look up an API key in the database and return its metadata, or None."""
    with db_session() as session:
        db_key = (
            session.query(APIKey)
            .filter(
                APIKey.key == api_key,
                APIKey.is_active,
            )
            .first()
        )
        if db_key and (not db_key.expires_at or db_key.expires_at > datetime.utcnow()):
            db_key.last_used_at = datetime.utcnow()
            db_key.usage_count = (db_key.usage_count or 0) + 1
            session.commit()
            scopes = db_key.scopes or []
            role = (
                "admin" if "admin" in scopes else "read-write" if "write" in scopes else "read-only"
            )
            return {
                "name": db_key.name,
                "role": role,
            }
        return None
