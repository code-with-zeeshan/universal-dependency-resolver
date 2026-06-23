from unittest.mock import patch
import pytest
import importlib


class TestValidateSettings:
    def _reload_settings(self):
        """Reload settings module so os.getenv picks up patched env vars."""
        import backend.settings

        importlib.reload(backend.settings)
        return backend.settings

    def test_returns_empty_list_when_config_ok(self):
        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "real-secret-not-default",
                "ENV": "development",
                "DATABASE_URL": "postgresql://localhost:5432/db",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://jaeger:4318",
                "API_RATE_LIMIT_PER_MINUTE": "60",
                "DATABASE_POOL_SIZE": "10",
            },
            clear=True,
        ):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert result == []

    def test_warns_on_default_secret_key(self):
        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "your-secret-key-here-change-in-production",
                "ENV": "development",
                "DATABASE_URL": "postgresql://localhost:5432/db",
            },
            clear=True,
        ):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert any("SECRET_KEY" in w for w in result)

    def test_warns_on_sqlite_in_production(self):
        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "real-secret",
                "ENV": "production",
                "DATABASE_URL": "sqlite:///./test.db",
            },
            clear=True,
        ):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert any("SQLite" in w for w in result)

    def test_warns_on_invalid_rate_limit(self):
        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "real-secret",
                "ENV": "development",
                "DATABASE_URL": "postgresql://localhost:5432/db",
                "API_RATE_LIMIT_PER_MINUTE": "not-a-number",
            },
            clear=True,
        ):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert any("API_RATE_LIMIT_PER_MINUTE" in w for w in result)

    def test_warns_on_negative_pool_size(self):
        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "real-secret",
                "ENV": "development",
                "DATABASE_URL": "postgresql://localhost:5432/db",
                "DATABASE_POOL_SIZE": "-1",
            },
            clear=True,
        ):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert any("DATABASE_POOL_SIZE" in w for w in result)

    def test_warns_on_bad_otel_endpoint(self):
        with patch.dict(
            "os.environ",
            {
                "SECRET_KEY": "real-secret",
                "ENV": "development",
                "DATABASE_URL": "postgresql://localhost:5432/db",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "localhost:4317",
            },
            clear=True,
        ):
            settings = self._reload_settings()
            result = settings.validate_settings()
            assert any("OTEL_EXPORTER_OTLP_ENDPOINT" in w for w in result)
