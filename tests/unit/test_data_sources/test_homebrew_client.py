from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_sources.homebrew_client import HomebrewClient
from backend.data_sources.homebrew_client import PackageType


class TestHomebrewClient:
    @pytest.fixture
    def client(self):
        return HomebrewClient()

    @pytest.fixture
    def sample_formula_data(self):
        return {
            "name": "curl",
            "full_name": "curl",
            "versions": {"stable": "8.4.0", "head": "HEAD"},
            "urls": {"stable": {"url": "https://curl.se/download/curl-8.4.0.tar.bz2"}},
            "revision": 0,
            "version_scheme": 0,
            "bottle": {
                "stable": {"rebuild": 0, "files": {"arm64_ventura": {"url": "..."}}}
            },
            "desc": "Get a file from an HTTP, HTTPS or FTP server",
            "license": "curl",
            "homepage": "https://curl.se",
            "dependencies": ["openssl", "zlib"],
            "build_dependencies": ["autoconf", "automake"],
        }

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_formula_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value=sample_formula_data,
        ):
            result = await client.get_package_info_async("curl", PackageType.FORMULA)
        assert result is not None
        assert result["name"] == "curl"

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(
        self, client, sample_formula_data
    ):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value=sample_formula_data,
        ) as mock_get:
            await client.get_package_info_async("curl", PackageType.FORMULA)
        mock_get.assert_called_once()
        url = mock_get.call_args[0][0]
        assert "curl" in url

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=None
        ):
            result = await client.get_package_info_async(
                "nonexistent", PackageType.FORMULA
            )
        assert result is None

    def test_get_package_info_sync_success(self, client, sample_formula_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_formula_data,
        ):
            result = client.get_package_info("curl", PackageType.FORMULA)
        assert result is not None
        assert result["name"] == "curl"

    def test_package_exists_returns_true(self, client):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value={"name": "curl"},
        ):
            assert client.package_exists("curl", PackageType.FORMULA) is True

    def test_package_exists_returns_false(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            assert client.package_exists("nonexistent", PackageType.FORMULA) is False

    def test_package_exists_handles_exception(self, client):
        with patch("requests.head", side_effect=Exception("Error")):
            assert client.package_exists("curl", PackageType.FORMULA) is False

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_formula_data):
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value=[sample_formula_data],
        ):
            results = await client.search_packages("curl", limit=10)
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
            results = await client.search_packages("curl")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client, sample_formula_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_formula_data,
        ):
            deps = await client.get_dependencies("curl", PackageType.FORMULA)
        assert "runtime" in deps
        assert "openssl" in deps["runtime"]

    @pytest.mark.asyncio
    async def test_get_dependencies_empty_on_error(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            deps = await client.get_dependencies("nonexistent", PackageType.FORMULA)
        assert deps == {}

    @pytest.mark.asyncio
    async def test_check_compatibility_returns_result(
        self, client, sample_formula_data
    ):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_formula_data,
        ):
            result = await client.check_compatibility("curl", PackageType.FORMULA, {})
        assert isinstance(result, dict)
