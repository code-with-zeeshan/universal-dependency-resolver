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

    @pytest.mark.asyncio
    async def test_package_exists_returns_true(self, client):
        session = client._get_session()
        with patch.object(session, "head", new_callable=AsyncMock) as mock_head:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_head.return_value = mock_response
            assert await client.package_exists("laravel/laravel") is True
            mock_head.assert_called_once()

    @pytest.mark.asyncio
    async def test_package_exists_returns_false(self, client):
        session = client._get_session()
        with patch.object(session, "head", new_callable=AsyncMock) as mock_head:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_head.return_value = mock_response
            assert await client.package_exists("nonexistent/pkg") is False

    @pytest.mark.asyncio
    async def test_package_exists_handles_exception(self, client):
        session = client._get_session()
        with patch.object(session, "head", side_effect=Exception("Network error")):
            assert await client.package_exists("laravel/laravel") is False

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


class TestPackagistClientCoverage:
    """Targeted tests to push coverage from 60% to 80%."""

    @pytest.fixture
    def client(self):
        return PackagistClient()

    @pytest.mark.asyncio
    async def test_search_packages_with_package_type(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={"results": []}) as mock_get:
            results = await client.search_packages("laravel", package_type="library")
        assert results == []
        params = mock_get.call_args[1]["params"]
        assert params["type"] == "library"

    @pytest.mark.asyncio
    async def test_search_packages_no_results_key(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={}):
            results = await client.search_packages("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_data_is_none(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            results = await client.search_packages("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_package_version_not_found(self, client):
        info = {
            "package": {
                "name": "vendor/pkg",
                "versions": {"1.0.0": {"version": "1.0.0"}},
            }
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=info):
            with patch.object(client, "_get_download_stats", new_callable=AsyncMock, return_value={"daily": 0, "monthly": 0, "total": 0}):
                result = await client.get_package_version("vendor/pkg", "2.0.0")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_versions_skips_dev_versions(self, client):
        info = {
            "package": {
                "name": "vendor/pkg",
                "versions": {
                    "1.0.0-dev": {"version": "1.0.0-dev"},
                    "1.0.0": {"version": "1.0.0"},
                },
            }
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=info):
            with patch.object(client, "_get_download_stats", new_callable=AsyncMock, return_value={"daily": 0, "monthly": 0, "total": 0}):
                result = await client.get_versions("vendor/pkg", include_dev=False)
        assert len(result) == 1
        assert result[0]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_dependencies_without_version(self, client):
        info = {
            "package": {
                "name": "vendor/pkg",
                "versions": {
                    "1.0.0": {
                        "version": "1.0.0",
                        "require": {"php": ">=8.0"},
                    }
                },
            }
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=info):
            with patch.object(client, "_get_download_stats", new_callable=AsyncMock, return_value={"daily": 0, "monthly": 0, "total": 0}):
                result = await client.get_dependencies("vendor/pkg")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_dependencies_exclude_dev(self, client):
        info = {
            "package": {
                "name": "vendor/pkg",
                "versions": {
                    "1.0.0": {
                        "version": "1.0.0",
                        "require": {"php": ">=8.0"},
                        "require-dev": {"phpunit/phpunit": "^9.0"},
                    }
                },
            }
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=info):
            with patch.object(client, "_get_download_stats", new_callable=AsyncMock, return_value={"daily": 0, "monthly": 0, "total": 0}):
                result = await client.get_dependencies("vendor/pkg", "1.0.0", include_dev=False)
        assert "require-dev" not in result

    @pytest.mark.asyncio
    async def test_get_download_stats_success(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={"package": {"daily": 100, "monthly": 3000, "total": 90000}}):
            result = await client._get_download_stats("vendor/pkg")
        assert result["daily"] == 100
        assert result["total"] == 90000

    @pytest.mark.asyncio
    async def test_get_download_stats_no_package_key(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={}):
            result = await client._get_download_stats("vendor/pkg")
        assert result == {"daily": 0, "monthly": 0, "total": 0}

    @pytest.mark.asyncio
    async def test_get_download_stats_exception(self, client):
        with patch.object(client, "_get", side_effect=Exception("error")):
            result = await client._get_download_stats("vendor/pkg")
        assert result == {"daily": 0, "monthly": 0, "total": 0}

    def test_extract_system_requirements_full(self, client):
        version_data = {
            "require": {
                "php": ">=8.1",
                "ext-json": "*",
                "ext-mbstring": "*",
                "lib-openssl": ">=1.1",
                "lib-pcre": "*",
                "composer": "^2.0",
            }
        }
        result = client._extract_system_requirements(version_data)
        assert result["php"] == ">=8.1"
        assert {"name": "json", "version": "*"} in result["extensions"]
        assert {"name": "mbstring", "version": "*"} in result["extensions"]
        assert result["platform"]["lib-openssl"] == ">=1.1"
        assert result["composer"] == "^2.0"

    def test_extract_dependencies(self, client):
        version_data = {
            "require": {"php": ">=8.0"},
            "require-dev": {"phpunit/phpunit": "^9.0"},
            "conflict": {"bad/pkg": "1.0"},
            "replace": {"old/pkg": "1.0"},
            "provide": {"virt/pkg": "1.0"},
            "suggest": {"opt/pkg": "1.0"},
        }
        result = client._extract_dependencies(version_data)
        assert "require" in result
        assert "require-dev" in result
        assert "conflict" in result
        assert "replace" in result
        assert "provide" in result
        assert "suggest" in result

    def test_is_valid_version_empty(self, client):
        assert client._is_valid_version("") is False

    def test_is_valid_version_dev_prefix(self, client):
        assert client._is_valid_version("dev-master") is False

    def test_is_dev_version_various(self, client):
        assert client._is_dev_version("dev-master") is True
        assert client._is_dev_version("1.0.0-dev") is True
        assert client._is_dev_version("1.0.0") is False

    def test_is_newer_version_valid(self, client):
        assert client._is_newer_version("2.0.0", "1.0.0") is True
        assert client._is_newer_version("1.0.0", "2.0.0") is False

    def test_is_newer_version_with_invalid(self, client):
        assert client._is_newer_version("invalid", "1.0.0") is False
        assert client._is_newer_version("1.0.0", "invalid") is False

    def test_parse_composer_version_requirement_caret(self, client):
        req = client._parse_composer_version_requirement("^1.2.3")
        assert req.operator == "^"
        assert req.major == 1
        assert req.minor == 2
        assert req.patch == 3

    def test_parse_composer_version_requirement_tilde(self, client):
        req = client._parse_composer_version_requirement("~4.5.6")
        assert req.operator == "~"
        assert req.major == 4
        assert req.minor == 5
        assert req.patch == 6

    def test_parse_composer_version_requirement_gte(self, client):
        req = client._parse_composer_version_requirement(">=7.8.9")
        assert req.operator == ">="
        assert req.major == 7
        assert req.minor == 8
        assert req.patch == 9

    def test_parse_composer_version_requirement_exact(self, client):
        req = client._parse_composer_version_requirement("10.11.12")
        assert req.operator is None
        assert req.major == 10
        assert req.minor == 11
        assert req.patch == 12

    def test_parse_composer_version_requirement_cached(self, client):
        client._version_cache["^1.0.0"] = "cached"
        req = client._parse_composer_version_requirement("^1.0.0")
        assert req == "cached"

    def test_check_php_compatibility_caret(self, client):
        assert client._check_php_compatibility("7.4.0", "^7.4.0") is True
        assert client._check_php_compatibility("8.0.0", "^7.4.0") is False

    def test_check_php_compatibility_tilde(self, client):
        assert client._check_php_compatibility("7.4.5", "~7.4.0") is True
        assert client._check_php_compatibility("7.5.0", "~7.4.0") is False

    def test_check_php_compatibility_gte(self, client):
        assert client._check_php_compatibility("8.1.0", ">=8.1.0") is True
        assert client._check_php_compatibility("8.0.0", ">=8.1.0") is False

    def test_check_php_compatibility_exact(self, client):
        assert client._check_php_compatibility("7.4.0", "7.4.0") is True
        assert client._check_php_compatibility("7.4.1", "7.4.0") is False

    def test_check_php_compatibility_unparseable_system_version(self, client):
        assert client._check_php_compatibility("invalid", "^7.4.0") is True

    def test_check_composer_compatibility(self, client):
        assert client._check_composer_compatibility("2.0.0", "^2.0.0") is True

    @pytest.mark.asyncio
    async def test_check_compatibility_package_not_found(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value=None):
            result = await client.check_compatibility("nonexistent/pkg", "1.0.0", {})
        assert result["compatible"] is False
        assert "not found" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_check_compatibility_php_mismatch(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "system_requirements": {"php": ">=8.1.0", "extensions": [], "platform": {}, "composer": None},
        }):
            result = await client.check_compatibility("vendor/pkg", "1.0.0", {"php_version": "7.4.0"})
        assert result["compatible"] is False
        assert any("PHP" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_check_compatibility_missing_extension(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "system_requirements": {"php": None, "extensions": [{"name": "json", "version": "*"}], "platform": {}, "composer": None},
        }):
            result = await client.check_compatibility("vendor/pkg", "1.0.0", {"php_extensions": []})
        assert result["compatible"] is False
        assert any("extension" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_check_compatibility_composer_warning(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "system_requirements": {"php": None, "extensions": [], "platform": {}, "composer": "^2.5.0"},
        }):
            result = await client.check_compatibility("vendor/pkg", "1.0.0", {"composer_version": "2.0.0"})
        assert any("Composer" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_check_compatibility_abandoned_with_replacement(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "system_requirements": {"php": None, "extensions": [], "platform": {}, "composer": None},
            "abandoned": True,
            "replacement": "new-vendor/new-pkg",
        }):
            result = await client.check_compatibility("vendor/pkg", "1.0.0", {})
        assert any("Consider using" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_check_compatibility_abandoned_without_replacement(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value={
            "system_requirements": {"php": None, "extensions": [], "platform": {}, "composer": None},
            "abandoned": True,
        }):
            result = await client.check_compatibility("vendor/pkg", "1.0.0", {})
        assert any("abandoned" in w for w in result["warnings"])

    def test_check_php_compatibility_caret_min_or_max_none(self, client):
        with patch("backend.data_sources.packagist_client.parse_version") as mock_pv:
            mock_pv.side_effect = [object(), None, None]
            assert client._check_php_compatibility("7.4.0", "^7.4.0") is True

    def test_check_php_compatibility_tilde_min_or_max_none(self, client):
        with patch("backend.data_sources.packagist_client.parse_version") as mock_pv:
            mock_pv.side_effect = [object(), None, None]
            assert client._check_php_compatibility("7.4.5", "~7.4.0") is True

    def test_check_php_compatibility_gte_min_v_none(self, client):
        with patch("backend.data_sources.packagist_client.parse_version") as mock_pv:
            mock_pv.side_effect = [object(), None]
            assert client._check_php_compatibility("8.0.0", ">=8.1.0") is True

    def test_check_php_compatibility_exact_exact_v_none(self, client):
        with patch("backend.data_sources.packagist_client.parse_version") as mock_pv:
            mock_pv.side_effect = [object(), None]
            assert client._check_php_compatibility("7.4.0", "7.4.0") is True


