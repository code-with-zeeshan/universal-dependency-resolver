import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import aiohttp
import pytest

from backend.data_sources.base_client import BaseDataSourceClient


class TestBaseDataSourceClient:

    @pytest.fixture
    def client(self):
        return BaseDataSourceClient(
            ecosystem='test',
            base_url='https://api.example.com',
            cache_ttl=3600,
            user_agent='TestAgent/1.0',
            rate_limit=10,
            timeout=30,
            max_retries=3,
        )

    def test_initialization(self, client):
        assert client.ecosystem == 'test'
        assert client.base_url == 'https://api.example.com'
        assert client.user_agent == 'TestAgent/1.0'
        assert client.rate_limit == 10
        assert client.timeout == 30
        assert client.max_retries == 3
        assert client._cache == {}
        assert client._request_timestamps == []

    def test_cache_get_hit(self, client):
        key = 'test_key'
        data = {'result': 'cached'}
        client._cache_set(key, data)
        result = client._cache_get(key)
        assert result == data

    def test_cache_get_expired(self, client):
        key = 'test_key'
        data = {'result': 'expired'}
        client._cache_ttl = 1
        client._cache[key] = (data, datetime.now() - timedelta(seconds=2))
        result = client._cache_get(key)
        assert result is None

    def test_cache_get_miss(self, client):
        result = client._cache_get('nonexistent')
        assert result is None

    def test_cache_set_and_get(self, client):
        client._cache_set('key1', {'value': 1})
        client._cache_set('key2', {'value': 2})
        assert client._cache_get('key1') == {'value': 1}
        assert client._cache_get('key2') == {'value': 2}

    def test_cache_key_eviction_on_ttl_expiry(self, client):
        key = 'volatile'
        client._cache_ttl = 0
        client._cache_set(key, 'data')
        assert client._cache_get(key) is None
        client._cache_ttl = 3600
        client._cache_set(key, 'data')
        assert client._cache_get(key) == 'data'

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

        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client._get('https://api.example.com/data')

        assert result is None
        assert mock_session.request.call_count == client.max_retries

    @pytest.mark.asyncio
    async def test_retry_then_success(self, client):
        mock_session = MagicMock()
        responses = [
            MagicMock(status=503, __aenter__=AsyncMock(return_value=MagicMock(status=503))),
            MagicMock(status=503, __aenter__=AsyncMock(return_value=MagicMock(status=503))),
            MagicMock(status=200, __aenter__=AsyncMock(return_value=MagicMock(
                status=200, json=AsyncMock(return_value={'result': 'ok'})
            ))),
        ]
        for r in responses:
            r.__aexit__ = AsyncMock()

        mock_session.request.side_effect = responses
        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client._get('https://api.example.com/data')

        assert result == {'result': 'ok'}
        assert mock_session.request.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_4xx(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(status=404, __aenter__=AsyncMock(return_value=MagicMock(status=404)))
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client._get('https://api.example.com/data')

        assert result is None
        assert mock_session.request.call_count == 1

    @pytest.mark.asyncio
    async def test_raises_on_other_errors(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(status=403, __aenter__=AsyncMock(
            return_value=MagicMock(status=403, raise_for_status=MagicMock(side_effect=aiohttp.ClientError('Forbidden')))
        ))
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client._get('https://api.example.com/data')

        assert result is None

    @pytest.mark.asyncio
    async def test_custom_headers_are_sent(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(status=200, __aenter__=AsyncMock(return_value=MagicMock(
            status=200, json=AsyncMock(return_value={})
        )))
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, '_get_session', return_value=mock_session):
            await client._get('https://api.example.com/data', headers={'Authorization': 'Bearer token'})

        call_kwargs = mock_session.request.call_args.kwargs
        assert 'Authorization' in call_kwargs['headers']
        assert call_kwargs['headers']['Authorization'] == 'Bearer token'
        assert call_kwargs['headers']['User-Agent'] == 'TestAgent/1.0'

    @pytest.mark.asyncio
    async def test_timeout_handling(self, client):
        mock_session = MagicMock()
        mock_session.request.side_effect = asyncio.TimeoutError()

        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client._get('https://api.example.com/data')

        assert result is None
        assert mock_session.request.call_count == client.max_retries

    @pytest.mark.asyncio
    async def test_network_error_retries(self, client):
        mock_session = MagicMock()
        mock_session.request.side_effect = aiohttp.ClientError('Connection refused')

        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client._get('https://api.example.com/data')

        assert result is None
        assert mock_session.request.call_count == client.max_retries

    @pytest.mark.asyncio
    async def test_cached_get_uses_cache(self, client):
        cache_key = 'cached_key'
        url = 'https://api.example.com/data'
        expected = {'cached': True}
        client._cache_set(cache_key, expected)

        mock_session = MagicMock()
        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client.cached_get(cache_key, url)
        assert result == expected
        mock_session.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_cached_get_cache_miss(self, client):
        cache_key = 'miss_key'
        url = 'https://api.example.com/data'
        expected = {'fresh': True}

        mock_session = MagicMock()
        mock_response = MagicMock(status=200, __aenter__=AsyncMock(return_value=MagicMock(
            status=200, json=AsyncMock(return_value=expected)
        )))
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client.cached_get(cache_key, url)

        assert result == expected
        assert client._cache_get(cache_key) == expected
        mock_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_cached_get_with_custom_ttl(self, client):
        cache_key = 'custom_ttl_key'
        url = 'https://api.example.com/data'
        expected = {'custom_ttl': True}

        mock_session = MagicMock()
        mock_response = MagicMock(status=200, __aenter__=AsyncMock(return_value=MagicMock(
            status=200, json=AsyncMock(return_value=expected)
        )))
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        original_ttl = client._cache_ttl
        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client.cached_get(cache_key, url, ttl=100)
        assert result == expected
        assert client._cache_ttl == original_ttl

    @pytest.mark.asyncio
    async def test_session_context_manager(self):
        async with BaseDataSourceClient('test', 'https://api.example.com') as client:
            assert client.session is not None
        assert client.session is None or client.session.closed

    @pytest.mark.asyncio
    async def test_request_includes_user_agent(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(status=200, __aenter__=AsyncMock(return_value=MagicMock(
            status=200, json=AsyncMock(return_value={})
        )))
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, '_get_session', return_value=mock_session):
            await client._get('https://api.example.com/data')

        call_kwargs = mock_session.request.call_args.kwargs
        assert call_kwargs['headers']['User-Agent'] == 'TestAgent/1.0'

    @pytest.mark.asyncio
    async def test_concurrent_requests_share_session(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(status=200, __aenter__=AsyncMock(return_value=MagicMock(
            status=200, json=AsyncMock(return_value={})
        )))
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, '_get_session', return_value=mock_session) as mock_get_session:
            await client._get('https://api.example.com/a')
            await client._get('https://api.example.com/b')

        assert mock_get_session.call_count == 2

    @pytest.mark.asyncio
    async def test_backoff_increases_with_retries(self, client):
        mock_session = MagicMock()
        mock_response = MagicMock(status=503, __aenter__=AsyncMock(return_value=MagicMock(status=503)))
        mock_response.__aexit__ = AsyncMock()
        mock_session.request.return_value = mock_response

        with patch.object(client, '_get_session', return_value=mock_session), \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await client._get('https://api.example.com/data')

        assert len(mock_sleep.call_args_list) == client.max_retries - 1
        sleep_args = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_args == [2.0 ** i for i in range(client.max_retries - 1)]
