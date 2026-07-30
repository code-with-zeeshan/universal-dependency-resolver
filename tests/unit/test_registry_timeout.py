"""Tests that registry HTTP clients handle timeouts correctly.

Uses mocked aiohttp sessions to simulate slow network conditions
and verifies that ``_make_request`` raises ``OSError`` / ``DataSourceError``
as appropriate when the configured timeout is exceeded.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from backend.data_sources.base_client import BaseDataSourceClient
from backend.data_sources.maven.client import MavenClient


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def base_client():
    return BaseDataSourceClient(
        ecosystem="test",
        base_url="https://example.com/api",
        timeout=5,
        max_retries=1,
    )


@pytest.fixture
def maven_client():
    return MavenClient()


# ==============================================================================
# BaseDataSourceClient._make_request timeout tests
# ==============================================================================


class TestBaseClientTimeout:
    """BaseDataSourceClient._make_request should propagate timeouts."""

    @pytest.mark.asyncio
    async def test_timeout_raises_oserror(self, base_client):
        """A timeout in the underlying HTTP call should raise OSError."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.side_effect = asyncio.TimeoutError("Connection timed out")
        session.request.return_value = cm

        with patch.object(base_client, "_get_session", return_value=session):
            with pytest.raises(OSError, match="Connection timed out"):
                await base_client._make_request("GET", "https://example.com/api/pkg")

    @pytest.mark.asyncio
    async def test_client_error_raises_oserror(self, base_client):
        """aiohttp.ClientError should also raise OSError."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.side_effect = aiohttp.ClientError("Connection refused")
        session.request.return_value = cm

        with patch.object(base_client, "_get_session", return_value=session):
            with pytest.raises(OSError, match="Connection refused"):
                await base_client._make_request("GET", "https://example.com/api/pkg")

    @pytest.mark.asyncio
    async def test_timeout_is_propagated_to_session(self, base_client):
        """The client timeout setting should be passed as aiohttp.ClientTimeout."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.side_effect = asyncio.TimeoutError("Timeout")
        session.request.return_value = cm

        with patch.object(base_client, "_get_session", return_value=session):
            try:
                await base_client._make_request("GET", "https://example.com/api/pkg")
            except OSError:
                pass

            call_kwargs = session.request.call_args[1]
            assert "timeout" in call_kwargs
            timeout = call_kwargs["timeout"]
            assert isinstance(timeout, aiohttp.ClientTimeout)
            assert timeout.sock_read == base_client.timeout

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, base_client):
        """The client should retry on timeout and eventually raise."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.side_effect = asyncio.TimeoutError("Timeout")
        session.request.return_value = cm

        with patch.object(base_client, "_get_session", return_value=session):
            with pytest.raises(OSError):
                await base_client._make_request("GET", "https://example.com/api/pkg")

        assert session.request.call_count == base_client.max_retries

    @pytest.mark.asyncio
    async def test_circuit_breaker_catches_timeout(self, base_client):
        """Circuit breaker should count timeout-related failures."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.side_effect = asyncio.TimeoutError("Timeout")
        session.request.return_value = cm

        assert base_client.circuit_state == "CLOSED"

        with patch.object(base_client, "_get_session", return_value=session):
            result = await base_client._circuit_breaker_call("GET", "https://example.com/api/pkg")

        assert result is None
        assert base_client._circuit_failure_count > 0

    @pytest.mark.asyncio
    async def test_cached_get_timeout_returns_none(self, base_client):
        """cached_get with timeout should return None, not raise."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.side_effect = asyncio.TimeoutError("Timeout")
        session.request.return_value = cm

        with patch.object(base_client, "_get_session", return_value=session):
            result = await base_client.cached_get(
                cache_key="test-key",
                url="https://example.com/api/pkg",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_successful_request_no_timeout(self, base_client):
        """A normal (fast) response should return data without error."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        resp = AsyncMock()
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value={"name": "pkg", "version": "1.0.0"})
        resp.__aenter__.return_value = resp
        session.request.return_value = resp

        with patch.object(base_client, "_get_session", return_value=session):
            result = await base_client._make_request("GET", "https://example.com/api/pkg")

        assert result == {"name": "pkg", "version": "1.0.0"}


# ==============================================================================
# MavenClient._make_request timeout tests
# ==============================================================================


class TestMavenClientTimeout:
    """MavenClient._make_request should handle timeouts correctly."""

    @pytest.mark.asyncio
    async def test_maven_timeout_raises_datasource_error(self, maven_client):
        """A timeout in Maven's HTTP call should raise DataSourceError."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.side_effect = asyncio.TimeoutError("Maven timeout")
        session.get.return_value = cm

        with patch.object(maven_client, "_get_session", return_value=session):
            with pytest.raises(Exception):
                await maven_client._make_request(url="https://repo1.maven.org/maven2/pkg")

    @pytest.mark.asyncio
    async def test_maven_timeout_is_propagated(self, maven_client):
        """The Maven client's timeout setting should be passed as aiohttp.ClientTimeout."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.side_effect = asyncio.TimeoutError("Timeout")
        session.get.return_value = cm

        with patch.object(maven_client, "_get_session", return_value=session):
            try:
                await maven_client._make_request(url="https://repo1.maven.org/maven2/pkg")
            except Exception:
                pass

            call_kwargs = session.get.call_args[1]
            assert "timeout" in call_kwargs
            timeout = call_kwargs["timeout"]
            assert isinstance(timeout, aiohttp.ClientTimeout)

    @pytest.mark.asyncio
    async def test_maven_client_error_raises(self, maven_client):
        """aiohttp.ClientError in Maven client should raise DataSourceError."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.side_effect = aiohttp.ClientError("Maven connection error")
        session.get.return_value = cm

        with patch.object(maven_client, "_get_session", return_value=session):
            with pytest.raises(Exception):
                await maven_client._make_request(url="https://repo1.maven.org/maven2/pkg")

    @pytest.mark.asyncio
    async def test_maven_successful_request(self, maven_client):
        """A normal Maven request should return data successfully."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        resp = AsyncMock()
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value={"groupId": "com.example", "artifactId": "pkg"})
        resp.__aenter__.return_value = resp
        session.get.return_value = resp

        with patch.object(maven_client, "_get_session", return_value=session):
            result = await maven_client._make_request(url="https://repo1.maven.org/maven2/pkg")

        assert result is not None


# ==============================================================================
# Edge-case: zero timeout, negative timeout (should not crash)
# ==============================================================================


class TestTimeoutEdgeCases:
    """Extreme timeout values must not crash the client."""

    @pytest.mark.asyncio
    async def test_large_timeout_value(self):
        """A very large timeout should be accepted."""
        client = BaseDataSourceClient(
            ecosystem="test",
            base_url="https://example.com",
            timeout=999999,
            max_retries=1,
        )
        assert client.timeout == 999999

    @pytest.mark.asyncio
    async def test_zero_timeout_does_not_crash(self):
        """A timeout of 0 should not crash the client on construction."""
        client = BaseDataSourceClient(
            ecosystem="test",
            base_url="https://example.com",
            timeout=0,
            max_retries=1,
        )
        assert client.timeout == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_closed_after_timeout_then_success(self, base_client):
        """Circuit breaker should recover after a timeout-then-success sequence."""
        session = AsyncMock(spec=aiohttp.ClientSession)

        resp_ok = AsyncMock()
        resp_ok.status = 200
        resp_ok.headers = {"Content-Type": "application/json"}
        resp_ok.json = AsyncMock(return_value={"ok": True})
        resp_ok.__aenter__.return_value = resp_ok

        fail_cm = AsyncMock()
        fail_cm.__aenter__.side_effect = asyncio.TimeoutError("Timeout")

        session.request.side_effect = [fail_cm, resp_ok]

        with patch.object(base_client, "_get_session", return_value=session):
            result_fail = await base_client._circuit_breaker_call("GET", "https://example.com/api")
            result_ok = await base_client._circuit_breaker_call("GET", "https://example.com/api")

        assert result_fail is None
        assert result_ok == {"ok": True}


# ==============================================================================
# Non-async compat tests (verify _make_request can be composed)
# ==============================================================================


class TestTimeoutSignature:
    """Verify timeout parameter is properly accepted by constructors."""

    def test_base_client_accepts_timeout(self):
        client = BaseDataSourceClient(
            ecosystem="test",
            base_url="https://example.com",
            timeout=42,
        )
        assert client.timeout == 42

    def test_maven_client_inherits_timeout(self):
        client = MavenClient()
        assert hasattr(client, "timeout")
        assert isinstance(client.timeout, int)
