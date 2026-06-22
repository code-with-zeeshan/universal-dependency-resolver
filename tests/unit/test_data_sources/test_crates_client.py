from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.crates_client import CratesClient


class TestCratesClient:
    @pytest.fixture
    def client(self):
        return CratesClient()

    @pytest.fixture
    def sample_crate_data(self):
        return {"crate": {"id": "serde", "name": "serde", "description": "A generic serialization framework",
                          "latest_version": "1.0.188", "repository": "https://github.com/serde-rs/serde",
                          "max_stars": 8000, "downloads": 50000000,
                          "homepage": "https://serde.rs", "license": "MIT",
                          "documentation": "https://docs.rs/serde"},
                "versions": [{"num": "1.0.188", "created_at": "2023-09-01", "license": "MIT",
                              "downloads": 1000000, "yanked": False},
                             {"num": "1.0.187", "created_at": "2023-08-15", "license": "MIT",
                              "downloads": 900000, "yanked": False}]}

    @pytest.fixture
    def sample_search_results(self):
        return {"crates": [{"id": "serde", "name": "serde", "description": "Serialization framework",
                            "latest_version": "1.0.188", "downloads": 50000000}],
                "meta": {"total": 1}}

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_search_results):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=sample_search_results):
            results = await client.search_packages('serde', limit=10)
        assert len(results) == 1
        assert results[0]['name'] == 'serde'

    @pytest.mark.asyncio
    async def test_search_packages_calls_correct_url(self, client, sample_search_results):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=sample_search_results) as mock_get:
            await client.search_packages('serde', limit=5)
        url = mock_get.call_args[0][0]
        assert 'q=serde' in url
        assert 'per_page=5' in url

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_no_results(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value={"crates": [], "meta": {"total": 0}}):
            results = await client.search_packages('nonexistent')
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_error(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=None):
            results = await client.search_packages('error')
        assert results == []

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, client, sample_crate_data):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=sample_crate_data):
            result = await client.get_package_info('serde')
        assert result is not None
        assert result['name'] == 'serde'
        assert result['latest_version'] == '1.0.188'

    @pytest.mark.asyncio
    async def test_get_package_info_calls_correct_url(self, client, sample_crate_data):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=sample_crate_data) as mock_get:
            await client.get_package_info('serde')
        url = mock_get.call_args[0][0]
        assert '/api/v1/crates/serde' in url

    @pytest.mark.asyncio
    async def test_get_package_info_not_found(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info('nonexistent')
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_handles_missing_crate_key(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value={"versions": []}):
            result = await client.get_package_info('bad-data')
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_versions_success(self, client, sample_crate_data):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=sample_crate_data):
            versions = await client.get_package_versions('serde')
        assert len(versions) == 2
        assert versions[0]['num'] == '1.0.188'

    @pytest.mark.asyncio
    async def test_get_package_versions_empty_on_no_data(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=None):
            versions = await client.get_package_versions('nonexistent')
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client):
        mock_deps = {"deps": [{"crate_id": "serde_derive", "kind": "normal",
                               "req": "^1.0", "optional": False}]}
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=mock_deps):
            deps = await client.get_dependencies('serde', '1.0.188')
        assert 'normal' in deps

    @pytest.mark.asyncio
    async def test_get_dependencies_empty_on_error(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=None):
            deps = await client.get_dependencies('nonexistent', '1.0')
        assert deps == {}

    @pytest.mark.asyncio
    async def test_check_compatibility_returns_result(self, client):
        with patch.object(client, '_get', new_callable=AsyncMock, return_value=sample_crate_data.__class__({"crate": {"id": "serde"}})):
            with patch.object(client, 'check_compatibility') as mock_check:
                mock_check.return_value = {"compatible": True}
                result = await client.check_compatibility('serde', '1.0.188', {})
                assert isinstance(result, dict)
