from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.nuget_client import NuGetClient


class TestNuGetClient:
    @pytest.fixture
    def client(self):
        return NuGetClient()

    @pytest.fixture
    def sample_package_data(self):
        return {
            "@id": "https://api.nuget.org/v3/registration5-semver1/newtonsoft.json/index.json",
            "id": "Newtonsoft.Json",
            "version": "13.0.3",
            "description": "Json.NET is a popular high-performance JSON framework for .NET",
            "authors": "James Newton-King",
            "licenseUrl": "https://licenses.nuget.org/MIT",
            "projectUrl": "https://www.newtonsoft.com/json",
            "tags": ["json", "serialization", "framework"],
            "published": "2023-08-15T00:00:00+00:00",
            "dependencyGroups": [{"@type": "PackageDependencyGroup",
                                  "targetFramework": ".NETStandard2.0",
                                  "dependencies": []}],
        }

    @pytest.fixture
    def sample_search_results(self):
        return {"data": [{"id": "Newtonsoft.Json", "version": "13.0.3",
                          "description": "JSON framework for .NET",
                          "totalDownloads": 3000000000,
                          "tags": ["json", "serialization"]}]}

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_package_data):
        with patch.object(client, 'cached_get', new_callable=AsyncMock, return_value=sample_package_data):
            result = await client.get_package_info_async('Newtonsoft.Json')
        assert result is not None
        assert result['id'] == 'Newtonsoft.Json'
        assert result['version'] == '13.0.3'

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(self, client, sample_package_data):
        with patch.object(client, 'cached_get', new_callable=AsyncMock, return_value=sample_package_data) as mock_get:
            await client.get_package_info_async('Newtonsoft.Json')
        mock_get.assert_called_once()
        cache_key, url = mock_get.call_args[0]
        assert 'newtonsoft' in cache_key.lower()

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(client, 'cached_get', new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info_async('Nonexistent.Package')
        assert result is None

    def test_get_package_info_sync_success(self, client, sample_package_data):
        with patch.object(client, 'get_package_info_async', new_callable=AsyncMock, return_value=sample_package_data):
            result = client.get_package_info('Newtonsoft.Json')
        assert result is not None
        assert result['id'] == 'Newtonsoft.Json'

    def test_package_exists_returns_true(self, client):
        with patch.object(client, 'get_package_info_async', new_callable=AsyncMock, return_value={"id": "Newtonsoft.Json"}):
            assert client.package_exists('Newtonsoft.Json') is True

    def test_package_exists_returns_false(self, client):
        with patch.object(client, 'get_package_info_async', new_callable=AsyncMock, return_value=None):
            assert client.package_exists('Nonexistent.Package') is False

    def test_package_exists_handles_exception(self, client):
        with patch.object(client, 'get_package_info_async', new_callable=AsyncMock, side_effect=Exception('Error')):
            assert client.package_exists('Newtonsoft.Json') is False

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_search_results):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=sample_search_results):
            results = await client.search_packages('json', limit=10)
        assert len(results) == 1
        assert results[0]['id'] == 'Newtonsoft.Json'

    @pytest.mark.asyncio
    async def test_search_packages_calls_correct_url(self, client, sample_search_results):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=sample_search_results) as mock_get:
            await client.search_packages('json', limit=5)
        url = mock_get.call_args[0][0]
        assert 'q=json' in url
        assert 'take=5' in url

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_no_results(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value={"data": []}):
            results = await client.search_packages('nonexistent')
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_exception(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, side_effect=Exception('Error')):
            results = await client.search_packages('json')
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_with_prerelease_filter(self, client, sample_search_results):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=sample_search_results) as mock_get:
            await client.search_packages('json', include_prerelease=True)
        url = mock_get.call_args[0][0]
        assert 'prerelease=true' in url

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client):
        mock_registration = {"items": [{"items": [{"catalogEntry": {"version": "13.0.3",
                                           "published": "2023-08-15", "projectUrl": "https://newtonsoft.com"}},
                                          {"catalogEntry": {"version": "13.0.2",
                                           "published": "2023-06-01", "projectUrl": "https://newtonsoft.com"}}]}]}
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=mock_registration):
            versions = await client.get_versions('Newtonsoft.Json')
        assert len(versions) >= 1
        assert all('version' in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_empty_on_no_package(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=None):
            versions = await client.get_versions('Nonexistent.Package')
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_version_success(self, client, sample_package_data):
        with patch.object(client, 'cached_get', new_callable=AsyncMock, return_value=sample_package_data):
            result = await client.get_package_version('Newtonsoft.Json', '13.0.3')
        assert result is not None
        assert result['version'] == '13.0.3'

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client, sample_package_data):
        with patch.object(client, 'cached_get', new_callable=AsyncMock, return_value=sample_package_data):
            deps = await client.get_dependencies('Newtonsoft.Json', '13.0.3')
        assert isinstance(deps, dict)

    @pytest.mark.asyncio
    async def test_get_dependencies_empty_on_error(self, client):
        with patch.object(client, 'cached_get', new_callable=AsyncMock, return_value=None):
            deps = await client.get_dependencies('Nonexistent.Package', '1.0')
        assert deps == {}

    @pytest.mark.asyncio
    async def test_check_compatibility_returns_result(self, client, sample_package_data):
        with patch.object(client, 'get_package_info_async', new_callable=AsyncMock, return_value=sample_package_data):
            result = await client.check_compatibility('Newtonsoft.Json', '13.0.3', {})
        assert isinstance(result, dict)
