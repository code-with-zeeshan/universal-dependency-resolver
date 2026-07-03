"""Tests for backend.api.auth module."""

import pytest
from jose import jwt

from backend.api.auth import (
    AuthService,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)
from backend.settings import ALGORITHM, SECRET_KEY


class TestAuthService:
    @pytest.fixture
    def auth_service(self):
        return AuthService()

    def test_verify_password(self):
        hashed = get_password_hash("testpassword")
        assert verify_password("testpassword", hashed)
        assert not verify_password("wrongpassword", hashed)

    def test_create_access_token(self):
        data = {"sub": "testuser"}
        token = create_access_token(data)
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert decoded["sub"] == "testuser"
        assert "exp" in decoded

    def test_create_refresh_token(self):
        data = {"sub": "testuser"}
        token = create_refresh_token(data)
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert decoded["sub"] == "testuser"
        assert decoded["type"] == "refresh"
