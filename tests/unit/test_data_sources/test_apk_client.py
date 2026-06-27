from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.apk_client import APKClient


class TestAPKClient:
    @pytest.fixture
    def client(self):
        return APKClient()

    @pytest.fixture
    def sample_package_data(self):
        return {
            "name": "nginx",
            "version": "1.24.0-r0",
            "description": "small, powerful, scalable web/proxy server",
            "url": "https://nginx.org",
            "license": "BSD-2-Clause",
            "architecture": "x86_64",
            "origin": "nginx",
            "maintainer": "Natanael Copa",
            "build_time": 1680000000,
            "size": 0,
            "installed_size": 0,
            "depends": "libc.musl-x86_64.so.1,libssl3>=3.0.0",
            "provides": "nginx=1.24.0-r0",
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_package_data):
        with patch.object(
            client,
            "_get_apkindex",
            new_callable=AsyncMock,
            return_value={"nginx": sample_package_data},
        ):
            result = await client.get_package_info_async("nginx")
        assert result is not None
        assert result["name"] == "nginx"

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
        assert result["name"] == "nginx"

    def test_package_exists_returns_true(self, client, sample_package_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_package_data.__class__({"pkg": {"name": "nginx"}}),
        ):
            assert client.package_exists("nginx") is True

    def test_package_exists_returns_false(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            assert client.package_exists("nonexistent") is False

    def test_package_exists_handles_exception(self, client):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            side_effect=Exception("Error"),
        ):
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
    async def test_search_packages_returns_empty_on_exception(self, client):
        with patch.object(
            client, "_get_apkindex", new_callable=AsyncMock, side_effect=Exception("Error")
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
    async def test_get_dependencies_success(self, client, sample_package_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            deps = await client.get_dependencies("nginx", "1.24.0-r0")
        assert isinstance(deps, dict)

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_error(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            deps = await client.get_dependencies("nonexistent", "1.0")
        assert deps == {}
