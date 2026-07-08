from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.homebrew_client import HomebrewClient, PackageType


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
            "bottle": {"stable": {"rebuild": 0, "files": {"arm64_ventura": {"url": "..."}}}},
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
    async def test_get_package_info_async_calls_correct_url(self, client, sample_formula_data):
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
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info_async("nonexistent", PackageType.FORMULA)
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

    @pytest.mark.asyncio
    async def test_package_exists_returns_true(self, client):
        session = client._get_session()
        with patch.object(session, "head", new_callable=AsyncMock) as mock_head:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_head.return_value = mock_response
            assert await client.package_exists("curl", PackageType.FORMULA) is True
            mock_head.assert_called_once()

    @pytest.mark.asyncio
    async def test_package_exists_returns_false(self, client):
        session = client._get_session()
        with patch.object(session, "head", new_callable=AsyncMock) as mock_head:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_head.return_value = mock_response
            assert await client.package_exists("nonexistent", PackageType.FORMULA) is False

    @pytest.mark.asyncio
    async def test_package_exists_handles_exception(self, client):
        session = client._get_session()
        with patch.object(session, "head", side_effect=Exception("Network error")):
            assert await client.package_exists("curl", PackageType.FORMULA) is False

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
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=[]):
            results = await client.search_packages("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_packages_empty_on_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("Error")):
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
    async def test_check_compatibility_returns_result(self, client, sample_formula_data):
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=sample_formula_data,
        ):
            result = await client.check_compatibility("curl", PackageType.FORMULA, {})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_package_exists_cask(self, client):
        session = client._get_session()
        with patch.object(session, "head", new_callable=AsyncMock) as mock_head:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_head.return_value = mock_response
            assert await client.package_exists("visual-studio-code", PackageType.CASK) is True

    @pytest.mark.asyncio
    async def test_search_casks_with_matches(self, client):
        cask_data = {
            "token": "visual-studio-code",
            "name": ["Visual Studio Code"],
            "desc": "Code editor",
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=[cask_data]):
            results = await client.search_packages("visual", package_type=PackageType.CASK)
        assert len(results) == 1
        assert results[0]["name"] == "visual-studio-code"

    @pytest.mark.asyncio
    async def test_search_casks_exception(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, side_effect=Exception("Error")):
            results = await client.search_packages("visual", package_type=PackageType.CASK)
        assert results == []

    def test_calculate_relevance_score_startswith(self, client):
        assert client._calculate_relevance_score("python@3.11", "python") == 0.8

    def test_calculate_relevance_score_in(self, client):
        assert client._calculate_relevance_score("python3", "thon") == 0.6

    def test_calculate_relevance_score_fallback(self, client):
        assert client._calculate_relevance_score("abc", "xyz") == 0.1

    @pytest.mark.asyncio
    async def test_get_package_info_async_cask(self, client):
        cask_data = {
            "token": "visual-studio-code",
            "name": ["Visual Studio Code"],
            "desc": "Code editor",
            "version": "1.85.0",
            "homepage": "https://code.visualstudio.com",
            "sha256": "abc123",
            "url": "https://update.code.visualstudio.com/1.85.0/darwin/universal",
            "depends_on": {
                "macos": {"min": "11.0"},
                "arch": "x86_64",
            },
        }
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=cask_data):
            result = await client.get_package_info_async("visual-studio-code", PackageType.CASK)
        assert result is not None
        assert result["name"] == "visual-studio-code"
        assert result["type"] == "cask"

    @pytest.mark.asyncio
    async def test_get_package_info_async_cask_not_found(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
            result = await client.get_package_info_async("nonexistent", PackageType.CASK)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_dependencies_cask(self, client):
        cask_data = {
            "token": "visual-studio-code",
            "dependencies": [],
            "build_dependencies": [],
            "optional_dependencies": [],
            "recommended_dependencies": [],
            "test_dependencies": [],
            "depends_on": {
                "formula": ["python@3.11"],
                "cask": ["docker"],
                "macos": {"min": "11.0"},
            },
        }
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=cask_data,
        ):
            deps = await client.get_dependencies("visual-studio-code", PackageType.CASK)
        assert "formula" in deps
        assert deps["formula"] == ["python@3.11"]
        assert deps["cask"] == ["docker"]
        assert deps["macos"] == {"min": "11.0"}

    def test_extract_formula_system_requirements_xcode(self, client):
        data = {
            "requirements": [
                {"name": "xcode", "version": "14.0"},
            ],
            "bottle": {},
        }
        reqs = client._extract_formula_system_requirements(data)
        assert reqs["xcode"] == "14.0"

    def test_extract_formula_system_requirements_java(self, client):
        data = {
            "requirements": [
                {"name": "java", "version": "17"},
            ],
            "bottle": {},
        }
        reqs = client._extract_formula_system_requirements(data)
        assert reqs["java"] == "17"

    def test_extract_formula_system_requirements_arch(self, client):
        data = {
            "requirements": [
                {"name": "arch", "specs": ["arm64"]},
            ],
            "bottle": {},
        }
        reqs = client._extract_formula_system_requirements(data)
        assert reqs["arch"] == ["arm64"]

    def test_extract_formula_system_requirements_bottle_macos(self, client):
        data = {
            "bottle": {
                "stable": {
                    "files": {
                        "monterey": {},
                        "big_sur": {},
                        "linux": {},
                    }
                }
            },
        }
        reqs = client._extract_formula_system_requirements(data)
        assert reqs["macos_version"] == ["monterey", "big_sur"]

    def test_extract_cask_system_requirements_macos_dict(self, client):
        data = {
            "depends_on": {
                "macos": {"min": "11.0", "max": "14.0"},
            },
        }
        reqs = client._extract_cask_system_requirements(data)
        assert reqs["macos_version"] == {"min": "11.0", "max": "14.0"}

    def test_extract_cask_system_requirements_macos_str(self, client):
        data = {
            "depends_on": {
                "macos": ">=11.0",
            },
        }
        reqs = client._extract_cask_system_requirements(data)
        assert reqs["macos_version"] == {"min": ">=11.0"}

    def test_extract_cask_system_requirements_arch(self, client):
        data = {
            "depends_on": {
                "arch": "x86_64",
            },
        }
        reqs = client._extract_cask_system_requirements(data)
        assert reqs["arch"] == "x86_64"

    @pytest.mark.asyncio
    async def test_check_compatibility_not_found(self, client):
        with patch.object(
            client, "get_package_info_async", new_callable=AsyncMock, return_value=None
        ):
            result = await client.check_compatibility(
                "nonexistent", PackageType.FORMULA, {"macos_version": "13.0"}
            )
        assert result["compatible"] is False
        assert "Package not found" in result["errors"]

    @pytest.mark.asyncio
    async def test_check_compatibility_macos_incompatible(self, client):
        formula_data = {"name": "curl", "system_requirements": {"macos_version": "14.0"}}
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=formula_data,
        ):
            result = await client.check_compatibility(
                "curl", PackageType.FORMULA, {"macos_version": "13.0"}
            )
        assert result["compatible"] is False
        assert any("macOS" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_check_compatibility_macos_compatible(self, client):
        formula_data = {"name": "curl", "system_requirements": {"macos_version": "13.0"}}
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=formula_data,
        ):
            result = await client.check_compatibility(
                "curl", PackageType.FORMULA, {"macos_version": "14.0"}
            )
        assert result["compatible"] is True

    @pytest.mark.asyncio
    async def test_check_compatibility_arch_incompatible(self, client):
        formula_data = {
            "name": "curl",
            "system_requirements": {"macos_version": None, "arch": ["arm64"]},
        }
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=formula_data,
        ):
            result = await client.check_compatibility(
                "curl", PackageType.FORMULA, {"macos_version": "14.0", "arch": "x86_64"}
            )
        assert result["compatible"] is False
        assert any("architecture" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_check_compatibility_deprecated(self, client):
        formula_data = {"name": "curl", "deprecated": True, "deprecation_reason": "Unmaintained"}
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=formula_data,
        ):
            result = await client.check_compatibility("curl", PackageType.FORMULA)
        assert "Package is deprecated: Unmaintained" in result["warnings"]

    @pytest.mark.asyncio
    async def test_check_compatibility_disabled(self, client):
        formula_data = {"name": "curl", "disabled": True, "disable_reason": "Broken"}
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=formula_data,
        ):
            result = await client.check_compatibility("curl", PackageType.FORMULA)
        assert "Package is disabled: Broken" in result["errors"]

    @pytest.mark.asyncio
    async def test_check_compatibility_conflicts(self, client):
        formula_data = {"name": "curl", "conflicts_with": ["wget", "aria2"]}
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=formula_data,
        ):
            result = await client.check_compatibility("curl", PackageType.FORMULA)
        assert "May conflict with: wget, aria2" in result["warnings"]

    @pytest.mark.asyncio
    async def test_check_compatibility_keg_only(self, client):
        formula_data = {
            "name": "curl",
            "keg_only": True,
            "keg_only_reason": {"reason": "macOS already provides curl"},
        }
        with patch.object(
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            return_value=formula_data,
        ):
            result = await client.check_compatibility("curl", PackageType.FORMULA)
        assert "Keg-only: macOS already provides curl" in result["warnings"]

    def test_check_macos_compatibility_string(self, client):
        assert client._check_macos_compatibility("14.0", "13.0") is True
        assert client._check_macos_compatibility("12.0", "13.0") is False

    def test_check_macos_compatibility_dict_min(self, client):
        required = {"min": "12.0"}
        assert client._check_macos_compatibility("13.0", required) is True
        assert client._check_macos_compatibility("11.0", required) is False

    def test_check_macos_compatibility_dict_max(self, client):
        required = {"max": "14.0"}
        assert client._check_macos_compatibility("13.0", required) is True
        assert client._check_macos_compatibility("15.0", required) is False

    def test_check_macos_compatibility_dict_both(self, client):
        required = {"min": "12.0", "max": "14.0"}
        assert client._check_macos_compatibility("13.0", required) is True
        assert client._check_macos_compatibility("11.0", required) is False
        assert client._check_macos_compatibility("15.0", required) is False

    def test_check_macos_compatibility_list(self, client):
        required = ["12.0", "13.0", "14.0"]
        assert client._check_macos_compatibility("13.0", required) is True
        assert client._check_macos_compatibility("11.0", required) is False

    def test_check_macos_compatibility_fallback(self, client):
        assert client._check_macos_compatibility("13.0", None) is True
        assert client._check_macos_compatibility("13.0", 42) is True
