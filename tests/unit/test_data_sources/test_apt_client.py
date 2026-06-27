from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.apt_client import APTClient


class TestAPTClient:
    @pytest.fixture
    def client(self):
        return APTClient()

    @pytest.fixture
    def sample_package_data(self):
        return {
            "package": "nginx",
            "version": "1.24.0-1",
            "description": "small, powerful, scalable web/proxy server",
            "maintainer": "Debian Nginx Maintainers",
            "architecture": "amd64",
            "depends": "libc6 >= 2.34, libssl3 >= 3.0, zlib1g >= 1:1.1.4",
            "homepage": "https://nginx.org",
            "section": "httpd",
            "priority": "optional",
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_package_data):
        with patch.object(
            client,
            "_get_packages_list",
            new_callable=AsyncMock,
            return_value={"nginx": sample_package_data},
        ):
            result = await client.get_package_info_async("nginx")
        assert result is not None
        assert result["name"] == "nginx"
        assert result["version"] == "1.24.0-1"

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(
        self, client, sample_package_data
    ):
        with patch.object(
            client,
            "_get_packages_list",
            new_callable=AsyncMock,
            return_value={"nginx": sample_package_data},
        ) as mock_get:
            await client.get_package_info_async("nginx")
        mock_get.assert_called()

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(
            client, "_get_packages_list", new_callable=AsyncMock, return_value={}
        ):
            result = await client.get_package_info_async("nonexistent")
        assert result is None

    def test_get_package_info_sync_success(self, client):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value={"name": "nginx", "version": "1.24.0-1"},
        ):
            result = client.get_package_info("nginx")
        assert result is not None
        assert result["name"] == "nginx"

    def test_get_package_info_sync_not_found(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            result = client.get_package_info("nonexistent")
        assert result is None

    def test_package_exists_returns_true(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value={"name": "nginx"}
        ):
            assert client.package_exists("nginx") is True

    def test_package_exists_returns_false(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            assert client.package_exists("nonexistent") is False

    def test_package_exists_handles_exception(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, side_effect=Exception("apt error")
        ):
            assert client.package_exists("nginx") is False

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_package_data):
        with patch.object(
            client,
            "_get_packages_list",
            new_callable=AsyncMock,
            return_value={"nginx": sample_package_data},
        ):
            results = await client.search_packages("nginx", limit=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_packages_returns_empty_on_failure(self, client):
        with patch.object(
            client, "_get_packages_list", new_callable=AsyncMock, return_value={}
        ):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_returns_empty_on_exception(self, client):
        with patch.object(
            client, "_get_packages_list", new_callable=AsyncMock, side_effect=Exception("Error")
        ):
            results = await client.search_packages("nginx")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_package_data):
        with patch.object(
            client,
            "_get_packages_list",
            new_callable=AsyncMock,
            return_value={"nginx": sample_package_data},
        ):
            versions = await client.get_versions("nginx")
        assert len(versions) >= 1
        assert all("version" in v for v in versions)

    @pytest.mark.asyncio
    async def test_get_versions_empty_when_no_package(self, client):
        with patch.object(
            client, "_get_packages_list", new_callable=AsyncMock, return_value={}
        ):
            versions = await client.get_versions("nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client, sample_package_data):
        with patch.object(
            client, "_get_packages_list", new_callable=AsyncMock, return_value={"nginx": sample_package_data}
        ):
            deps = await client.get_dependencies("nginx", "1.24.0-1")
        assert "depends" in deps

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_error(self, client):
        with patch.object(
            client, "_get_packages_list", new_callable=AsyncMock, return_value={}
        ):
            deps = await client.get_dependencies("nonexistent", "1.0")
        assert deps == {}
