from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.rubygems_client import RubyGemsClient


class TestRubyGemsClient:
    @pytest.fixture
    def client(self):
        return RubyGemsClient()

    @pytest.fixture
    def sample_gem_data(self):
        return {
            "name": "rails",
            "version": "7.1.2",
            "info": "Ruby on Rails is a full-stack web framework",
            "homepage_uri": "https://rubyonrails.org",
            "source_code_uri": "https://github.com/rails/rails",
            "documentation_uri": "https://guides.rubyonrails.org",
            "licenses": ["MIT"],
            "authors": "David Heinemeier Hansson",
            "gem_uri": "https://rubygems.org/gems/rails-7.1.2.gem",
            "downloads": 50000000,
            "version_downloads": 1000000,
            "platform": "ruby",
        }

    @pytest.fixture
    def sample_versions_data(self):
        return [
            {
                "number": "7.1.2",
                "created_at": "2023-11-10",
                "downloads": 100000,
                "platform": "ruby",
                "licenses": ["MIT"],
                "ruby_version": ">=2.7",
            },
            {
                "number": "7.1.1",
                "created_at": "2023-10-15",
                "downloads": 50000,
                "platform": "ruby",
                "licenses": ["MIT"],
                "ruby_version": ">=2.7",
            },
        ]

    @pytest.mark.asyncio
    async def test_get_package_info_async_success(self, client, sample_gem_data):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=sample_gem_data):
            with patch.object(client, "_get_all_versions", new_callable=AsyncMock, return_value=[]):
                with patch.object(
                    client, "_get_reverse_dependencies", new_callable=AsyncMock, return_value=[]
                ):
                    with patch.object(
                        client,
                        "_get_download_stats",
                        new_callable=AsyncMock,
                        return_value={"total": 0, "version": 0},
                    ):
                        with patch.object(
                            client, "_get_dependencies", new_callable=AsyncMock, return_value={}
                        ):
                            result = await client.get_package_info_async("rails")
        assert result is not None
        assert result["name"] == "rails"
        assert result["version"] == "7.1.2"

    @pytest.mark.asyncio
    async def test_get_package_info_async_calls_correct_url(self, client, sample_gem_data):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=sample_gem_data
        ) as mock_get:
            with patch.object(client, "_get_all_versions", new_callable=AsyncMock, return_value=[]):
                with patch.object(
                    client, "_get_reverse_dependencies", new_callable=AsyncMock, return_value=[]
                ):
                    with patch.object(
                        client,
                        "_get_download_stats",
                        new_callable=AsyncMock,
                        return_value={"total": 0, "version": 0},
                    ):
                        with patch.object(
                            client, "_get_dependencies", new_callable=AsyncMock, return_value={}
                        ):
                            await client.get_package_info_async("rails")
        mock_get.assert_called_once()
        url = mock_get.call_args[0][0]
        assert "rails" in url

    @pytest.mark.asyncio
    async def test_get_package_info_async_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info_async("nonexistent")
        assert result is None

    def test_get_package_info_sync_success(self, client, sample_gem_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_gem_data,
        ):
            result = client.get_package_info("rails")
        assert result is not None
        assert result["name"] == "rails"

    @pytest.mark.asyncio
    async def test_package_exists_returns_true(self, client):
        session = client._get_session()
        with patch.object(session, "head", new_callable=AsyncMock) as mock_head:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_head.return_value = mock_response
            assert await client.package_exists("rails") is True
            mock_head.assert_called_once()

    @pytest.mark.asyncio
    async def test_package_exists_returns_false(self, client):
        session = client._get_session()
        with patch.object(session, "head", new_callable=AsyncMock) as mock_head:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_head.return_value = mock_response
            assert await client.package_exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_package_exists_handles_exception(self, client):
        session = client._get_session()
        with patch.object(session, "head", side_effect=Exception("Network error")):
            assert await client.package_exists("rails") is False

    @pytest.mark.asyncio
    async def test_search_packages_success(self, client, sample_gem_data):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=[sample_gem_data]):
            results = await client.search_packages("rails", limit=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_packages_calls_correct_url(self, client, sample_gem_data):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=[sample_gem_data]
        ) as mock_get:
            await client.search_packages("rails", limit=5)
        _args, kwargs = mock_get.call_args
        params = kwargs.get("params", {})
        assert params.get("query") == "rails"

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_no_results(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=[]):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("Error")):
            results = await client.search_packages("rails")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_versions_success(self, client, sample_versions_data):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=sample_versions_data
        ):
            versions = await client.get_versions("rails")
        assert len(versions) == 2
        assert versions[0]["version"] == "7.1.2"

    @pytest.mark.asyncio
    async def test_get_versions_empty_on_error(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            versions = await client.get_versions("nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_version_success(self, client, sample_versions_data):
        with (
            patch.object(client, "_get", new_callable=AsyncMock, return_value=sample_versions_data),
            patch.object(client, "_parse_dependencies", new_callable=AsyncMock, return_value={}),
        ):
            result = await client.get_package_version("rails", "7.1.2")
        assert result is not None
        assert result["version"] == "7.1.2"

    @pytest.mark.asyncio
    async def test_get_package_version_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=[]):
            result = await client.get_package_version("rails", "999.0.0")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client, sample_versions_data):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=sample_versions_data
        ):
            with patch.object(
                client,
                "_parse_dependencies",
                new_callable=AsyncMock,
                return_value={"runtime": {"activesupport": ">=7.1.0"}},
            ):
                deps = await client.get_dependencies("rails", "7.1.2")
        assert "runtime" in deps

    @pytest.mark.asyncio
    async def test_get_dependencies_empty_on_error(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            deps = await client.get_dependencies("nonexistent", "1.0")
        assert deps == {}

    @pytest.mark.asyncio
    async def test_check_compatibility_returns_result(self, client, sample_versions_data):
        with (
            patch.object(client, "_get", new_callable=AsyncMock, return_value=sample_versions_data),
            patch.object(client, "_parse_dependencies", new_callable=AsyncMock, return_value={}),
        ):
            result = await client.check_compatibility("rails", "7.1.2", {})
        assert isinstance(result, dict)

    # === New test: get_versions filters out prereleases when include_prereleases=False
    @pytest.mark.asyncio
    async def test_get_versions_excludes_prereleases(self, client):
        versions_with_prerelease = [
            {
                "number": "7.1.2",
                "prerelease": False,
                "yanked": False,
                "platform": "ruby",
                "created_at": "2023-11-10",
                "sha": None,
                "metadata": {},
                "downloads_count": 100000,
            },
            {
                "number": "7.2.0.beta1",
                "prerelease": True,
                "yanked": False,
                "platform": "ruby",
                "created_at": "2023-12-01",
                "sha": None,
                "metadata": {},
                "downloads_count": 5000,
            },
            {
                "number": "7.1.1",
                "prerelease": False,
                "yanked": False,
                "platform": "ruby",
                "created_at": "2023-10-15",
                "sha": None,
                "metadata": {},
                "downloads_count": 50000,
            },
        ]
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=versions_with_prerelease
        ):
            versions = await client.get_versions("rails", include_prereleases=False)
        assert len(versions) == 2
        assert all(v["prerelease"] is False for v in versions)

    # === New test: _get_all_versions wraps non-list response in list
    @pytest.mark.asyncio
    async def test_get_all_versions_wraps_non_list(self, client):
        single_version = {"number": "1.0.0", "prerelease": False}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=single_version):
            result = await client._get_all_versions("rails")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["number"] == "1.0.0"

    # === New test: _get_all_versions returns empty list on None
    @pytest.mark.asyncio
    async def test_get_all_versions_returns_empty_on_none(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client._get_all_versions("rails")
        assert result == []

    # === New test: _parse_dependencies handles runtime and development deps
    @pytest.mark.asyncio
    async def test_parse_dependencies_runtime_and_dev(self, client):
        deps_data = {
            "dependencies": [
                {"name": "activesupport", "requirements": ">=7.1.0", "type": "runtime"},
                {"name": "rack", "requirements": ">=2.2.4", "type": "runtime"},
                {"name": "rspec", "requirements": ">=3.0", "type": "development"},
            ]
        }
        result = await client._parse_dependencies(deps_data)
        assert "runtime" in result
        assert "development" in result
        assert result["runtime"]["activesupport"] == ">=7.1.0"
        assert result["runtime"]["rack"] == ">=2.2.4"
        assert result["development"]["rspec"] == ">=3.0"

    # === New test: _parse_dependencies returns empty dicts when no deps key
    @pytest.mark.asyncio
    async def test_parse_dependencies_empty_when_no_deps_key(self, client):
        result = await client._parse_dependencies({})
        assert result == {"runtime": {}, "development": {}}

    # === New test: _get_download_stats returns download counts
    @pytest.mark.asyncio
    async def test_get_download_stats_returns_counts(self, client):
        stats_data = {"total_downloads": 50000000, "version_downloads": 1000000}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=stats_data):
            result = await client._get_download_stats("rails")
        assert result["total"] == 50000000
        assert result["version"] == 1000000

    # === New test: _get_download_stats returns zeros on error
    @pytest.mark.asyncio
    async def test_get_download_stats_returns_zeros_on_error(self, client):
        with patch.object(
            client, "_get", new_callable=AsyncMock, side_effect=Exception("API error")
        ):
            result = await client._get_download_stats("rails")
        assert result == {"total": 0, "version": 0}

    # === New test: _get_download_stats returns zeros when data is None
    @pytest.mark.asyncio
    async def test_get_download_stats_returns_zeros_on_none(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client._get_download_stats("rails")
        assert result == {"total": 0, "version": 0}

    # === New test: _get_reverse_dependencies returns list
    @pytest.mark.asyncio
    async def test_get_reverse_dependencies_returns_list(self, client):
        reverse_deps = ["gem_a", "gem_b", "gem_c"]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=reverse_deps):
            result = await client._get_reverse_dependencies("rails")
        assert result == reverse_deps

    # === New test: _get_reverse_dependencies returns empty on non-list
    @pytest.mark.asyncio
    async def test_get_reverse_dependencies_returns_empty_on_non_list(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client._get_reverse_dependencies("rails")
        assert result == []

    # === New test: check_compatibility with ruby_version in system_info
    @pytest.mark.asyncio
    async def test_check_compatibility_with_ruby_version(self, client):
        versions_data = [
            {
                "number": "7.1.2",
                "prerelease": False,
                "yanked": False,
                "required_ruby_version": ">=3.0.0",
                "required_rubygems_version": None,
                "platform": "ruby",
            }
        ]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=versions_data):
            with patch.object(
                client, "_parse_dependencies", new_callable=AsyncMock, return_value={}
            ):
                result = await client.check_compatibility(
                    "rails", "7.1.2", {"ruby_version": "3.1.0"}
                )
        assert result["compatible"] is True

    # === New test: check_compatibility with rubygems_version in system_info
    @pytest.mark.asyncio
    async def test_check_compatibility_with_rubygems_version(self, client):
        versions_data = [
            {
                "number": "7.1.2",
                "prerelease": False,
                "yanked": False,
                "required_ruby_version": None,
                "required_rubygems_version": ">=3.2.0",
                "platform": "ruby",
            }
        ]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=versions_data):
            with patch.object(
                client, "_parse_dependencies", new_callable=AsyncMock, return_value={}
            ):
                result = await client.check_compatibility(
                    "rails", "7.1.2", {"rubygems_version": "3.4.0"}
                )
        assert result["compatible"] is True
        assert len(result["warnings"]) == 0

    # === Test: get_package_version returns None when version not found in list (line 189)
    @pytest.mark.asyncio
    async def test_get_package_version_returns_none_when_version_mismatch(
        self, client, sample_versions_data
    ):
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=sample_versions_data
        ):
            result = await client.get_package_version("rails", "0.0.0")
        assert result is None

    # === Test: get_versions excludes yanked versions (line 209)
    @pytest.mark.asyncio
    async def test_get_versions_excludes_yanked(self, client):
        versions_with_yanked = [
            {
                "number": "7.1.2",
                "prerelease": False,
                "yanked": False,
                "platform": "ruby",
                "created_at": "2023-11-10",
                "sha": None,
                "metadata": {},
                "downloads_count": 100000,
            },
            {
                "number": "7.1.0",
                "prerelease": False,
                "yanked": True,
                "platform": "ruby",
                "created_at": "2023-10-01",
                "sha": None,
                "metadata": {},
                "downloads_count": 50000,
            },
            {
                "number": "7.0.0",
                "prerelease": False,
                "yanked": False,
                "platform": "ruby",
                "created_at": "2023-09-01",
                "sha": None,
                "metadata": {},
                "downloads_count": 25000,
            },
        ]
        with patch.object(
            client, "_get", new_callable=AsyncMock, return_value=versions_with_yanked
        ):
            versions = await client.get_versions("rails", include_yanked=False)
        assert len(versions) == 2
        assert all(v["yanked"] is False for v in versions)

    # === Test: get_dependencies without version uses get_package_info_async (line 242)
    @pytest.mark.asyncio
    async def test_get_dependencies_without_version(self, client):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value={"dependencies": {"runtime": {"rack": ">=2.2"}}},
        ):
            deps = await client.get_dependencies("rails")
        assert deps == {"runtime": {"rack": ">=2.2"}}

    # === Test: _get_dependencies internal method finds matching version (lines 282-287)
    @pytest.mark.asyncio
    async def test_get_dependencies_internal_found(self, client):
        versions_data = [
            {
                "number": "7.1.2",
                "dependencies": {
                    "dependencies": [{"name": "rack", "requirements": ">=2.2", "type": "runtime"}]
                },
            }
        ]
        with patch.object(
            client, "_get_all_versions", new_callable=AsyncMock, return_value=versions_data
        ):
            result = await client._get_dependencies("rails", "7.1.2")
        assert "runtime" in result
        assert result["runtime"]["rack"] == ">=2.2"

    # === Test: _get_dependencies internal method returns {} when version not found (line 289)
    @pytest.mark.asyncio
    async def test_get_dependencies_internal_not_found(self, client):
        with patch.object(
            client, "_get_all_versions", new_callable=AsyncMock, return_value=[{"number": "7.1.2"}]
        ):
            result = await client._get_dependencies("rails", "0.0.0")
        assert result == {}

    # === Test: _process_versions skips entries with missing number (lines 312-314)
    def test_process_versions_skips_missing_number(self, client):
        versions_data = [
            {"created_at": "2023-11-10", "platform": "ruby"},
            {"number": "7.1.2", "created_at": "2023-11-10", "platform": "ruby"},
        ]
        result = client._process_versions(versions_data)
        assert len(result) == 1
        assert result[0]["version"] == "7.1.2"

    # === Test: _process_versions skips unparseable versions (lines 312-314)
    def test_process_versions_skips_invalid_version(self, client):
        versions_data = [
            {"number": "not-a-valid-version", "created_at": "2023-11-10", "platform": "ruby"},
            {"number": "7.1.2", "created_at": "2023-11-10", "platform": "ruby"},
        ]
        result = client._process_versions(versions_data)
        assert len(result) == 1
        assert result[0]["version"] == "7.1.2"

    # === Test: _extract_system_requirements reads ruby/rubygems from metadata (lines 345, 347)
    def test_extract_system_requirements_with_metadata(self, client):
        data = {
            "platform": "ruby",
            "licenses": ["MIT"],
            "metadata": {
                "required_ruby_version": ">=3.0.0",
                "required_rubygems_version": ">=3.2.0",
            },
        }
        result = client._extract_system_requirements(data)
        assert result["ruby"] == ">=3.0.0"
        assert result["rubygems"] == ">=3.2.0"

    # === Test: _parse_ruby_version_requirement uses cache (line 353)
    def test_parse_ruby_version_requirement_cache(self, client):
        result1 = client._parse_ruby_version_requirement("~> 3.0.0")
        result2 = client._parse_ruby_version_requirement("~> 3.0.0")
        assert result1 is result2

    # === Test: check_compatibility when package version not found (line 394)
    @pytest.mark.asyncio
    async def test_check_compatibility_package_not_found(self, client):
        with patch.object(client, "get_package_version", new_callable=AsyncMock, return_value=None):
            result = await client.check_compatibility("rails", "7.1.2", {})
        assert result["compatible"] is False
        assert "Package version not found" in result["errors"]

    # === Test: check_compatibility with incompatible ruby_version (line 408)
    @pytest.mark.asyncio
    async def test_check_compatibility_ruby_incompatible_error(self, client):
        versions_data = [
            {
                "number": "7.1.2",
                "prerelease": False,
                "yanked": False,
                "required_ruby_version": ">=3.0.0",
                "required_rubygems_version": None,
                "platform": "ruby",
            }
        ]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=versions_data):
            with patch.object(
                client, "_parse_dependencies", new_callable=AsyncMock, return_value={}
            ):
                result = await client.check_compatibility(
                    "rails", "7.1.2", {"ruby_version": "2.7.0"}
                )
        assert result["compatible"] is False
        assert any("Requires Ruby" in e for e in result["errors"])

    # === Test: check_compatibility with incompatible rubygems_version (line 417)
    @pytest.mark.asyncio
    async def test_check_compatibility_rubygems_incompatible_warning(self, client):
        versions_data = [
            {
                "number": "7.1.2",
                "prerelease": False,
                "yanked": False,
                "required_ruby_version": None,
                "required_rubygems_version": ">=3.2.0",
                "platform": "ruby",
            }
        ]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=versions_data):
            with patch.object(
                client, "_parse_dependencies", new_callable=AsyncMock, return_value={}
            ):
                result = await client.check_compatibility(
                    "rails", "7.1.2", {"rubygems_version": "3.0.0"}
                )
        assert result["compatible"] is True
        assert any("Recommends RubyGems" in w for w in result["warnings"])

    # === Test: check_compatibility with incompatible platform (lines 423-426)
    @pytest.mark.asyncio
    async def test_check_compatibility_platform_incompatible_error(self, client):
        versions_data = [
            {
                "number": "7.1.2",
                "prerelease": False,
                "yanked": False,
                "required_ruby_version": None,
                "required_rubygems_version": None,
                "platform": "x86_64-linux",
            }
        ]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=versions_data):
            with patch.object(
                client, "_parse_dependencies", new_callable=AsyncMock, return_value={}
            ):
                result = await client.check_compatibility(
                    "rails", "7.1.2", {"platform": "arm64-darwin"}
                )
        assert result["compatible"] is False
        assert any("Not compatible with platform" in e for e in result["errors"])

    # === Test: _check_ruby_compatibility with unparseable system version (line 442)
    def test_check_ruby_compatibility_invalid_system_version(self, client):
        result = client._check_ruby_compatibility("not-a-version", ">=3.0.0")
        assert result is True

    # === Test: _check_ruby_compatibility with tilde-greater operator (lines 449-456)
    def test_check_ruby_compatibility_tilde_gt(self, client):
        assert client._check_ruby_compatibility("3.0.5", "~> 3.0.0") is True
        assert client._check_ruby_compatibility("3.1.0", "~> 3.0.0") is False

    # === Test: _check_ruby_compatibility with >= operator (lines 458-461)
    def test_check_ruby_compatibility_gte(self, client):
        assert client._check_ruby_compatibility("3.1.0", ">= 3.0.0") is True
        assert client._check_ruby_compatibility("2.9.0", ">= 3.0.0") is False

    # === Test: _check_ruby_compatibility with exact version (lines 463-466)
    def test_check_ruby_compatibility_exact(self, client):
        assert client._check_ruby_compatibility("3.0.0", "3.0.0") is True
        assert client._check_ruby_compatibility("3.0.1", "3.0.0") is False

    # === Test: _check_platform_compatibility returns True for "ruby" (line 476)
    def test_check_platform_compatibility_ruby(self, client):
        assert client._check_platform_compatibility("x86_64-linux", "ruby") is True

    # === Test: _check_platform_compatibility with mapped platform matching (lines 487-488)
    def test_check_platform_compatibility_mapped_match(self, client):
        assert client._check_platform_compatibility("x86_64-linux", "x86_64-linux") is True
        assert client._check_platform_compatibility("arm64-darwin", "arm64-darwin") is True

    # === Test: _check_platform_compatibility with mapped platform not matching (lines 487-488)
    def test_check_platform_compatibility_mapped_no_match(self, client):
        assert client._check_platform_compatibility("arm64-darwin", "x86_64-linux") is False

    # === Test: _check_platform_compatibility fallback for unmapped platform (line 490)
    def test_check_platform_compatibility_fallback(self, client):
        assert client._check_platform_compatibility("linux", "linux") is True
        assert client._check_platform_compatibility("windows", "linux") is False
