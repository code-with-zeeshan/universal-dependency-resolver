import importlib
from unittest.mock import patch

BASE_TEST_ENV = {
    "SECRET_KEY": "real-secret",
    "ENV": "development",
    "DATABASE_URL": "postgresql://localhost:5432/db",
    "ENABLE_CSRF": "false",
}


class TestValidateSettings:
    def _reload_settings(self):
        import backend.settings
        importlib.reload(backend.settings)
        return backend.settings

    def teardown_method(self):
        import backend.settings
        importlib.reload(backend.settings)

    def test_returns_empty_list_when_config_ok(self):
        with patch.dict("os.environ", BASE_TEST_ENV, clear=True):
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
