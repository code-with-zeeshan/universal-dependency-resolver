from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.conda_client import CondaClient


class TestCondaClient:
    @pytest.fixture
    def client(self):
        return CondaClient()

    @pytest.fixture
    def sample_package_data(self):
        return {
            "name": "numpy",
            "version": "1.24.3",
            "summary": "NumPy is the fundamental package for array computing with Python.",
            "license": "BSD-3-Clause",
            "home_page": "https://numpy.org",
            "dev_url": "https://github.com/numpy/numpy",
            "doc_url": "https://numpy.org/doc",
            "versions": ["1.24.3", "1.24.2", "1.24.1"],
            "files": [
                {
                    "filename": "numpy-1.24.3-py311_0.tar.bz2",
                    "size": 15000000,
                    "upload_time": "2023-04-01",
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_package_data):
        with patch.object(
            client,
            "cached_get",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            result = await client.get_package_info_async("numpy")
        assert result is not None
        assert result["name"] == "numpy"
        assert result["version"] == "1.24.3"

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(
        self, client, sample_package_data
    ):
        with patch.object(
            client,
            "cached_get",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ) as mock_get:
            await client.get_package_info_async("numpy")
        mock_get.assert_called_once()
        cache_key, url = mock_get.call_args[0]
        assert "numpy" in cache_key
        assert "/package/numpy" in url

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=None
        ):
            result = await client.get_package_info_async("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_async_handles_bad_data(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value={"invalid": True}
        ):
            result = await client.get_package_info_async("bad-pkg")
        assert result is not None
        assert result.get("name") is None

    def test_get_package_info_sync_success(self, client, sample_package_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            result = client.get_package_info("numpy")
        assert result is not None
        assert result["name"] == "numpy"

    def test_package_exists_returns_true(self, client):
        with patch("requests.head") as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_head.return_value = mock_response
            assert client.package_exists("numpy") is True

    def test_package_exists_returns_false(self, client):
        with patch("requests.head") as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_head.return_value = mock_response
            assert client.package_exists("nonexistent") is False

    def test_package_exists_handles_exception(self, client):
        with patch("requests.head", side_effect=Exception("Network error")):
            assert client.package_exists("numpy") is False

    @pytest.mark.asyncio
    async def test_search_success(self, client, sample_package_data):
        with patch.object(
            client,
            "cached_get",
            new_callable=AsyncMock,
            return_value=[sample_package_data],
        ):
            results = await client.search("numpy")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_failure(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=[]
        ):
            results = await client.search("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_exception(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, side_effect=Exception("Error")
        ):
            results = await client.search("numpy")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_package_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            versions = await client.get_versions("numpy")
        assert len(versions) == 3
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
        mock_deps = {"depends": ["python >=3.8", "libblas >=3.0"], "build": ["cmake"]}
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=mock_deps
        ):
            deps = await client.get_dependencies("numpy", "1.24.3")
        assert "depends" in deps

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_error(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=None
        ):
            deps = await client.get_dependencies("nonexistent", "1.0.0")
        assert deps == {}
