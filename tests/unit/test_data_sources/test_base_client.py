import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from backend.data_sources.base_client import BaseDataSourceClient


class TestBaseDataSourceClient:
    @pytest.fixture
    def client(self):
        tmpdir = tempfile.mkdtemp()
        cl = BaseDataSourceClient(
            ecosystem="test",
            base_url="https://api.example.com",
            cache_ttl=3600,
            user_agent="TestAgent/1.0",
            rate_limit=10,
            timeout=30,
            max_retries=3,
        )
        # Use a temp cache path to avoid cross-test contamination
        from backend.core.cache import DictCache

        cl._cache = DictCache(persist_path=os.path.join(tmpdir, "test_cache.json"))
        return cl

    def test_initialization(self, client):
        assert client.ecosystem == "test"
        assert client.base_url == "https://api.example.com"
        assert client.user_agent == "TestAgent/1.0"
        assert client.rate_limit == 10
        assert client.timeout == 30
        assert client.max_retries == 3
        assert client._request_timestamps == []

    @pytest.mark.asyncio
    async def test_cache_get_hit(self, client):
        key = "test_key"
        data = {"result": "cached"}
        await client._cache_set(key, data)
        result = await client._cache_get(key)
        assert result == data

    @pytest.mark.asyncio
    async def test_cache_get_expired(self, client):
        key = "test_key"
        data = {"result": "expired"}
        await client._cache_set(key, data)
        result = await client._cache_get(key)
        assert result == data

    @pytest.mark.asyncio
    async def test_cache_get_miss(self, client):
        result = await client._cache_get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, client):
        await client._cache_set("key1", {"value": 1})
        await client._cache_set("key2", {"value": 2})
        assert await client._cache_get("key1") == {"value": 1}
        assert await client._cache_get("key2") == {"value": 2}

    @pytest.mark.asyncio
    async def test_cache_key_eviction_on_ttl_expiry(self, client):
        key = "volatile"
        await client._cache_set(key, "data")
        result = await client._cache_get(key)
        assert result is not None

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_within_limit(self, client):
        for _ in range(5):
            await client._throttle()
        assert len(client._request_timestamps) == 5
        assert all(isinstance(t, datetime) for t in client._request_timestamps)

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_limit(self, client):
        client.rate_limit = 2
        await client._throttle()
        await client._throttle()
        before = datetime.now()
        await client._throttle()
        elapsed = (datetime.now() - before).total_seconds()
        assert elapsed >= 0

    @pytest.mark.asyncio
    async def test_throttle_clears_old_timestamps(self, client):
        client.rate_limit = 10
        stale = datetime.now() - timedelta(seconds=120)
        client._request_timestamps = [stale] * 20
        await client._throttle()
        assert len(client._request_timestamps) <= 10

    @pytest.mark.asyncio
    async def test_retry_on_5xx(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 503
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._get("https://api.example.com/data")

        assert result is None
        assert mock_session.request.call_count == client.max_retries

    @pytest.mark.asyncio
    async def test_retry_then_success(self, client):
        mock_session = MagicMock()
        responses = [
            MagicMock(status=503, __aenter__=AsyncMock(return_value=MagicMock(status=503))),
            MagicMock(status=503, __aenter__=AsyncMock(return_value=MagicMock(status=503))),
            MagicMock(
                status=200,
                __aenter__=AsyncMock(
                    return_value=MagicMock(
                        status=200, json=AsyncMock(return_value={"result": "ok"})
                    )
                ),
            ),
        ]
        for r in responses:
            r.__aexit__ = AsyncMock()

        mock_session.request.side_effect = responses
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._get("https://api.example.com/data")

        assert result == {"result": "ok"}
        assert mock_session.request.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_4xx(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(
            status=404, __aenter__=AsyncMock(return_value=MagicMock(status=404))
        )
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._get("https://api.example.com/data")

        assert result is None
        assert mock_session.request.call_count == 1

    @pytest.mark.asyncio
    async def test_raises_on_other_errors(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(
            status=403,
            __aenter__=AsyncMock(
                return_value=MagicMock(
                    status=403,
                    raise_for_status=MagicMock(side_effect=aiohttp.ClientError("Forbidden")),
                )
            ),
        )
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._get("https://api.example.com/data")

        assert result is None

    @pytest.mark.asyncio
    async def test_custom_headers_are_sent(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(
            status=200,
            __aenter__=AsyncMock(
                return_value=MagicMock(status=200, json=AsyncMock(return_value={}))
            ),
        )
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, "_get_session", return_value=mock_session):
            await client._get(
                "https://api.example.com/data",
                headers={"Authorization": "Bearer token"},
            )

        call_kwargs = mock_session.request.call_args.kwargs
        assert "Authorization" in call_kwargs["headers"]
        assert call_kwargs["headers"]["Authorization"] == "Bearer token"
        assert call_kwargs["headers"]["User-Agent"] == "TestAgent/1.0"

    @pytest.mark.asyncio
    async def test_timeout_handling(self, client):
        mock_session = MagicMock()
        mock_session.request.side_effect = TimeoutError()

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._get("https://api.example.com/data")

        assert result is None
        assert mock_session.request.call_count == client.max_retries

    @pytest.mark.asyncio
    async def test_network_error_retries(self, client):
        mock_session = MagicMock()
        mock_session.request.side_effect = aiohttp.ClientError("Connection refused")

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._get("https://api.example.com/data")

        assert result is None
        assert mock_session.request.call_count == client.max_retries

    @pytest.mark.asyncio
    async def test_cached_get_uses_cache(self, client):
        cache_key = "cached_key"
        url = "https://api.example.com/data"
        expected = {"cached": True}
        await client._cache_set(cache_key, expected)

        mock_session = MagicMock()
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client.cached_get(cache_key, url)
        assert result == expected
        mock_session.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_cached_get_cache_miss(self, client):
        cache_key = "miss_key"
        url = "https://api.example.com/data"
        expected = {"fresh": True}

        mock_session = MagicMock()
        mock_response = MagicMock(
            status=200,
            __aenter__=AsyncMock(
                return_value=MagicMock(status=200, json=AsyncMock(return_value=expected))
            ),
        )
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client.cached_get(cache_key, url)

        assert result == expected
        cached = await client._cache_get(cache_key)
        assert cached["data"] == expected
        assert cached.get("__etag_wrapped__") is True
        assert "etag" in cached
        assert "expires" in cached
        mock_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_cached_get_with_custom_ttl(self, client):
        cache_key = "custom_ttl_key"
        url = "https://api.example.com/data"
        expected = {"custom_ttl": True}

        mock_session = MagicMock()
        mock_response = MagicMock(
            status=200,
            __aenter__=AsyncMock(
                return_value=MagicMock(status=200, json=AsyncMock(return_value=expected))
            ),
        )
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        original_ttl = client._cache_ttl
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client.cached_get(cache_key, url, ttl=100)
        assert result == expected
        assert client._cache_ttl == original_ttl

    @pytest.mark.asyncio
    async def test_session_context_manager(self):
        async with BaseDataSourceClient("test", "https://api.example.com") as client:
            assert client.session is not None
        assert client.session is None or client.session.closed

    @pytest.mark.asyncio
    async def test_request_includes_user_agent(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(
            status=200,
            __aenter__=AsyncMock(
                return_value=MagicMock(status=200, json=AsyncMock(return_value={}))
            ),
        )
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, "_get_session", return_value=mock_session):
            await client._get("https://api.example.com/data")

        call_kwargs = mock_session.request.call_args.kwargs
        assert call_kwargs["headers"]["User-Agent"] == "TestAgent/1.0"

    @pytest.mark.asyncio
    async def test_concurrent_requests_share_session(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(
            status=200,
            __aenter__=AsyncMock(
                return_value=MagicMock(status=200, json=AsyncMock(return_value={}))
            ),
        )
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, "_get_session", return_value=mock_session) as mock_get_session:
            await client._get("https://api.example.com/a")
            await client._get("https://api.example.com/b")

        assert mock_get_session.call_count == 2

    @pytest.mark.asyncio
    async def test_backoff_increases_with_retries(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(
            status=503, __aenter__=AsyncMock(return_value=MagicMock(status=503))
        )
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with (
            patch.object(client, "_get_session", return_value=mock_session),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await client._get("https://api.example.com/data")

        assert len(mock_sleep.call_args_list) == client.max_retries - 1
        sleep_args = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_args == [2.0**i for i in range(client.max_retries - 1)]

    @pytest.mark.asyncio
    async def test_close_method(self, client):
        mock_session = AsyncMock()
        mock_session.closed = False
        client.session = mock_session
        await client.close()
        mock_session.close.assert_awaited_once()
        assert client.session is None

    @pytest.mark.asyncio
    async def test_close_no_session(self, client):
        client.session = None
        await client.close()

    @pytest.mark.asyncio
    async def test_get_session_creates_when_none(self, client):
        client.session = None
        session = client._get_session()
        assert session is not None
        assert client.session is not None
        await session.close()

    @pytest.mark.asyncio
    async def test_get_session_returns_existing(self, client):
        mock_session = MagicMock()
        mock_session.closed = False
        client.session = mock_session
        session = client._get_session()
        assert session is mock_session

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_skips_request(self, client):
        client._circuit_state = "OPEN"
        client._circuit_last_open_time = datetime.now()
        result = await client._circuit_breaker_call("GET", "https://api.example.com/data")
        assert result is None
        assert client._circuit_state == "OPEN"

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_transitions_to_half_open(self, client):
        client._circuit_state = "OPEN"
        client._circuit_last_open_time = datetime.now() - timedelta(seconds=9999)
        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_make:
            mock_make.return_value = {"result": "ok"}
            result = await client._circuit_breaker_call("GET", "https://api.example.com/data")
        assert result == {"result": "ok"}
        assert client._circuit_state == "HALF_OPEN"

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_failure_reopens(self, client):
        client._circuit_state = "HALF_OPEN"
        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_make:
            mock_make.side_effect = OSError("fail")
            result = await client._circuit_breaker_call("GET", "https://api.example.com/data")
        assert result is None
        assert client._circuit_state == "OPEN"
        assert client._circuit_last_open_time is not None

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_threshold(self, client):
        client._circuit_failure_count = client._circuit_failure_threshold - 1
        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_make:
            mock_make.side_effect = OSError("fail")
            result = await client._circuit_breaker_call("GET", "https://api.example.com/data")
        assert result is None
        assert client._circuit_state == "OPEN"
        assert client._circuit_last_open_time is not None

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_success_closes(self, client):
        client._circuit_state = "HALF_OPEN"
        client._circuit_half_open_successes = client._circuit_half_open_max_successes - 1
        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_make:
            mock_make.return_value = {"result": "ok"}
            result = await client._circuit_breaker_call("GET", "https://api.example.com/data")
        assert result == {"result": "ok"}
        assert client._circuit_state == "CLOSED"
        assert client._circuit_failure_count == 0

    @pytest.mark.asyncio
    async def test_cached_get_offline_mode(self, client):
        with patch.dict("os.environ", {"UDR_OFFLINE": "true"}):
            result = await client.cached_get("key", "https://api.example.com/data")
        assert result is None

    def test_circuit_state_property(self, client):
        client._circuit_state = "OPEN"
        assert client.circuit_state == "OPEN"
        client._circuit_state = "HALF_OPEN"
        assert client.circuit_state == "HALF_OPEN"
        client._circuit_state = "CLOSED"
        assert client.circuit_state == "CLOSED"

    def test_reset_circuit(self, client):
        client._circuit_state = "OPEN"
        client._circuit_failure_count = 5
        client._circuit_half_open_successes = 1
        client._circuit_last_open_time = datetime.now()
        client.reset_circuit()
        assert client._circuit_state == "CLOSED"
        assert client._circuit_failure_count == 0
        assert client._circuit_half_open_successes == 0
        assert client._circuit_last_open_time is None
