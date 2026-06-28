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
            client, "_get", new_callable=AsyncMock, return_value={"name": "Alamofire", "version": "5.7.1", "summary": "Elegant HTTP Networking in Swift", "homepage": "https://github.com/Alamofire/Alamofire", "license": "MIT", "authors": "Alamofire Software Foundation", "source": {"git": "https://github.com/Alamofire/Alamofire.git", "tag": "5.7.1"}, "platforms": {"ios": "10.0", "osx": "10.12"}, "swift_versions": ["5.3", "5.4", "5.5"], "versions": ["5.7.1", "5.7.0"]}
        ):
            with patch.object(
                client, "_get_podspec", new_callable=AsyncMock, return_value={"name": "Alamofire", "version": "5.7.1", "description": "Elegant HTTP Networking in Swift", "homepage": "https://github.com/Alamofire/Alamofire", "source": {"git": "https://github.com/Alamofire/Alamofire.git", "tag": "5.7.1"}, "license": "MIT", "authors": {"Alamofire Software Foundation": ""}, "platforms": {"ios": "10.0", "osx": "10.12"}, "swift_versions": ["5.3", "5.4", "5.5"]}
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
            client, "_get", new_callable=AsyncMock, return_value=sample_pod_data
        ) as mock_get:
            with patch.object(
                client, "_get_podspec", new_callable=AsyncMock, return_value={}
            ):
                await client.get_package_info_async("Alamofire")
        mock_get.assert_called()
        url = mock_get.call_args[0][0]
        assert "alamofire" in url.lower()

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=None
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

    @pytest.mark.asyncio
    async def test_package_exists_returns_true(self, client):
        session = client._get_session()
        with patch.object(session, "get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_get.return_value = mock_response
            assert await client.package_exists("Alamofire") is True
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_package_exists_returns_false(self, client):
        session = client._get_session()
        with patch.object(session, "get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_get.return_value = mock_response
            assert await client.package_exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_package_exists_handles_exception(self, client):
        session = client._get_session()
        with patch.object(session, "get", side_effect=Exception("Network error")):
            assert await client.package_exists("Alamofire") is False

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_pod_data):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=[sample_pod_data]
        ):
            results = await client.search_packages("Alamofire", limit=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_no_results(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=[]
        ):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_exception(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, side_effect=Exception("Error")
        ):
            results = await client.search_packages("Alamofire")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_pod_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"name": "Alamofire", "versions": ["5.7.1", "5.7.0"]},
        ):
            versions = await client.get_versions("Alamofire")
        assert len(versions) >= 1
        assert all("version" in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_empty_when_no_package(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=None
        ):
            versions = await client.get_versions("nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client, sample_pod_data):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=sample_pod_data
        ):
            with patch.object(
                client, "_get_podspec", new_callable=AsyncMock, return_value={"dependencies": {"UIKit": ["~> 1.0"]}}
            ):
                deps = await client.get_dependencies("Alamofire", "5.7.1")
        assert isinstance(deps, dict)

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_error(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            deps = await client.get_dependencies("nonexistent", "1.0")
        assert deps == {}
