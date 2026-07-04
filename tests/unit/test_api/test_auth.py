"""Tests for auth routes (login, register, refresh, logout, profile)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend.api.auth import AuthService, get_current_user
from backend.api.routes.auth import router as auth_router
from backend.orchestrator.db_service import User

_mock_user = User(
    id=1,
    username="testuser",
    email="test@example.com",
    full_name="Test User",
    is_active=True,
    hashed_password="hashed",
    scopes=["read"],
)

_test_app = FastAPI()
_test_app.state.limiter = Limiter(key_func=get_remote_address)
_test_app.state.limiter.enabled = False
_test_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
_test_app.add_middleware(SlowAPIMiddleware)
_test_app.include_router(auth_router, prefix="/api/v1/auth")


@pytest.fixture
def client():
    return TestClient(_test_app)


@pytest.fixture
def mock_get_current_user():
    """Override get_current_user to return a mock user."""
    async def _override():
        return _mock_user
    _test_app.dependency_overrides.clear()
    _test_app.dependency_overrides[get_current_user] = _override
    yield
    _test_app.dependency_overrides.clear()


class TestRegister:
    def test_register_success(self, client):
        with patch.object(AuthService, "register_user", new_callable=AsyncMock) as mock_reg:
            mock_reg.return_value = {
                "id": 2,
                "username": "newuser",
                "email": "new@example.com",
                "full_name": None,
                "is_active": True,
                "scopes": [],
            }
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "username": "newuser",
                    "email": "new@example.com",
                    "password": "securepass123",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["username"] == "newuser"
            assert data["email"] == "new@example.com"
            mock_reg.assert_called_once()

    def test_register_missing_fields(self, client):
        response = client.post("/api/v1/auth/register", json={"username": "newuser"})
        assert response.status_code == 422

    def test_register_duplicate_user(self, client):
        with patch.object(AuthService, "register_user", new_callable=AsyncMock) as mock_reg:
            from fastapi import HTTPException, status
            mock_reg.side_effect = HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already registered",
            )
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "username": "existing",
                    "email": "existing@example.com",
                    "password": "securepass123",
                },
            )
            assert response.status_code == 400
            assert "already registered" in response.text

    def test_register_short_password(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "new@example.com",
                "password": "short",
            },
        )
        assert response.status_code == 422


class TestLogin:
    def test_login_success(self, client):
        with patch.object(AuthService, "login", new_callable=AsyncMock) as mock_login:
            mock_login.return_value = MagicMock(
                access_token="test-access-token",
                refresh_token="test-refresh-token",
                token_type="bearer",
                expires_in=3600,
            )
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "testuser", "password": "correctpassword"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["access_token"] == "test-access-token"
            assert data["refresh_token"] == "test-refresh-token"
            assert data["token_type"] == "bearer"

    def test_login_invalid_credentials(self, client):
        with patch.object(AuthService, "login", new_callable=AsyncMock) as mock_login:
            from fastapi import HTTPException, status
            mock_login.side_effect = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
            )
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "wrong", "password": "wrong"},
            )
            assert response.status_code == 401

    def test_login_missing_password(self, client):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser"},
        )
        assert response.status_code == 422


class TestToken:
    def test_token_endpoint_success(self, client):
        with patch.object(AuthService, "authenticate_user", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = {
                "id": 1,
                "username": "testuser",
                "email": "test@example.com",
                "full_name": None,
                "is_active": True,
                "scopes": [],
                "hashed_password": "...",
            }
            response = client.post(
                "/api/v1/auth/token",
                data={"username": "testuser", "password": "correctpassword"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

    def test_token_invalid_credentials(self, client):
        with patch.object(AuthService, "authenticate_user", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = None
            response = client.post(
                "/api/v1/auth/token",
                data={"username": "wrong", "password": "wrong"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status_code == 401


class TestRefreshToken:
    def test_refresh_success(self, client):
        with patch.object(AuthService, "refresh_token", new_callable=AsyncMock) as mock_ref:
            mock_ref.return_value = MagicMock(
                access_token="new-access-token",
                token_type="bearer",
                refresh_token=None,
                expires_in=3600,
            )
            response = client.post(
                "/api/v1/auth/refresh",
                params={"refresh_token": "valid-refresh-token"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["access_token"] == "new-access-token"

    def test_refresh_invalid_token(self, client):
        with patch.object(AuthService, "refresh_token", new_callable=AsyncMock) as mock_ref:
            from fastapi import HTTPException, status
            mock_ref.side_effect = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
            response = client.post(
                "/api/v1/auth/refresh",
                params={"refresh_token": "invalid-token"},
            )
            assert response.status_code == 401


class TestLogout:
    def test_logout_success(self, client):
        async def _override():
            return _mock_user
        _test_app.dependency_overrides.clear()
        _test_app.dependency_overrides[get_current_user] = _override
        try:
            response = client.post("/api/v1/auth/logout")
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Successfully logged out"
        finally:
            _test_app.dependency_overrides.clear()

    def test_logout_unauthorized(self, client):
        async def _override():
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        _test_app.dependency_overrides.clear()
        _test_app.dependency_overrides[get_current_user] = _override
        try:
            response = client.post("/api/v1/auth/logout")
            assert response.status_code == 401
        finally:
            _test_app.dependency_overrides.clear()



