"""Data-access service layer — mediates between API and database models."""

from datetime import UTC, datetime
from typing import Any

from passlib.context import CryptContext
from sqlalchemy import text

from backend.database.models import APIKey, db_session

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def authenticate_api_key(raw_key: str) -> dict[str, Any] | None:
    """Look up an API key in the database and return its metadata, or None.

    API keys are stored as bcrypt hashes; this function iterates active
    keys and verifies each with ``passlib``.
    """
    with db_session() as session:
        active_keys = session.query(APIKey).filter(APIKey.is_active).all()

        now = datetime.now(UTC).replace(tzinfo=None)
        db_key = None
        for k in active_keys:
            if k.expires_at and k.expires_at < now:
                continue
            if _pwd_context.verify(raw_key, k.key):
                db_key = k
                break

        if db_key:
            db_key.last_used_at = now
            # Atomic increment — avoids read-modify-write race under concurrency
            session.execute(
                text(
                    "UPDATE api_keys SET usage_count = COALESCE(usage_count, 0) + 1 WHERE id = :id"
                ),
                {"id": db_key.id},
            )
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
