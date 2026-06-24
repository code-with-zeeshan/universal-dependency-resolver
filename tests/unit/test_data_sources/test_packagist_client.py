from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.packagist_client import PackagistClient


class TestPackagistClient:
    @pytest.fixture
    def client(self):
        return PackagistClient()

    @pytest.fixture
    def sample_package_data(self):
        return {
            "name": "laravel/laravel",
            "description": "The Laravel Framework",
            "type": "project",
            "repository": "https://github.com/laravel/laravel",
            "downloads": {"total": 100000000, "monthly": 5000000, "daily": 150000},
            "favers": 50000,
            "versions": {
                "11.0.0": {
                    "version": "11.0.0",
                    "require": {"php": ">=8.1"},
                    "require-dev": {"mockery/mockery": "^1.6"},
                }
            },
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_package_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"package": sample_package_data},
        ):
            with patch.object(client, "_get_download_stats", new_callable=AsyncMock, return_value={"daily": 0, "monthly": 0, "total": 0}):
                result = await client.get_package_info_async("laravel/laravel")
        assert result is not None
        assert result["name"] == "laravel/laravel"

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(
        self, client, sample_package_data
    ):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"package": sample_package_data},
        ) as mock_get:
            with patch.object(client, "_get_download_stats", new_callable=AsyncMock, return_value={"daily": 0, "monthly": 0, "total": 0}):
                await client.get_package_info_async("laravel/laravel")
        mock_get.assert_called()
        url = mock_get.call_args[0][0]
        assert "laravel" in url

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=None
        ):
            result = await client.get_package_info_async("nonexistent/pkg")
        assert result is None

    def test_get_package_info_sync_success(self, client, sample_package_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_package_data,
        ):
            result = client.get_package_info("laravel/laravel")
        assert result is not None

    def test_package_exists_returns_true(self, client):
        with patch("requests.head") as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_head.return_value = mock_response
            assert client.package_exists("laravel/laravel") is True

    def test_package_exists_returns_false(self, client):
        with patch("requests.head") as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_head.return_value = mock_response
            assert client.package_exists("nonexistent/pkg") is False

    def test_package_exists_handles_exception(self, client):
        with patch("requests.head", side_effect=Exception("Network error")):
            assert client.package_exists("laravel/laravel") is False

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_package_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"results": [sample_package_data]},
        ) as mock_get:
            results = await client.search_packages("laravel", limit=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_packages_calls_correct_url(self, client, sample_package_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"results": [sample_package_data]},
        ) as mock_get:
            await client.search_packages("laravel", limit=5)
        url = mock_get.call_args[0][0]
        assert "/search.json" in url
        kwargs = mock_get.call_args[1]
        params = kwargs.get("params", {})
        assert params.get("q") == "laravel"

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_no_results(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value={"results": []}
        ):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_with_tags_filter(self, client, sample_package_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"results": [sample_package_data]},
        ) as mock_get:
            results = await client.search_packages("laravel", tags=["framework"])
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_package_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"package": sample_package_data},
        ):
            with patch.object(
                client,
                "_get_download_stats",
                new_callable=AsyncMock,
                return_value={"daily": 0, "monthly": 0, "total": 0},
            ):
                result = await client.get_versions("laravel/laravel")
        assert len(result) >= 1
        assert all("version" in v for v in result)

    @pytest.mark.asyncio
    async def test_get_versions_empty_on_no_package(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            versions = await client.get_versions("nonexistent/pkg")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_version_success(self, client, sample_package_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"package": sample_package_data},
        ):
            with patch.object(
                client,
                "_get_download_stats",
                new_callable=AsyncMock,
                return_value={"daily": 0, "monthly": 0, "total": 0},
            ):
                result = await client.get_package_version("laravel/laravel", "11.0.0")
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={
                "package": {"versions": {"1.0": {"require": {"php": ">=8.0"}}}}
            },
        ):
            deps = await client.get_dependencies("vendor/pkg", "1.0")
        assert isinstance(deps, dict)

    @pytest.mark.asyncio
    async def test_get_dependencies_empty_on_error(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            deps = await client.get_dependencies("nonexistent/pkg", "1.0")
        assert deps == {}

    @pytest.mark.asyncio
    async def test_check_compatibility_returns_result(self, client):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={
                "package": {"versions": {"1.0": {"require": {"php": ">=8.0"}}}}
            },
        ):
            result = await client.check_compatibility(
                "vendor/pkg", "1.0", {"php": "8.2.0"}
            )
        assert isinstance(result, dict)
