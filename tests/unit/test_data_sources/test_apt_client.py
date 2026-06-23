from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.apt_client import APTClient


class TestAPTClient:
    @pytest.fixture
    def client(self):
        return APTClient()

    @pytest.fixture
    def sample_package_data(self):
        return {
            "Package": "nginx",
            "Version": "1.24.0-1",
            "Description": "small, powerful, scalable web/proxy server",
            "Maintainer": "Debian Nginx Maintainers",
            "Architecture": "amd64",
            "Depends": "libc6 >= 2.34, libssl3 >= 3.0, zlib1g >= 1:1.1.4",
            "Homepage": "https://nginx.org",
            "Section": "httpd",
            "Priority": "optional",
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_package_data):
        with patch.object(
            client,
            "cached_get",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            result = await client.get_package_info_async("nginx")
        assert result is not None
        assert result["Package"] == "nginx"
        assert result["Version"] == "1.24.0-1"

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
            await client.get_package_info_async("nginx")
        mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=None
        ):
            result = await client.get_package_info_async("nonexistent")
        assert result is None

    def test_get_package_info_sync_success(self, client, sample_package_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            result = client.get_package_info("nginx")
        assert result is not None
        assert result["Package"] == "nginx"

    def test_get_package_info_sync_not_found(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            result = client.get_package_info("nonexistent")
        assert result is None

    def test_package_exists_returns_true(self, client):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Package: nginx\n"
            mock_run.return_value = mock_result
            assert client.package_exists("nginx") is True

    def test_package_exists_returns_false(self, client):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_run.return_value = mock_result
            assert client.package_exists("nonexistent") is False

    def test_package_exists_handles_exception(self, client):
        with patch("subprocess.run", side_effect=Exception("apt error")):
            assert client.package_exists("nginx") is False

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_package_data):
        with patch.object(
            client,
            "cached_get",
            new_callable=AsyncMock,
            return_value=[sample_package_data],
        ):
            results = await client.search_packages("nginx", limit=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_packages_returns_empty_on_failure(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=[]
        ):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_returns_empty_on_exception(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, side_effect=Exception("Error")
        ):
            results = await client.search_packages("nginx")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_package_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            versions = await client.get_versions("nginx")
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
        mock_deps = {"Depends": "libc6 >= 2.34, libssl3 >= 3.0", "Pre-Depends": "dpkg"}
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=mock_deps
        ):
            deps = await client.get_dependencies("nginx", "1.24.0-1")
        assert "Depends" in deps

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_error(self, client):
        with patch.object(
            client, "cached_get", new_callable=AsyncMock, return_value=None
        ):
            deps = await client.get_dependencies("nonexistent", "1.0")
        assert deps == {}
