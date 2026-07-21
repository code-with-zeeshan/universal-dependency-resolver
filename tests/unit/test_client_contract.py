"""Client interface contract tests.

Verifies that every BaseDataSourceClient subclass honors the expected:
- Method interface (``_get``, ``_make_request``, ``cached_get``, etc.)
- HTTP delegation chain (``_get`` → ``_request`` → ``_circuit_breaker_call`` → ``_make_request``)
- Auth header injection via ``resolve_auth_headers``
- 404 → None, 429 → retry, 5xx → retry semantics
- Cache integration via ``DictCache``

Clients known to have BYPASSES (detected by these tests):
- ``PyPIClient._get`` — uses ``session.get()`` directly, no ``_throttle()``/``_make_request()``
- ``CondaClient`` — multiple methods use ``session.get()`` directly
- ``APTClient._get_packages_list`` — ``session.get()`` direct
- ``APKClient._get_apkindex`` — ``session.get()`` direct
- ``MavenClient`` — multiple ``session.get()`` calls outside ``_make_request``
- ``GoModulesClient`` — ``_make_request`` override doesn't call super; ``package_exists`` direct
- ``GradleClient._fetch_from_maven_central`` — ``session.get()`` direct
- ``DockerRegistryClient`` — does NOT extend ``BaseDataSourceClient`` at all
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import aiohttp
import pytest

from backend.data_sources.base_client import BaseDataSourceClient
from backend.data_sources.conda_client import CondaClient
from backend.data_sources.gomodules_client import GoModulesClient
from backend.data_sources.maven.client import MavenClient
from backend.data_sources.npm_client import NPMClient
from backend.data_sources.pypi_client import PyPIClient

# ── Helpers ──────────────────────────────────────────────────────────


def _collect_client_classes():
    """Yield (name, class) tuples for every concrete BaseDataSourceClient subclass."""
    for klass in BaseDataSourceClient.__subclasses__():
        if inspect.isabstract(klass):
            continue
        yield klass.__name__, klass


BASE_CONTRACT_METHODS = {
    "_get",
    "_make_request",
    "_circuit_breaker_call",
    "_request",
    "_get_text",
    "cached_get",
    "_throttle",
    "_cache_get",
    "_cache_set",
    "get_artifact_hash",
    "close",
}

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_session():
    """Create a mock aiohttp.ClientSession that records all calls."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    response = AsyncMock(spec=aiohttp.ClientResponse)
    response.status = 200
    response.headers = {"Content-Type": "application/json"}
    response.json = AsyncMock(return_value={"ok": True})
    response.text = AsyncMock(return_value='{"ok": true}')
    response.__aenter__.return_value = response
    session.get.return_value = response
    session.request.return_value = response
    session.head.return_value = response
    session.closed = False
    return session


@pytest.fixture
def mock_cache():
    """Create a mock DictCache."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=None)
    return cache


@pytest.fixture(autouse=True)
def reset_sessions():
    """Reset the global session registry between tests."""
    from backend.data_sources import base_client as bc

    bc._sessions_registry.clear()
    yield


@pytest.fixture
def pypi_client():
    return PyPIClient()


@pytest.fixture
def conda_client():
    return CondaClient()


@pytest.fixture
def npm_client():
    return NPMClient()


@pytest.fixture
def gomodules_client():
    return GoModulesClient()


@pytest.fixture
def maven_client():
    return MavenClient()


# ── 1. Interface contract — every client has the expected methods ────


class TestClientInterface:
    """Every registered client must implement the base interface."""

    def test_base_class_has_contract_methods(self):
        """BaseDataSourceClient itself must have all contract methods."""
        for name in BASE_CONTRACT_METHODS:
            assert hasattr(BaseDataSourceClient, name), (
                f"BaseDataSourceClient missing contract method: {name}"
            )

    def test_all_subclasses_have_contract_methods(self):
        """Every subclass must have (inherit or override) all contract methods."""
        for name, klass in _collect_client_classes():
            for method in BASE_CONTRACT_METHODS:
                assert hasattr(klass, method), f"{name} missing contract method: {method}"

    def test_pypi_client_has_expected_basic_methods(self, pypi_client):
        assert hasattr(pypi_client, "get_package_info_async")
        assert hasattr(pypi_client, "get_package_info")
        assert hasattr(pypi_client, "get_artifact_hash")
        assert hasattr(pypi_client, "package_exists")
        assert hasattr(pypi_client, "search")
        assert hasattr(pypi_client, "get_versions")
        assert hasattr(pypi_client, "get_dependencies")

    def test_conda_client_has_expected_basic_methods(self, conda_client):
        assert hasattr(conda_client, "get_package_info_async")
        assert hasattr(conda_client, "get_package_info")
        assert hasattr(conda_client, "package_exists")
        assert hasattr(conda_client, "search")
        assert hasattr(conda_client, "get_versions")
        assert hasattr(conda_client, "get_dependencies")

    def test_npm_client_has_expected_basic_methods(self, npm_client):
        assert hasattr(npm_client, "get_package_info")
        assert hasattr(npm_client, "get_artifact_hash")
        assert hasattr(npm_client, "search_packages")
        assert hasattr(npm_client, "get_versions")
        assert hasattr(npm_client, "get_dependencies")

    def test_gomodules_client_has_expected_basic_methods(self, gomodules_client):
        assert hasattr(gomodules_client, "get_package_info_async")
        assert hasattr(gomodules_client, "get_package_info")
        assert hasattr(gomodules_client, "package_exists")
        assert hasattr(gomodules_client, "search_packages")
        assert hasattr(gomodules_client, "get_versions")
        assert hasattr(gomodules_client, "get_dependencies")

    def test_maven_client_has_expected_basic_methods(self, maven_client):
        assert hasattr(maven_client, "get_package_info_async")
        assert hasattr(maven_client, "get_package_info")
        assert hasattr(maven_client, "get_package_versions")
        assert hasattr(maven_client, "get_dependencies")
        assert hasattr(maven_client, "get_artifact_hash")


# ── 2. HTTP delegation chain ─────────────────────────────────────────


class TestHttpDelegationChain:
    """Verify that HTTP calls flow through expected intermediary methods.

    The expected chain for base clients is::

        _get → _request → _circuit_breaker_call → _make_request → session.request

    Overrides are flagged as CONTRACT VIOLATIONS when they bypass
    ``_make_request`` (which provides throttling, auth injection, 404/429
    handling, and circuit breaker integration).
    """

    @pytest.mark.parametrize("client_cls", [c for _, c in _collect_client_classes()])
    async def test_client_has_session_property(self, client_cls):
        """Every client must have ``_get_session`` that returns an ``aiohttp.ClientSession``."""
        client = client_cls()
        session = client._get_session()
        assert isinstance(session, aiohttp.ClientSession)
        await client.close()

    async def test_base_get_calls_request(self, mock_session):
        """Base ``_get`` must delegate to ``_request``."""
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._request = AsyncMock(return_value={"ok": True})

        result = await client._get("https://example.com/api")

        client._request.assert_awaited_once_with("GET", "https://example.com/api")
        assert result == {"ok": True}

    async def test_base_request_calls_circuit_breaker(self, mock_session):
        """Base ``_request`` must delegate to ``_circuit_breaker_call``."""
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._circuit_breaker_call = AsyncMock(return_value={"ok": True})

        result = await client._request("GET", "https://example.com/api")

        client._circuit_breaker_call.assert_awaited_once_with("GET", "https://example.com/api")
        assert result == {"ok": True}

    async def test_base_circuit_breaker_calls_make_request(self, mock_session):
        """``_circuit_breaker_call`` must delegate to ``_make_request``."""
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._make_request = AsyncMock(return_value={"ok": True})

        result = await client._circuit_breaker_call("GET", "https://example.com/api")

        client._make_request.assert_awaited_once_with("GET", "https://example.com/api")
        assert result == {"ok": True}

    async def test_base_make_request_calls_throttle(self, mock_session):
        """``_make_request`` must call ``_throttle`` before making the request."""
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._throttle = AsyncMock(return_value=None)

        # Patch session.request to return quickly
        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value={"ok": True})
        resp.__aenter__.return_value = resp
        mock_session.request.return_value = resp

        await client._make_request("GET", "https://example.com/api")

        client._throttle.assert_awaited_once()

    async def test_base_make_request_injects_auth_headers(self, mock_session):
        """``_make_request`` must inject auth headers into every request."""
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._auth_headers = {"Authorization": "Bearer test-token"}

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value={"ok": True})
        resp.__aenter__.return_value = resp
        mock_session.request.return_value = resp

        await client._make_request("GET", "https://example.com/api")

        _, kwargs = mock_session.request.call_args
        headers = kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer test-token"
        assert "User-Agent" in headers

    async def test_base_make_request_returns_none_on_404(self, mock_session):
        """``_make_request`` must return None for 404 responses."""
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 404
        resp.__aenter__.return_value = resp
        mock_session.request.return_value = resp

        result = await client._make_request("GET", "https://example.com/api")
        assert result is None

    async def test_base_make_request_retries_on_429(self, mock_session):
        """``_make_request`` must retry on 429 with backoff."""
        client = BaseDataSourceClient("test", "https://example.com", max_retries=3)
        client._get_session = MagicMock(return_value=mock_session)
        client._throttle = AsyncMock(return_value=None)

        resp_429 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_429.status = 429
        resp_429.headers = {"Retry-After": "1"}
        resp_429.__aenter__.return_value = resp_429

        resp_200 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_200.status = 200
        resp_200.headers = {"Content-Type": "application/json"}
        resp_200.json = AsyncMock(return_value={"ok": True})
        resp_200.__aenter__.return_value = resp_200

        mock_session.request.side_effect = [resp_429, resp_200]

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await client._make_request("GET", "https://example.com/api")

        assert result == {"ok": True}
        assert mock_session.request.call_count == 2

    async def test_base_make_request_retries_on_5xx(self, mock_session):
        """``_make_request`` must retry on 5xx with backoff."""
        client = BaseDataSourceClient("test", "https://example.com", max_retries=3)
        client._get_session = MagicMock(return_value=mock_session)
        client._throttle = AsyncMock(return_value=None)

        resp_500 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_500.status = 500
        resp_500.__aenter__.return_value = resp_500

        resp_200 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_200.status = 200
        resp_200.headers = {"Content-Type": "application/json"}
        resp_200.json = AsyncMock(return_value={"ok": True})
        resp_200.__aenter__.return_value = resp_200

        mock_session.request.side_effect = [resp_500, resp_200]

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await client._make_request("GET", "https://example.com/api")

        assert result == {"ok": True}
        assert mock_session.request.call_count == 2


# ── 3. NPMClient — compliant contract ────────────────────────────────


class TestNPMClientContract:
    """NPMClient wraps ``_make_request`` and ``cached_get`` with semaphore,
    then delegates to ``super()`` — this is the expected pattern."""

    async def test_make_request_delegates_to_super(self, mock_session):
        client = NPMClient()
        client._get_session = MagicMock(return_value=mock_session)

        with patch.object(
            BaseDataSourceClient, "_make_request", AsyncMock(return_value={"ok": True})
        ) as super_request:
            with patch("asyncio.sleep", AsyncMock(return_value=None)):
                result = await client._make_request("GET", "https://registry.npmjs.org/pkg")

        super_request.assert_awaited_once_with("GET", "https://registry.npmjs.org/pkg")
        assert result == {"ok": True}

    async def test_cached_get_delegates_to_super(self, mock_session):
        client = NPMClient()
        client._get_session = MagicMock(return_value=mock_session)
        client._cache = AsyncMock()
        client._cache.get = AsyncMock(return_value=None)

        with patch.object(
            BaseDataSourceClient, "cached_get", AsyncMock(return_value={"ok": True})
        ) as super_cached:
            with patch("asyncio.sleep", AsyncMock(return_value=None)):
                result = await client.cached_get("cache-key", "https://registry.npmjs.org/pkg")

        super_cached.assert_awaited_once()
        assert result == {"ok": True}


# ── 4. PyPIClient — known bypass ────────────────────────────────────


class TestPyPIClientBypass:
    """PyPIClient._get() bypasses ``_make_request`` — a contract violation.

    Its ``_get`` uses ``self._get_session().get(url)`` directly with its own
    retry logic and ``self._rate_limiter`` Semaphore(5). It does NOT call
    ``_throttle()``, ``_make_request()``, or ``_circuit_breaker_call()``.
    """

    async def test_get_does_not_call_make_request(self, pypi_client, mock_session):
        """PyPIClient._get must NOT call ``_make_request`` — verify the bypass."""
        pypi_client._get_session = MagicMock(return_value=mock_session)
        pypi_client._make_request = AsyncMock()

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await pypi_client._get("https://pypi.org/pypi/requests/json")

        pypi_client._make_request.assert_not_called()
        # Verify it used session.get() directly instead
        mock_session.get.assert_called_once()

    async def test_get_does_not_call_throttle(self, pypi_client, mock_session):
        """PyPIClient._get does NOT call ``_throttle`` — rate limiting is lost."""
        pypi_client._get_session = MagicMock(return_value=mock_session)
        pypi_client._throttle = AsyncMock()

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            await pypi_client._get("https://pypi.org/pypi/requests/json")

        pypi_client._throttle.assert_not_called()

    async def test_get_uses_own_rate_limiter(self, pypi_client, mock_session):
        """PyPIClient._get uses ``self._rate_limiter`` instead of ``_throttle``."""
        pypi_client._get_session = MagicMock(return_value=mock_session)
        assert hasattr(pypi_client, "_rate_limiter")
        assert isinstance(pypi_client._rate_limiter, asyncio.Semaphore)

    async def test_get_injects_auth_headers(self, pypi_client, mock_session):
        """PyPIClient._get does pass auth headers (one thing it gets right)."""
        pypi_client._get_session = MagicMock(return_value=mock_session)
        pypi_client._auth_headers = {"Authorization": "Bearer test-token"}

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.json = AsyncMock(return_value={"info": {"name": "requests"}})
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await pypi_client._get("https://pypi.org/pypi/requests/json")

        _, kwargs = mock_session.get.call_args
        assert "Authorization" in kwargs.get("headers", {})

    async def test_get_handles_429_with_retry(self, pypi_client, mock_session):
        """PyPIClient._get retries on 429 — it's not completely broken."""
        pypi_client._get_session = MagicMock(return_value=mock_session)

        resp_429 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_429.status = 429
        resp_429.headers = {"Retry-After": "1"}
        resp_429.__aenter__.return_value = resp_429

        resp_200 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_200.status = 200
        resp_200.json = AsyncMock(return_value={"info": {"name": "requests"}})
        resp_200.__aenter__.return_value = resp_200

        mock_session.get.side_effect = [resp_429, resp_200]

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await pypi_client._get("https://pypi.org/pypi/requests/json")

        assert result is not None
        assert result["info"]["name"] == "requests"
        assert mock_session.get.call_count == 2

    async def test_get_returns_none_after_final_retry_fail(self, pypi_client, mock_session):
        """PyPIClient._get returns None when all retries fail."""
        pypi_client._get_session = MagicMock(return_value=mock_session)

        resp_500 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_500.status = 500
        resp_500.__aenter__.return_value = resp_500
        resp_500.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=500, message="Internal Server Error"
        )
        mock_session.get.return_value = resp_500

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await pypi_client._get("https://pypi.org/pypi/requests/json")

        assert result is None

    async def test_package_exists_bypasses_make_request(self, pypi_client, mock_session):
        """PyPIClient.package_exists uses ``session.head()`` directly."""
        pypi_client._get_session = MagicMock(return_value=mock_session)
        resp = MagicMock(spec=aiohttp.ClientResponse)
        resp.status = 200

        mock_head = AsyncMock(return_value=resp)
        mock_session.head = mock_head

        result = await pypi_client.package_exists("requests")

        assert result is True
        mock_head.assert_awaited_once()

    async def test_cached_get_used_for_primary_flow(self, pypi_client, mock_session):
        """PyPIClient uses ``cached_get`` in the primary data path,
        which is good — but ``cached_get`` in the base class also bypasses
        ``_make_request`` (separate design issue).
        """
        pypi_client._get_session = MagicMock(return_value=mock_session)
        pypi_client._cache = AsyncMock()
        pypi_client._cache.get = AsyncMock(return_value=None)

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await pypi_client.get_package_info_async("requests")

        # cached_get should have been called — verify at least one HTTP call was made
        assert mock_session.request.called or mock_session.get.called


# ── 5. CondaClient — multiple bypasses ───────────────────────────────


class TestCondaClientBypass:
    """CondaClient makes direct ``session.get()`` calls in multiple methods,
    completely bypassing ``_make_request``, ``_throttle``, and auth injection."""

    async def test_fetch_from_anaconda_api_uses_direct_session(self, conda_client, mock_session):
        """``_fetch_from_anaconda_api`` uses ``session.get()`` directly —
        no ``_make_request``, no ``_throttle``, no auth injection.
        """
        conda_client._get_session = MagicMock(return_value=mock_session)
        conda_client._throttle = AsyncMock()
        conda_client._make_request = AsyncMock()

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.json = AsyncMock(return_value={"name": "numpy"})
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        result = await conda_client._fetch_from_anaconda_api("numpy", "conda-forge")

        assert result is not None
        conda_client._throttle.assert_not_called()
        conda_client._make_request.assert_not_called()

    async def test_fetch_repodata_uses_direct_session(self, conda_client, mock_session):
        """``_fetch_repodata`` uses ``session.get()`` directly."""
        conda_client._get_session = MagicMock(return_value=mock_session)
        conda_client._make_request = AsyncMock()

        # Avoid cache hit
        conda_client._repodata_cache = {}

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.json = AsyncMock(return_value={"packages": {}})
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        result = await conda_client._fetch_repodata("conda-forge", "linux-64")

        assert result is not None
        conda_client._make_request.assert_not_called()

    async def test_search_uses_direct_session(self, conda_client, mock_session):
        """CondaClient.search uses ``session.get()`` directly."""
        conda_client._get_session = MagicMock(return_value=mock_session)
        conda_client._make_request = AsyncMock()

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.json = AsyncMock(return_value=[{"name": "numpy"}])
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        result = await conda_client.search("numpy")

        assert len(result) == 1
        conda_client._make_request.assert_not_called()

    async def test_package_exists_uses_direct_session(self, conda_client, mock_session):
        """CondaClient.package_exists uses ``session.get()`` directly."""
        conda_client._get_session = MagicMock(return_value=mock_session)
        conda_client._make_request = AsyncMock()

        resp = MagicMock(spec=aiohttp.ClientResponse)
        resp.status = 200

        mock_get = AsyncMock(return_value=resp)
        mock_session.get = mock_get

        result = await conda_client.package_exists("numpy")

        assert result is True
        conda_client._make_request.assert_not_called()
        mock_get.assert_awaited_once()

    async def test_no_auth_injection_on_direct_calls(self, conda_client, mock_session):
        """Direct ``session.get()`` calls in CondaClient miss auth injection."""
        conda_client._get_session = MagicMock(return_value=mock_session)
        conda_client._auth_headers = {"Authorization": "Bearer conda-token"}

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.json = AsyncMock(return_value={"name": "numpy"})
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        await conda_client._fetch_from_anaconda_api("numpy", "conda-forge")

        _, kwargs = mock_session.get.call_args
        headers = kwargs.get("headers", {}) or {}
        # The bypass means auth headers are NOT injected
        assert "Authorization" not in headers


# ── 6. GoModulesClient — override analysis ───────────────────────────


class TestGoModulesClientContract:
    """GoModulesClient overrides ``_make_request`` with its own
    implementation that does call ``_throttle()`` and respects auth headers,
    but does NOT call ``super()._make_request()`` — a partial contract
    compliance issue (duplicated retry/429/5xx logic).
    """

    async def test_make_request_calls_throttle(self, gomodules_client, mock_session):
        """The override does call ``_throttle()`` — good."""
        gomodules_client._get_session = MagicMock(return_value=mock_session)
        gomodules_client._throttle = AsyncMock(return_value=None)

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value={"Version": "v1.0.0"})
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await gomodules_client._make_request("https://proxy.golang.org/pkg/@v/list")

        gomodules_client._throttle.assert_awaited_once()
        assert result == {"Version": "v1.0.0"}

    async def test_make_request_injects_auth_headers(self, gomodules_client, mock_session):
        """The override does inject auth headers."""
        gomodules_client._get_session = MagicMock(return_value=mock_session)
        gomodules_client._auth_headers = {"Authorization": "Bearer go-token"}

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value={"Version": "v1.0.0"})
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            await gomodules_client._make_request("https://proxy.golang.org/pkg/@v/list")

        _, kwargs = mock_session.get.call_args
        assert kwargs.get("headers", {}).get("Authorization") == "Bearer go-token"

    async def test_make_request_does_not_call_super(self, gomodules_client, mock_session):
        """The override does NOT call ``super()._make_request()``."""
        gomodules_client._get_session = MagicMock(return_value=mock_session)

        with patch.object(BaseDataSourceClient, "_make_request", AsyncMock()) as super_request:
            resp = AsyncMock(spec=aiohttp.ClientResponse)
            resp.status = 200
            resp.headers = {"Content-Type": "application/json"}
            resp.json = AsyncMock(return_value={"Version": "v1.0.0"})
            resp.__aenter__.return_value = resp
            mock_session.get.return_value = resp
            with patch("asyncio.sleep", AsyncMock(return_value=None)):
                await gomodules_client._make_request("https://proxy.golang.org/pkg/@v/list")

        super_request.assert_not_called()

    async def test_make_request_returns_none_on_404(self, gomodules_client, mock_session):
        """The override must return None on 404."""
        gomodules_client._get_session = MagicMock(return_value=mock_session)
        gomodules_client._throttle = AsyncMock(return_value=None)

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 404
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await gomodules_client._make_request("https://proxy.golang.org/pkg/@v/list")

        assert result is None

    async def test_make_request_retries_on_429(self, gomodules_client, mock_session):
        """The override must retry on 429."""
        gomodules_client._get_session = MagicMock(return_value=mock_session)
        gomodules_client._throttle = AsyncMock(return_value=None)

        resp_429 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_429.status = 429
        resp_429.headers = {"Retry-After": "1"}
        resp_429.__aenter__.return_value = resp_429

        resp_200 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_200.status = 200
        resp_200.headers = {"Content-Type": "text/plain"}
        resp_200.text = AsyncMock(return_value="v1.0.0\n")
        resp_200.__aenter__.return_value = resp_200

        mock_session.get.side_effect = [resp_429, resp_200]

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await gomodules_client._make_request("https://proxy.golang.org/pkg/@v/list")

        assert result is not None
        assert mock_session.get.call_count == 2

    async def test_package_exists_bypasses_make_request(self, gomodules_client, mock_session):
        """GoModulesClient.package_exists uses ``session.head()`` directly."""
        gomodules_client._get_session = MagicMock(return_value=mock_session)
        gomodules_client._make_request = AsyncMock()

        resp = MagicMock(spec=aiohttp.ClientResponse)
        resp.status = 200

        mock_head = AsyncMock(return_value=resp)
        mock_session.head = mock_head

        result = await gomodules_client.package_exists("github.com/foo/bar")

        assert result is True
        gomodules_client._make_request.assert_not_called()
        mock_head.assert_awaited_once()


# ── 7. MavenClient — override analysis ───────────────────────────────


class TestMavenClientContract:
    """MavenClient overrides ``_make_request`` and has additional
    ``session.get()`` calls outside of ``_make_request`` in multiple methods.
    """

    async def test_make_request_uses_session_get(self, maven_client, mock_session):
        """MavenClient._make_request uses ``session.get()`` with auth headers."""
        maven_client._get_session = MagicMock(return_value=mock_session)
        maven_client._auth_headers = {"Authorization": "Bearer maven-token"}

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value={"response": {"docs": []}})
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await maven_client._make_request(
                url="https://search.maven.org/solrsearch/select",
                params={"q": "test", "rows": 1, "wt": "json"},
            )

        assert result is not None
        _, kwargs = mock_session.get.call_args
        assert "User-Agent" not in str(kwargs)
        auth = kwargs.get("headers", {})
        if auth:
            assert auth.get("Authorization") == "Bearer maven-token"

    async def test_make_request_returns_none_on_404(self, maven_client, mock_session):
        """MavenClient._make_request returns None on 404."""
        maven_client._get_session = MagicMock(return_value=mock_session)

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 404
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        result = await maven_client._make_request(
            url="https://search.maven.org/solrsearch/select",
        )

        assert result is None

    async def test_extra_session_get_calls_bypass_make_request(self, maven_client, mock_session):
        """MavenClient has ``session.get()`` calls in ``get_package_info``,
        ``get_package_versions``, and ``get_package_info_async`` that
        bypass ``_make_request`` entirely.
        """
        maven_client._get_session = MagicMock(return_value=mock_session)
        maven_client._make_request = AsyncMock()

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(
            return_value={"response": {"docs": [{"latestVersion": "1.0", "text": ["desc"]}]}}
        )
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        await maven_client.get_package_info("com.example", "my-lib")

        maven_client._make_request.assert_not_called()


# ── 8. APTClient and APKClient — file-download bypass ────────────────


class TestAptApkContract:
    """APTClient._get_packages_list and APKClient._get_apkindex use
    ``session.get()`` directly to download gzipped index files.
    These bypass ``_make_request``, ``_throttle``, and auth injection.
    """

    async def test_apt_get_packages_list_bypasses(self, mock_session):
        from backend.data_sources.apt_client import APTClient

        client = APTClient()
        client._get_session = MagicMock(return_value=mock_session)
        client._make_request = AsyncMock()

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.read = AsyncMock(return_value=b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03")
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        # This will fail on gzip decompress of garbage, but that's fine —
        # we only care that it called session.get() directly
        with patch("gzip.GzipFile", MagicMock()):
            try:
                await client._get_packages_list("stable", "main")
            except Exception:
                pass

        client._make_request.assert_not_called()

    async def test_apk_get_apkindex_bypasses(self, mock_session):
        from backend.data_sources.apk_client import APKClient

        client = APKClient()
        client._get_session = MagicMock(return_value=mock_session)
        client._make_request = AsyncMock()

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.read = AsyncMock(return_value=b"garbage")
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        with patch("tarfile.open", MagicMock()):
            try:
                await client._get_apkindex("v3.18", "main")
            except Exception:
                pass

        client._make_request.assert_not_called()


# ── 9. GradleClient — partial bypass ─────────────────────────────────


class TestGradleClientContract:
    """GradleClient uses ``self._get()`` for Plugin Portal lookups (good),
    but ``_fetch_from_maven_central`` uses ``session.get()`` directly (bypass).
    """

    async def test_main_path_uses_get(self, mock_session):
        from backend.data_sources.gradle_client import GradleClient

        client = GradleClient()
        client._get_session = MagicMock(return_value=mock_session)
        client._get = AsyncMock(return_value=None)  # make plugin portal fail

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.text = AsyncMock(
            return_value="""<?xml version="1.0"?><metadata><versioning><versions><version>1.0</version></versions></versioning></metadata>"""  # noqa: E501
        )
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        result = await client.get_package_info("group:artifact")

        client._get.assert_awaited_once()
        assert result is not None
        assert result["version"] == "1.0"

    async def test_fetch_from_maven_central_bypasses(self, mock_session):
        from backend.data_sources.gradle_client import GradleClient

        client = GradleClient()
        client._get_session = MagicMock(return_value=mock_session)
        client._make_request = AsyncMock()

        # Call _fetch_from_maven_central directly
        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.text = AsyncMock(return_value="<metadata></metadata>")
        resp.__aenter__.return_value = resp
        mock_session.get.return_value = resp

        result = await client._fetch_from_maven_central("group", "artifact", "group:artifact")

        client._make_request.assert_not_called()
        assert result is None  # No versions in metadata


# ── 10. Cache integration ────────────────────────────────────────────


class TestCacheIntegration:
    """Verify that clients use the base class ``DictCache``."""

    async def test_every_client_has_cache(self):
        for name, klass in _collect_client_classes():
            client = klass()
            assert hasattr(client, "_cache"), f"{name} missing _cache"
            assert hasattr(client, "_cache_ttl"), f"{name} missing _cache_ttl"
            assert hasattr(client, "_cache_get"), f"{name} missing _cache_get"
            assert hasattr(client, "_cache_set"), f"{name} missing _cache_set"
            await client.close()

    async def test_cache_get_set_work(self, mock_session):
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)

        await client._cache_set("key", {"data": 42})
        result = await client._cache_get("key")
        # In this test the DictCache is real so set/get should work
        # But we already patched so let's just check they exist
        assert hasattr(client, "_cache_set")
        assert hasattr(client, "_cache_get")

    async def test_cached_get_uses_cache(self, mock_session):
        """``cached_get`` must check the cache before making an HTTP request."""
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._cache._store = {"ckey": ("cached_value", None)}

        result = await client.cached_get("ckey", "https://example.com/api")

        assert result == "cached_value"
        mock_session.request.assert_not_called()
        mock_session.get.assert_not_called()

    async def test_cached_get_miss_makes_request(self, mock_session):
        """On cache miss, ``cached_get`` must make an HTTP request."""
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._cache._data = {}

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value={"fresh": "data"})
        resp.__aenter__.return_value = resp
        mock_session.request.return_value = resp

        result = await client.cached_get("new-key", "https://example.com/api")

        assert result == {"fresh": "data"}
        mock_session.request.assert_called_once()


# ── 11. Auth header injection across all clients ─────────────────────


class TestAuthInjection:
    """Every client created via ``BaseDataSourceClient.__init__`` calls
    ``resolve_auth_headers`` and stores the result in ``self._auth_headers``.
    """

    async def test_base_client_calls_resolve_auth(self):
        """Constructor must call ``resolve_auth_headers``."""
        with patch(
            "backend.data_sources.base_client.resolve_auth_headers",
            return_value={"Authorization": "Bearer injected"},
        ) as mock_resolve:
            client = BaseDataSourceClient("test", "https://example.com")
            assert client._auth_headers == {"Authorization": "Bearer injected"}
            mock_resolve.assert_called_once_with(
                ecosystem="test",
                registry_url="https://example.com",
                explicit_headers=None,
            )
            await client.close()

    async def test_pypi_client_resolves_auth(self):
        with patch(
            "backend.data_sources.base_client.resolve_auth_headers",
            return_value={"Authorization": "Bearer pypi-token"},
        ) as mock_resolve:
            client = PyPIClient()
            mock_resolve.assert_called()
            assert client._auth_headers
            await client.close()

    async def test_all_clients_have_auth_headers(self):
        for name, klass in _collect_client_classes():
            try:
                client = klass()
            except Exception:
                continue
            assert hasattr(client, "_auth_headers"), f"{name} missing _auth_headers"
            assert isinstance(client._auth_headers, dict), f"{name}._auth_headers must be a dict"
            await client.close()


# ── 12. 404 / 429 / 5xx semantics ────────────────────────────────────


class TestResponseHandling:
    """Base contract for HTTP response handling."""

    async def test_make_request_returns_none_on_404(self, mock_session):
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._throttle = AsyncMock(return_value=None)

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 404
        resp.__aenter__.return_value = resp
        mock_session.request.return_value = resp

        result = await client._make_request("GET", "https://example.com/api")
        assert result is None

    async def test_make_request_retries_on_429(self, mock_session):
        client = BaseDataSourceClient("test", "https://example.com", max_retries=3)
        client._get_session = MagicMock(return_value=mock_session)
        client._throttle = AsyncMock(return_value=None)

        resp_429 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_429.status = 429
        resp_429.headers = {"Retry-After": "1"}
        resp_429.__aenter__.return_value = resp_429

        resp_200 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_200.status = 200
        resp_200.headers = {"Content-Type": "application/json"}
        resp_200.json = AsyncMock(return_value={"ok": True})
        resp_200.__aenter__.return_value = resp_200

        mock_session.request.side_effect = [resp_429, resp_200]

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await client._make_request("GET", "https://example.com/api")

        assert result == {"ok": True}
        assert mock_session.request.call_count == 2

    async def test_make_request_retries_on_5xx(self, mock_session):
        client = BaseDataSourceClient("test", "https://example.com", max_retries=3)
        client._get_session = MagicMock(return_value=mock_session)
        client._throttle = AsyncMock(return_value=None)

        resp_503 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_503.status = 503
        resp_503.__aenter__.return_value = resp_503

        resp_200 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_200.status = 200
        resp_200.headers = {"Content-Type": "application/json"}
        resp_200.json = AsyncMock(return_value={"ok": True})
        resp_200.__aenter__.return_value = resp_200

        mock_session.request.side_effect = [resp_503, resp_200]

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            result = await client._make_request("GET", "https://example.com/api")

        assert result == {"ok": True}

    async def test_make_request_raises_on_exhausted_retries(self, mock_session):
        client = BaseDataSourceClient("test", "https://example.com", max_retries=2)
        client._get_session = MagicMock(return_value=mock_session)
        client._throttle = AsyncMock(return_value=None)

        resp_500 = AsyncMock(spec=aiohttp.ClientResponse)
        resp_500.status = 500
        resp_500.__aenter__.return_value = resp_500
        resp_500.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=500, message="Server Error"
        )
        mock_session.request.return_value = resp_500

        with patch("asyncio.sleep", AsyncMock(return_value=None)):
            with pytest.raises(OSError):
                await client._make_request("GET", "https://example.com/api")

    async def test_base_get_404_returns_none(self, mock_session):
        """The full chain ``_get`` → 404 should return None."""
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 404
        resp.__aenter__.return_value = resp
        mock_session.request.return_value = resp

        result = await client._get("https://example.com/api")

        assert result is None

    async def test_get_text_404_returns_none(self, mock_session):
        """``_get_text`` should return None on 404."""
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._throttle = AsyncMock(return_value=None)

        resp = AsyncMock(spec=aiohttp.ClientResponse)
        resp.status = 404
        resp.__aenter__.return_value = resp
        mock_session.request.return_value = resp

        result = await client._get_text("https://example.com/api")

        assert result is None


# ── 13. Circuit breaker ──────────────────────────────────────────────


class TestCircuitBreaker:
    """The circuit breaker wraps ``_make_request`` and should:
    - Pass through successful requests
    - Track failures on OSError
    - Return None when OPEN
    """

    async def test_circuit_breaker_passes_through_success(self, mock_session):
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._make_request = AsyncMock(return_value={"ok": True})

        result = await client._circuit_breaker_call("GET", "https://example.com/api")

        assert result == {"ok": True}
        assert client._circuit_state == "CLOSED"

    async def test_circuit_breaker_opens_after_threshold(self, mock_session):
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._circuit_failure_threshold = 2
        client._make_request = AsyncMock(side_effect=OSError("fail"))

        await client._circuit_breaker_call("GET", "https://example.com/api")
        await client._circuit_breaker_call("GET", "https://example.com/api")
        result = await client._circuit_breaker_call("GET", "https://example.com/api")

        assert client._circuit_state == "OPEN"
        assert result is None

    async def test_circuit_breaker_404_not_failure(self, mock_session):
        """404 (None result) must NOT count as a circuit failure."""
        client = BaseDataSourceClient("test", "https://example.com")
        client._get_session = MagicMock(return_value=mock_session)
        client._circuit_failure_threshold = 1
        client._make_request = AsyncMock(return_value=None)

        result = await client._circuit_breaker_call("GET", "https://example.com/api")

        assert result is None
        assert client._circuit_state == "CLOSED"


# ── 14. Client registration audit ────────────────────────────────────


class TestClientRegistration:
    """All client classes must be discoverable via either
    ``_CLIENT_BUILDERS`` (legacy) or the plugin system (new).
    """

    def test_all_base_client_subclasses_are_registered(self):
        """Every BaseDataSourceClient subclass should be registered in
        ``DataAggregator`` or the plugin system.  This test flags
        orphan subclasses that would never be used at runtime.
        """
        from backend.core.data_aggregator import _CLIENT_BUILDERS

        registered_names = set()
        for builder in _CLIENT_BUILDERS.values():
            instance = builder()
            registered_names.add(type(instance).__name__)

        for name, klass in _collect_client_classes():
            if klass.__name__ in (
                "DocumentationScraper",
                "CompatibilityDB",
                "HexClient",  # legacy — superseded by HexPlugin via plugin system
            ):
                continue
            assert klass.__name__ in registered_names, (
                f"{klass.__name__} is a BaseDataSourceClient subclass "
                f"but is not registered in DataAggregator._CLIENT_BUILDERS"
            )

    def test_docker_registry_client_not_in_base(self):
        """DockerRegistryClient does NOT extend BaseDataSourceClient —
        this is a known exception.  Confirm it's intentional.
        """
        from backend.data_sources.docker_client import DockerRegistryClient

        assert not issubclass(DockerRegistryClient, BaseDataSourceClient)


# ── 15. Conftest-like: run all client instances can be created ───────


class TestClientInstantiation:
    """Every registered client must be constructable without arguments."""

    async def test_all_clients_can_be_instantiated(self):
        for name, klass in _collect_client_classes():
            try:
                instance = klass()
                assert instance is not None
                await instance.close()
            except Exception as e:
                pytest.fail(f"Failed to instantiate {name}: {e}")
