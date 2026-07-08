"""Tests for backend.core.registry_auth."""

import os
import tempfile
from unittest.mock import patch

from backend.core.registry_auth import (
    _apply_auth_header,
    _apply_basic_auth,
    _apply_netrc,
    resolve_auth_headers,
)


class TestResolveAuthHeaders:
    def test_no_auth_returns_empty(self):
        result = resolve_auth_headers("npm", "https://registry.npmjs.org")
        assert result == {}

    def test_explicit_headers_highest_priority(self):
        explicit = {"Authorization": "Bearer explicit"}
        with patch.dict(os.environ, {"NPM_AUTH_TOKEN": "env_token"}, clear=True):
            result = resolve_auth_headers(
                "npm",
                "https://registry.npmjs.org",
                explicit_headers=explicit,
            )
        assert result == {"Authorization": "Bearer explicit"}

    def test_env_var_bearer_token(self):
        with patch.dict(
            os.environ, {"NPM_AUTH_TOKEN": "mytoken", "NPM_AUTH_TYPE": "bearer"}, clear=True
        ):
            result = resolve_auth_headers("npm", "https://registry.npmjs.org")
        assert result == {"Authorization": "Bearer mytoken"}

    def test_env_var_basic_token(self):
        with patch.dict(
            os.environ, {"NPM_AUTH_TOKEN": "base64stuff", "NPM_AUTH_TYPE": "basic"}, clear=True
        ):
            result = resolve_auth_headers("npm", "https://registry.npmjs.org")
        import base64

        expected = base64.b64encode(b"base64stuff:").decode()
        assert result == {"Authorization": f"Basic {expected}"}

    def test_env_var_header_type(self):
        with patch.dict(
            os.environ,
            {"NPM_AUTH_TOKEN": "X-API-Key:abc123", "NPM_AUTH_TYPE": "header"},
            clear=True,
        ):
            result = resolve_auth_headers("npm", "https://registry.npmjs.org")
        assert result == {"X-API-Key": "abc123"}

    def test_env_var_username_password(self):
        with patch.dict(
            os.environ, {"NPM_AUTH_USERNAME": "user", "NPM_AUTH_PASSWORD": "pass"}, clear=True
        ):
            result = resolve_auth_headers("npm", "https://registry.npmjs.org")
        import base64

        expected = base64.b64encode(b"user:pass").decode()
        assert result == {"Authorization": f"Basic {expected}"}

    def test_unknown_ecosystem_uses_uppercased_name(self):
        with patch.dict(os.environ, {"FOO_AUTH_TOKEN": "token"}, clear=True):
            result = resolve_auth_headers("foo")
        assert result == {"Authorization": "Bearer token"}

    def test_unknown_auth_type_falls_back_to_bearer(self):
        with patch.dict(
            os.environ, {"NPM_AUTH_TOKEN": "token", "NPM_AUTH_TYPE": "invalid"}, clear=True
        ):
            result = resolve_auth_headers("npm")
        assert result == {"Authorization": "Bearer token"}

    def test_token_overrides_username_password(self):
        with patch.dict(
            os.environ,
            {
                "NPM_AUTH_TOKEN": "tok",
                "NPM_AUTH_USERNAME": "user",
                "NPM_AUTH_PASSWORD": "pass",
            },
            clear=True,
        ):
            result = resolve_auth_headers("npm")
        assert result == {"Authorization": "Bearer tok"}


class TestApplyAuthHeader:
    def test_bearer(self):
        headers = {}
        _apply_auth_header(headers, "abc", "bearer")
        assert headers["Authorization"] == "Bearer abc"

    def test_basic(self):
        headers = {}
        _apply_auth_header(headers, "abc", "basic")
        import base64

        assert headers["Authorization"] == f"Basic {base64.b64encode(b'abc:').decode()}"

    def test_header_with_colon(self):
        headers = {}
        _apply_auth_header(headers, "X-Custom:myvalue", "header")
        assert headers["X-Custom"] == "myvalue"

    def test_header_without_colon(self):
        headers = {}
        _apply_auth_header(headers, "myvalue", "header")
        assert headers["X-Auth-Token"] == "myvalue"


class TestApplyBasicAuth:
    def test_basic_auth_encoding(self):
        headers = {}
        _apply_basic_auth(headers, "user", "pass")
        import base64

        expected = base64.b64encode(b"user:pass").decode()
        assert headers["Authorization"] == f"Basic {expected}"


class TestApplyNetrc:
    def test_no_netrc_file_does_nothing(self):
        headers = {}
        _apply_netrc(headers, "https://registry.example.com")
        assert headers == {}

    def test_netrc_matched_host(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".netrc", delete=False) as f:
            f.write("machine registry.example.com login myuser password mypass\n")
            netrc_path = f.name
        try:
            with patch("backend.core.registry_auth.netrc") as mock_netrc:
                mock_auth = ("myuser", None, "mypass")
                mock_netrc.return_value.authenticators.return_value = mock_auth
                headers = {}
                _apply_netrc(headers, "https://registry.example.com")
                import base64

                expected = base64.b64encode(b"myuser:mypass").decode()
                assert headers["Authorization"] == f"Basic {expected}"
        finally:
            os.unlink(netrc_path)

    def test_netrc_no_password_skips(self):
        with patch("backend.core.registry_auth.netrc") as mock_netrc:
            mock_netrc.return_value.authenticators.return_value = ("user", None, None)
            headers = {}
            _apply_netrc(headers, "https://example.com")
            assert headers == {}
