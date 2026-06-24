"""
Pytest configuration and shared fixtures for Universal Dependency Resolver tests.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, Generator
import json

# FastAPI testing
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment before importing app
os.environ.setdefault("ENABLE_CSRF", "false")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")

# Import your application
from backend.api.main import app
from backend.database.models import Base, get_db
from backend.core.cache import cache_manager


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
    """Set up test database"""
    Base.metadata.create_all(bind=engine)
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
    yield TestClient(app)


@pytest.fixture
def mock_cache():
    """Mock cache manager for testing"""
    with patch.object(
        cache_manager, "get", new_callable=AsyncMock
    ) as mock_get, patch.object(
        cache_manager, "set", new_callable=AsyncMock
    ) as mock_set, patch.object(
        cache_manager, "delete", new_callable=AsyncMock
    ) as mock_delete:
        mock_get.return_value = None
        mock_set.return_value = True
        mock_delete.return_value = True

        yield {"get": mock_get, "set": mock_set, "delete": mock_delete}


@pytest.fixture
def sample_package_data():
    """Sample package data for testing"""
    return {
        "name": "test-package",
        "ecosystem": "pypi",
        "version": "1.0.0",
        "description": "A test package",
        "homepage": "https://example.com",
        "license": "MIT",
        "dependencies": {"required": {"requests": ">=2.25.0", "click": ">=7.0"}},
    }


@pytest.fixture
def mock_external_apis():
    """Mock external API responses"""
    pypi_response = {
        "info": {
            "name": "requests",
            "version": "2.31.0",
            "summary": "Python HTTP for Humans.",
            "home_page": "https://requests.readthedocs.io",
            "license": "Apache 2.0",
        },
        "releases": {
            "2.31.0": [
                {
                    "filename": "requests-2.31.0-py3-none-any.whl",
                    "size": 62317,
                    "upload_time": "2023-05-22T14:56:27",
                }
            ]
        },
    }

    npm_response = {
        "name": "express",
        "version": "4.18.2",
        "description": "Fast, unopinionated, minimalist web framework",
        "homepage": "http://expressjs.com/",
        "license": "MIT",
        "versions": {
            "4.18.2": {
                "name": "express",
                "version": "4.18.2",
                "dependencies": {"accepts": "~1.3.8", "array-flatten": "1.1.1"},
            }
        },
    }

    return {"pypi": pypi_response, "npm": npm_response}


@pytest.fixture
def temp_requirements_file():
    """Create a temporary requirements.txt file for testing"""
    content = """
# Test requirements file
requests>=2.25.0
click>=7.0
numpy>=1.20.0
flask==2.3.3
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content.strip())
        temp_path = f.name

    yield temp_path

    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def temp_package_json():
    """Create a temporary package.json file for testing"""
    content = {
        "name": "test-project",
        "version": "1.0.0",
        "dependencies": {"express": "^4.18.0", "lodash": "^4.17.21"},
        "devDependencies": {"jest": "^29.0.0", "eslint": "^8.0.0"},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(content, f, indent=2)
        temp_path = f.name

    yield temp_path

    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def mock_subprocess():
    """Mock subprocess calls for system scanning"""
    with patch("subprocess.run") as mock_run:
        # Default successful response
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Mock output"
        mock_run.return_value.stderr = ""

        yield mock_run


@pytest.fixture
def authenticated_client(client):
    """Create an authenticated test client"""
    # Mock authentication for testing
    with patch("backend.api.auth.get_current_user") as mock_auth:
        mock_user = Mock()
        mock_user.id = 1
        mock_user.username = "testuser"
        mock_user.email = "test@example.com"
        mock_user.is_active = True
        mock_user.scopes = ["read:packages", "read:system"]

        mock_auth.return_value = mock_user
        yield client


@pytest.fixture
def sample_resolved_packages():
    """Sample resolved package data for export testing"""
    return {
        "flask": "2.3.3",
        "werkzeug": "2.3.7",
        "jinja2": "3.1.2",
        "click": "8.1.7",
        "markupsafe": "2.1.3",
    }


# Async test helpers
@pytest.fixture
def async_mock():
    """Helper to create async mocks"""

    def _async_mock(*args, **kwargs):
        mock = AsyncMock(*args, **kwargs)
        return mock

    return _async_mock


# Test data loaders
@pytest.fixture
def load_test_fixture():
    """Helper to load test fixtures from JSON files"""

    def _load_fixture(filename: str) -> Dict[Any, Any]:
        fixture_path = Path(__file__).parent / "fixtures" / filename
        with open(fixture_path, "r") as f:
            return json.load(f)

    return _load_fixture


# Environment variable mocking
@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing"""
    test_env = {
        "DATABASE_URL": "sqlite:///./test.db",
        "REDIS_URL": "redis://localhost:6379",
        "SECRET_KEY": "test-secret-key",
        "TESTING": "true",
        "CACHE_TTL": "300",
        "RATE_LIMIT_PER_MINUTE": "100",
    }

    with patch.dict(os.environ, test_env):
        yield test_env


# Performance testing helpers
@pytest.fixture
def performance_timer():
    """Helper for performance testing"""
    import time

    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None

        def start(self):
            self.start_time = time.time()

        def stop(self):
            self.end_time = time.time()

        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None

    return Timer()


# Cleanup helpers
@pytest.fixture(autouse=True)
def disable_rate_limiter():
    was_enabled = getattr(app.state, "limiter", None)
    if was_enabled:
        app.state.limiter.enabled = False
    yield
    if was_enabled:
        app.state.limiter.enabled = True


@pytest.fixture(autouse=True)
def cleanup_cache():
    """Automatically cleanup cache after each test"""
    yield
    # CacheManager has no clear() method, so this is intentionally a no-op.
    # If clear_pattern were needed, it would need an event loop-aware approach.


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
