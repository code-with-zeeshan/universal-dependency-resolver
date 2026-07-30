"""Tests for auth routes (all 15 endpoints)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend.api.auth import AuthService, APIKeyCreate, get_current_user
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

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        _test_app.dependency_overrides.clear()
        _test_app.dependency_overrides[get_current_user] = _override
        try:
            response = client.post("/api/v1/auth/logout")
            assert response.status_code == 401
        finally:
            _test_app.dependency_overrides.clear()


class TestProfile:
    """Tests for GET/PUT /api/v1/auth/profile."""

    def test_get_profile(self, client, mock_get_current_user):
        response = client.get("/api/v1/auth/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert data["full_name"] == "Test User"

    def test_get_profile_unauthorized(self, client):
        async def _deny():
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        _test_app.dependency_overrides.clear()
        _test_app.dependency_overrides[get_current_user] = _deny
        try:
            response = client.get("/api/v1/auth/profile")
            assert response.status_code == 401
        finally:
            _test_app.dependency_overrides.clear()

    def test_update_profile(self, client, mock_get_current_user):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "testuser"
        mock_user.email = "test@example.com"
        mock_user.full_name = "Updated Name"
        mock_user.is_active = True
        mock_user.scopes = ["read"]
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        with patch("backend.orchestrator.db_service.db_session") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_db
            response = client.put(
                "/api/v1/auth/profile",
                json={"full_name": "Updated Name"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["full_name"] == "Updated Name"

    def test_update_profile_email_taken(self, client, mock_get_current_user):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "testuser"
        mock_user.email = "old@example.com"
        mock_user.full_name = "Test User"
        mock_user.is_active = True
        mock_user.scopes = ["read"]
        mock_other = MagicMock(id=2, email="taken@example.com")
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_user,
            mock_other,
        ]
        with patch("backend.orchestrator.db_service.db_session") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_db
            response = client.put(
                "/api/v1/auth/profile",
                json={"email": "taken@example.com"},
            )
            assert response.status_code == 400
            assert "already in use" in response.text


class TestChangePassword:
    """Tests for POST /api/v1/auth/change-password."""

    def test_change_password_success(self, client, mock_get_current_user):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.hashed_password = "hashed_current"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        with (
            patch("backend.orchestrator.db_service.db_session") as mock_ctx,
            patch("backend.api.auth.verify_password", return_value=True) as mock_verify,
            patch("backend.api.auth.get_password_hash", return_value="hashed_new"),
        ):
            mock_ctx.return_value.__enter__.return_value = mock_db
            response = client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "correct", "new_password": "newpass123"},
            )
            assert response.status_code == 200
            assert "changed successfully" in response.text
            mock_verify.assert_called_once_with("correct", "hashed_current")

    def test_change_password_wrong_current(self, client, mock_get_current_user):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.hashed_password = "hashed_current"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        with (
            patch("backend.orchestrator.db_service.db_session") as mock_ctx,
            patch("backend.api.auth.verify_password", return_value=False),
        ):
            mock_ctx.return_value.__enter__.return_value = mock_db
            response = client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "wrong", "new_password": "newpass123"},
            )
            assert response.status_code == 400
            assert "incorrect" in response.text.lower()

    def test_change_password_unauthorized(self, client):
        async def _deny():
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        _test_app.dependency_overrides.clear()
        _test_app.dependency_overrides[get_current_user] = _deny
        try:
            response = client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "x", "new_password": "y"},
            )
            assert response.status_code == 401
        finally:
            _test_app.dependency_overrides.clear()


class TestApiKeys:
    """Tests for /api/v1/auth/api-keys endpoints."""

    def test_get_api_keys_empty(self, client, mock_get_current_user):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        with patch("backend.orchestrator.db_service.db_session") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_db
            response = client.get("/api/v1/auth/api-keys")
            assert response.status_code == 200
            assert response.json() == []

    def test_get_api_keys(self, client, mock_get_current_user):
        from datetime import datetime, timezone

        mock_key = MagicMock()
        mock_key.id = 1
        mock_key.name = "test-key"
        mock_key.key = "abc12345"
        mock_key.description = "test"
        mock_key.scopes = ["read"]
        mock_key.created_at = datetime.now(timezone.utc)
        mock_key.expires_at = None
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_key]
        with patch("backend.orchestrator.db_service.db_session") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_db
            response = client.get("/api/v1/auth/api-keys")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["name"] == "test-key"
            assert data[0]["id"] == 1
            assert data[0]["key"].endswith("12345")

    def test_create_api_key(self, client, mock_get_current_user):
        from datetime import datetime, timezone

        mock_key = MagicMock()
        mock_key.id = 1
        mock_key.name = "new-key"
        mock_key.key = "udr_abc123decoded"
        mock_key.description = None
        mock_key.scopes = []
        mock_key.created_at = datetime.now(timezone.utc)
        mock_key.expires_at = None
        with patch.object(AuthService, "create_api_key", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = (mock_key, "udr_raw_secret_key")
            response = client.post(
                "/api/v1/auth/api-keys",
                json={"name": "new-key"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "new-key"
            assert data["key"] == "udr_raw_secret_key"
            mock_create.assert_called_once()

    def test_create_api_key_validation(self, client, mock_get_current_user):
        response = client.post("/api/v1/auth/api-keys", json={"name": "ab"})
        assert response.status_code == 422

    def test_revoke_api_key(self, client, mock_get_current_user):
        with patch.object(AuthService, "revoke_api_key", new_callable=AsyncMock) as mock_revoke:
            mock_revoke.return_value = True
            response = client.delete("/api/v1/auth/api-keys/1")
            assert response.status_code == 200
            assert "revoked" in response.text
            mock_revoke.assert_called_once()

    def test_revoke_api_key_not_found(self, client, mock_get_current_user):
        with patch.object(AuthService, "revoke_api_key", new_callable=AsyncMock) as mock_revoke:
            mock_revoke.return_value = False
            response = client.delete("/api/v1/auth/api-keys/999")
            assert response.status_code == 404

    def test_revoke_api_key_unauthorized(self, client):
        async def _deny():
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        _test_app.dependency_overrides.clear()
        _test_app.dependency_overrides[get_current_user] = _deny
        try:
            response = client.delete("/api/v1/auth/api-keys/1")
            assert response.status_code == 401
        finally:
            _test_app.dependency_overrides.clear()


class TestVerify:
    """Tests for GET /api/v1/auth/verify."""

    def test_verify_success(self, client, mock_get_current_user):
        response = client.get("/api/v1/auth/verify")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["username"] == "testuser"

    def test_verify_unauthorized(self, client):
        async def _deny():
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        _test_app.dependency_overrides.clear()
        _test_app.dependency_overrides[get_current_user] = _deny
        try:
            response = client.get("/api/v1/auth/verify")
            assert response.status_code == 401
        finally:
            _test_app.dependency_overrides.clear()


class TestCheckUsername:
    """Tests for POST /api/v1/auth/check-username."""

    def test_check_username_available(self, client):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with patch("backend.orchestrator.db_service.db_session") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_db
            response = client.post(
                "/api/v1/auth/check-username",
                params={"email_or_username": "newuser123"},
            )
            assert response.status_code == 200
            assert response.json() == {"available": True}

    def test_check_username_taken(self, client):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(id=1)
        with patch("backend.orchestrator.db_service.db_session") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_db
            response = client.post(
                "/api/v1/auth/check-username",
                params={"email_or_username": "testuser"},
            )
            assert response.status_code == 200
            assert response.json() == {"available": False}


class TestSigningKey:
    """Tests for GET /api/v1/auth/signing-key and POST /api/v1/auth/gen-key."""

    def test_show_signing_key_found(self, client, mock_get_current_user):
        from cryptography.hazmat.primitives.asymmetric import ed25519

        mock_pub_bytes = b"\x00" * 32
        mock_private_key = MagicMock(spec=ed25519.Ed25519PrivateKey)
        mock_public_key = MagicMock()
        mock_public_key.public_bytes_raw.return_value = mock_pub_bytes
        mock_private_key.public_key.return_value = mock_public_key
        with (
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.read_bytes", return_value=b"fake-key-data"),
            patch(
                "cryptography.hazmat.primitives.serialization.load_pem_private_key",
                return_value=mock_private_key,
            ),
        ):
            response = client.get("/api/v1/auth/signing-key")
            assert response.status_code == 200
            data = response.json()
            assert data["algorithm"] == "Ed25519"
            assert data["status"] == "success"

    def test_show_signing_key_not_found(self, client, mock_get_current_user):
        with patch("pathlib.Path.is_file", return_value=False):
            response = client.get("/api/v1/auth/signing-key")
            assert response.status_code == 404
            assert "No signing key found" in response.text

    def test_gen_signing_key(self, client, mock_get_current_user):
        mock_private_key = MagicMock()
        mock_public_key = MagicMock()
        mock_pub_bytes = b"\xde\xad\xbe\xef" + b"\x00" * 28
        mock_public_key.public_bytes_raw.return_value = mock_pub_bytes
        mock_private_key.public_key.return_value = mock_public_key
        mock_private_key.private_bytes.return_value = b"mock-pem-data"
        with (
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.write_bytes"),
            patch("pathlib.Path.write_text"),
            patch("pathlib.Path.chmod"),
            patch(
                "cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PrivateKey.generate",
                return_value=mock_private_key,
            ),
        ):
            response = client.post("/api/v1/auth/gen-key")
            assert response.status_code == 201
            data = response.json()
            assert data["status"] == "success"
            assert "generated" in data["message"]
