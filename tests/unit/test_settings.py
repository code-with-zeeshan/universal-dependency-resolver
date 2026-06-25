from unittest.mock import patch
import pytest
import importlib


BASE_TEST_ENV = {
    "SECRET_KEY": "real-secret",
    "ENV": "development",
    "DATABASE_URL": "postgresql://localhost:5432/db",
    "ENABLE_CSRF": "false",
}


class TestValidateSettings:
    def _reload_settings(self):
        """Reload settings module so os.getenv picks up patched env vars."""
        import backend.settings

        importlib.reload(backend.settings)
        return backend.settings

    def teardown_method(self):
        """Restore settings module after each test that may have reloaded it."""
        import backend.settings
        importlib.reload(backend.settings)

    def test_returns_empty_list_when_config_ok(self):
        env = {**BASE_TEST_ENV,
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://jaeger:4318",
            "API_RATE_LIMIT_PER_MINUTE": "60",
            "DATABASE_POOL_SIZE": "10",
        }
        with patch.dict("os.environ", env, clear=True):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert result == []

    def test_warns_on_default_secret_key(self):
        env = {**BASE_TEST_ENV,
            "SECRET_KEY": "your-secret-key-here-change-in-production",
            "ENV": "development",
            "DATABASE_URL": "postgresql://localhost:5432/db",
        }
        with patch.dict("os.environ", env, clear=True):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert any("SECRET_KEY" in w for w in result)

    def test_warns_on_sqlite_in_production(self):
        env = {**BASE_TEST_ENV,
            "ENV": "production",
            "DATABASE_URL": "sqlite:///./test.db",
        }
        with patch.dict("os.environ", env, clear=True):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert any("SQLite" in w for w in result)

    def test_warns_on_invalid_rate_limit(self):
        env = {**BASE_TEST_ENV,
            "API_RATE_LIMIT_PER_MINUTE": "not-a-number",
        }
        with patch.dict("os.environ", env, clear=True):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert any("API_RATE_LIMIT_PER_MINUTE" in w for w in result)

    def test_warns_on_negative_pool_size(self):
        env = {**BASE_TEST_ENV,
            "DATABASE_POOL_SIZE": "-1",
        }
        with patch.dict("os.environ", env, clear=True):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert any("DATABASE_POOL_SIZE" in w for w in result)

    def test_warns_on_bad_otel_endpoint(self):
        env = {**BASE_TEST_ENV,
            "OTEL_EXPORTER_OTLP_ENDPOINT": "localhost:4317",
        }
        with patch.dict("os.environ", env, clear=True):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert any("OTEL_EXPORTER_OTLP_ENDPOINT" in w for w in result)
