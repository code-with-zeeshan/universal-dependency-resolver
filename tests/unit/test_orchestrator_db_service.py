"""Unit tests for orchestrator/db_service.py."""

from unittest.mock import patch


class TestGetDbEngine:
    def test_delegates_to_get_engine(self):
        from backend.orchestrator.db_service import get_db_engine

        with patch("backend.orchestrator.db_service.get_engine", return_value="fake_engine"):
            result = get_db_engine()
            assert result == "fake_engine"


class TestCheckHealth:
    def test_delegates_to_check_db_health(self):
        from backend.orchestrator.db_service import check_health

        with patch(
            "backend.orchestrator.db_service.check_db_health",
            return_value={"status": "healthy"},
        ):
            result = check_health()
            assert result == {"status": "healthy"}


class TestAuthenticateApiKey:
    def test_delegates_to_database_service(self):
        from backend.orchestrator.db_service import authenticate_api_key

        with patch(
            "backend.database.service.authenticate_api_key",
            return_value={"name": "test", "role": "admin"},
        ):
            result = authenticate_api_key("valid_key")
            assert result == {"name": "test", "role": "admin"}

    def test_returns_none_for_invalid_key(self):
        from backend.orchestrator.db_service import authenticate_api_key

        with patch(
            "backend.database.service.authenticate_api_key",
            return_value=None,
        ):
            result = authenticate_api_key("invalid_key")
            assert result is None


class TestReExports:
    def test_api_key_class_accessible(self):
        from backend.database.models import APIKey as DBAPIKey
        from backend.orchestrator.db_service import APIKey

        assert APIKey is DBAPIKey

    def test_user_class_accessible(self):
        from backend.database.models import User as DBUser
        from backend.orchestrator.db_service import User

        assert User is DBUser

    def test_compatibility_db_accessible(self):
        from backend.database.compatibility_db import CompatibilityDB as DBCompat
        from backend.orchestrator.db_service import CompatibilityDB

        assert CompatibilityDB is DBCompat

    def test_db_session_accessible(self):
        from backend.database.models import db_session as DBsession
        from backend.orchestrator.db_service import db_session

        assert db_session is DBsession

    def test_all_exports_match_all(self):
        from backend.orchestrator.db_service import __all__

        expected = {
            "APIKey",
            "CompatibilityDB",
            "User",
            "authenticate_api_key",
            "check_health",
            "db_session",
            "get_db_engine",
        }
        assert set(__all__) == expected
