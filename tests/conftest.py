"""
Pytest configuration and shared fixtures for Universal Dependency Resolver tests.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

# FastAPI testing
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment before importing app
os.environ.setdefault("ENABLE_CSRF", "false")
os.environ.setdefault("ENABLE_AUTH", "false")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")

# Import your application
from backend.api.main import app
from backend.core.cache import cache_manager
from backend.database.models import Base, get_db

# Test Database Setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# Override dependencies
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Set up test database via Alembic migrations"""
    from backend.database.models import run_migrations

    run_migrations()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Create a fresh database session for each test"""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client():
    """Create a test client for FastAPI (skip lifespan to avoid DB requirement)"""
    return TestClient(app)


# Cleanup helpers
@pytest.fixture(autouse=True)
def disable_rate_limiter():
    was_enabled = getattr(app.state, "limiter", None)
    if was_enabled:
        app.state.limiter.enabled = False
    yield
    if was_enabled:
        app.state.limiter.enabled = True


# Markers for different test types
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "e2e: mark test as an end-to-end test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line(
        "markers", "external_api: mark test as requiring external API access"
    )


# Test collection customization
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically"""
    for item in items:
        # Add unit marker to unit tests
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Add integration marker to integration tests
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        # Add e2e marker to e2e tests
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
