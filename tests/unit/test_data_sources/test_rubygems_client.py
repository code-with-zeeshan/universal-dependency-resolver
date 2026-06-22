from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.rubygems_client import RubyGemsClient


class TestRubyGemsClient:
    @pytest.fixture
    def client(self):
        return RubyGemsClient()

    @pytest.fixture
    def sample_gem_data(self):
        return {
            "name": "rails",
            "version": "7.1.2",
            "info": "Ruby on Rails is a full-stack web framework",
            "homepage_uri": "https://rubyonrails.org",
            "source_code_uri": "https://github.com/rails/rails",
            "documentation_uri": "https://guides.rubyonrails.org",
            "licenses": ["MIT"],
            "authors": "David Heinemeier Hansson",
            "gem_uri": "https://rubygems.org/gems/rails-7.1.2.gem",
            "downloads": 50000000,
            "version_downloads": 1000000,
            "platform": "ruby",
        }

    @pytest.fixture
    def sample_versions_data(self):
        return [{"number": "7.1.2", "created_at": "2023-11-10", "downloads": 100000,
                 "platform": "ruby", "licenses": ["MIT"], "ruby_version": ">=2.7"},
                {"number": "7.1.1", "created_at": "2023-10-15", "downloads": 50000,
                 "platform": "ruby", "licenses": ["MIT"], "ruby_version": ">=2.7"}]

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_gem_data):
        with patch.object(client, 'cached_get', new_callable=AsyncMock, return_value=sample_gem_data):
            result = await client.get_package_info_async('rails')
        assert result is not None
        assert result['name'] == 'rails'
        assert result['version'] == '7.1.2'

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(self, client, sample_gem_data):
        with patch.object(client, 'cached_get', new_callable=AsyncMock, return_value=sample_gem_data) as mock_get:
            await client.get_package_info_async('rails')
        mock_get.assert_called_once()
        cache_key, url = mock_get.call_args[0]
        assert 'rails' in cache_key

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(client, 'cached_get', new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info_async('nonexistent')
        assert result is None

    def test_get_package_info_sync_success(self, client, sample_gem_data):
        with patch.object(client, 'get_package_info_async', new_callable=AsyncMock, return_value=sample_gem_data):
            result = client.get_package_info('rails')
        assert result is not None
        assert result['name'] == 'rails'

    def test_package_exists_returns_true(self, client):
        with patch('requests.head') as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_head.return_value = mock_response
            assert client.package_exists('rails') is True

    def test_package_exists_returns_false(self, client):
        with patch('requests.head') as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_head.return_value = mock_response
            assert client.package_exists('nonexistent') is False

    def test_package_exists_handles_exception(self, client):
        with patch('requests.head', side_effect=Exception('Network error')):
            assert client.package_exists('rails') is False

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_gem_data):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=[sample_gem_data]):
            results = await client.search_packages('rails', limit=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_packages_calls_correct_url(self, client, sample_gem_data):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=[sample_gem_data]) as mock_get:
            await client.search_packages('rails', limit=5)
        url = mock_get.call_args[0][0]
        assert 'query=rails' in url.lower() or 'q=rails' in url.lower()

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_no_results(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=[]):
            results = await client.search_packages('nonexistent')
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_exception(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, side_effect=Exception('Error')):
            results = await client.search_packages('rails')
        assert results == []

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_versions_data):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=sample_versions_data):
            versions = await client.get_versions('rails')
        assert len(versions) == 2
        assert versions[0]['number'] == '7.1.2'

    @pytest.mark.asyncio
    async def test_get_versions_empty_on_error(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=None):
            versions = await client.get_versions('nonexistent')
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_version_success(self, client, sample_gem_data):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=sample_gem_data):
            result = await client.get_package_version('rails', '7.1.2')
        assert result is not None
        assert result['version'] == '7.1.2'

    @pytest.mark.asyncio
    async def test_get_package_version_not_found(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=None):
            result = await client.get_package_version('rails', '999.0.0')
        assert result is None

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client):
        mock_deps = {"dependencies": {"runtime": [{"name": "activesupport", "requirements": ">=7.1.0"}],
                                       "development": [{"name": "sqlite3", "requirements": "~> 1.4"}]}}
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=mock_deps):
            deps = await client.get_dependencies('rails', '7.1.2')
        assert 'runtime' in deps.get('dependencies', deps)

    @pytest.mark.asyncio
    async def test_get_dependencies_empty_on_error(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=None):
            deps = await client.get_dependencies('nonexistent', '1.0')
        assert deps == {}

    @pytest.mark.asyncio
    async def test_check_compatibility_returns_result(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value={"ruby_version": ">=2.7"}):
            result = await client.check_compatibility('rails', '7.1.2', {"ruby": "3.2.0"})
        assert isinstance(result, dict)
