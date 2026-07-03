"""
Integration test fixtures using real PostgreSQL and Redis.
These tests are run against actual database and cache instances.
Falls back to SQLite when PostgreSQL is unavailable, and skips Redis-dependent tests
when Redis is unavailable.
"""

import logging
import os
from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.models import (
    Base,
)
from backend.database.models import (
    engine as prod_engine,
)

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/test_integration.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:16379")


def _postgres_reachable(url: str, timeout: int = 2) -> bool:
    """Check if PostgreSQL is reachable."""
    try:
        eng = create_engine(url, connect_args={"connect_timeout": timeout})
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


def _redis_reachable(url: str, timeout: int = 2) -> bool:
    """Check if Redis is reachable."""
    try:
        import redis

        r = redis.from_url(url, socket_connect_timeout=timeout, decode_responses=True)
        r.ping()
        r.close()
        return True
    except Exception:
        return False


USING_SQLITE = DATABASE_URL.startswith("sqlite")

if DATABASE_URL.startswith("postgresql"):
    if not _postgres_reachable(DATABASE_URL):
        logger.warning("PostgreSQL not reachable, falling back to SQLite")
        DATABASE_URL = "sqlite:////tmp/test_integration.db"
        USING_SQLITE = True

REDIS_AVAILABLE = False
if REDIS_URL:
    if _redis_reachable(REDIS_URL):
        REDIS_AVAILABLE = True
    else:
        logger.warning("Redis not reachable, Redis-dependent tests will be skipped")

# Override settings for integration tests
os.environ.setdefault("DATABASE_URL", DATABASE_URL)
os.environ.setdefault("REDIS_URL", REDIS_URL)
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("OTEL_ENABLED", "false")
os.environ.setdefault("ENABLE_AUTH", "false")

def _enable_sqlite_fk(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

if USING_SQLITE:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_fk)
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create all tables before tests, drop after."""
    from backend.database.models import run_migrations

    run_migrations()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _patch_engine():
    """Replace the production engine/session with test ones for the duration of tests."""
    with patch.object(prod_engine, "connect", engine.connect):
        with patch.object(prod_engine, "begin", engine.begin):
            with patch("backend.database.models.engine", engine):
                with patch("backend.database.models.SessionLocal", TestingSessionLocal):
                    yield


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a transactional database session rolled back after each test.

    Cleans all tables at the start to remove data left by API tests
    (which use a different session via the FastAPI app's get_db()).
    """
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f"DELETE FROM {table.name}"))
        conn.commit()

    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def clean_tables(db_session):
    """Clean all tables before each test (between transactions)."""
    for table in reversed(Base.metadata.sorted_tables):
        if USING_SQLITE:
            db_session.execute(text(f"DELETE FROM {table.name}"))
        else:
            db_session.execute(text(f"TRUNCATE {table.name} CASCADE"))
    db_session.commit()


@pytest.fixture(scope="session")
def event_loop():
    """Overrides the default function-scoped event loop for async fixtures."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def redis_client():
    """Provide a real Redis client for testing. Skips if Redis is unavailable."""
    if not REDIS_AVAILABLE:
        pytest.skip("Redis is not available")
    import redis.asyncio as aioredis

    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r.flushdb()
    yield r
    await r.flushdb()
    await r.close()


@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient connected to real services.

    Disables rate limiting, authentication, and OTel tracing to keep tests fast.
    Overrides service-layer dependencies with real implementations.
    """
    from backend.api.main import app

    # Disable rate limiting
    limiter = getattr(app.state, "limiter", None)
    if limiter:
        limiter.enabled = False

    # Clear any dependency overrides from previous tests
    app.dependency_overrides.clear()

    # Ensure auth returns a mock user when disabled
    if os.environ.get("ENABLE_AUTH", "true").lower() != "true":
        from unittest.mock import MagicMock

        from backend.api.auth import get_current_user

        mock_user = MagicMock()
        mock_user.username = "testuser"
        mock_user.is_active = True
        mock_user.is_superuser = False

        async def _mock_get_current_user():
            return mock_user

        app.dependency_overrides[get_current_user] = _mock_get_current_user

    with TestClient(app) as client:
        yield client


@pytest.fixture
def api_client(test_client) -> TestClient:
    """Alias for test_client - use when testing API endpoints."""
    return test_client


@pytest.fixture
def app_url() -> str:
    """Base URL for the API."""
    return "/api/v1"


@pytest.fixture
def sample_package_data() -> dict:
    """Sample package data for integration tests."""
    return {
        "name": "test-package",
        "ecosystem": "pypi",
        "version": "1.0.0",
        "description": "A test package for integration testing",
    }


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers",
        "requires_postgres: mark test as requiring PostgreSQL-specific features",
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests that require PostgreSQL when running on SQLite."""
    if not USING_SQLITE:
        return
    for item in items:
        if item.get_closest_marker("requires_postgres"):
            item.add_marker(
                pytest.mark.skip(
                    reason="Test requires PostgreSQL but running on SQLite"
                )
            )
