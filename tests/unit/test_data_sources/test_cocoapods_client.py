from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.cocoapods_client import CocoaPodsClient


class TestCocoaPodsClient:
    @pytest.fixture
    def client(self):
        return CocoaPodsClient()

    @pytest.fixture
    def sample_pod_data(self):
        return {
            "name": "Alamofire",
            "version": "5.7.1",
            "summary": "Elegant HTTP Networking in Swift",
            "homepage": "https://github.com/Alamofire/Alamofire",
            "license": "MIT",
            "authors": "Alamofire Software Foundation",
            "source": {
                "git": "https://github.com/Alamofire/Alamofire.git",
                "tag": "5.7.1",
            },
            "platforms": {"ios": "10.0", "osx": "10.12"},
            "swift_versions": ["5.3", "5.4", "5.5"],
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_pod_data):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=sample_pod_data
        ):
            result = await client.get_package_info_async("Alamofire")
        assert result is not None
        assert result["name"] == "Alamofire"
        assert result["version"] == "5.7.1"

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(
        self, client, sample_pod_data
    ):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=sample_pod_data
        ) as mock_get:
            await client.get_package_info_async("Alamofire")
        mock_get.assert_called_once()
        cache_key, url = mock_get.call_args[0]
        assert "alamofire" in cache_key.lower()

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=None
        ):
            result = await client.get_package_info_async("nonexistent")
        assert result is None

    def test_get_package_info_sync_success(self, client, sample_pod_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_pod_data,
        ):
            result = client.get_package_info("Alamofire")
        assert result is not None
        assert result["name"] == "Alamofire"

    def test_package_exists_returns_true(self, client):
        with patch("requests.head") as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_head.return_value = mock_response
            assert client.package_exists("Alamofire") is True

    def test_package_exists_returns_false(self, client):
        with patch("requests.head") as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_head.return_value = mock_response
            assert client.package_exists("nonexistent") is False

    def test_package_exists_handles_exception(self, client):
        with patch("requests.head", side_effect=Exception("Network error")):
            assert client.package_exists("Alamofire") is False

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_pod_data):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=[sample_pod_data]
        ):
            results = await client.search_packages("Alamofire", limit=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_no_results(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=[]
        ):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_exception(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, side_effect=Exception("Error")
        ):
            results = await client.search_packages("Alamofire")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_pod_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_pod_data,
        ):
            versions = await client.get_versions("Alamofire")
        assert len(versions) >= 1
        assert all("version" in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_empty_when_no_package(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            versions = await client.get_versions("nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client):
        mock_deps = {"ios": ["UIKit", "Foundation"], "osx": ["AppKit"]}
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=mock_deps
        ):
            deps = await client.get_dependencies("Alamofire", "5.7.1")
        assert isinstance(deps, dict)

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_error(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=None
        ):
            deps = await client.get_dependencies("nonexistent", "1.0")
        assert deps == {}
