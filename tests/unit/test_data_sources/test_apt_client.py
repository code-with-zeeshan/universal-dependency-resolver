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
    async def test_get_package_info_async_calls_correct_url(self, client, sample_package_data):
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
        with patch.object(client, "_get_packages_list", new_callable=AsyncMock, return_value={}):
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
            client,
            "get_package_info_async",
            new_callable=AsyncMock,
            side_effect=Exception("apt error"),
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
        with patch.object(client, "_get_packages_list", new_callable=AsyncMock, return_value={}):
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
        with patch.object(client, "_get_packages_list", new_callable=AsyncMock, return_value={}):
            versions = await client.get_versions("nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_dependencies_success(self, client, sample_package_data):
        with patch.object(
            client,
            "_get_packages_list",
            new_callable=AsyncMock,
            return_value={"nginx": sample_package_data},
        ):
            deps = await client.get_dependencies("nginx", "1.24.0-1")
        assert "depends" in deps

    @pytest.mark.asyncio
    async def test_get_dependencies_returns_empty_on_error(self, client):
        with patch.object(client, "_get_packages_list", new_callable=AsyncMock, return_value={}):
            deps = await client.get_dependencies("nonexistent", "1.0")
        assert deps == {}

    @pytest.mark.asyncio
    async def test_get_dependencies_no_version_match(self, client, sample_package_data):
        pkg_data = dict(sample_package_data, version="2.0.0-1")
        with patch.object(
            client, "_get_packages_list", new_callable=AsyncMock, return_value={"nginx": pkg_data}
        ):
            deps = await client.get_dependencies("nginx", "1.24.0-1")
        assert deps == {}

    @pytest.mark.asyncio
    async def test_get_dependencies_version_none(self, client, sample_package_data):
        with patch.object(
            client,
            "_get_packages_list",
            new_callable=AsyncMock,
            return_value={"nginx": sample_package_data},
        ):
            deps = await client.get_dependencies("nginx")
        assert "depends" in deps

    def test_parse_dependency_string_or_deps(self, client):
        deps = client._parse_dependency_string("libc6 | libc7")
        assert len(deps) == 1
        assert "or_dependencies" in deps[0]
        assert len(deps[0]["or_dependencies"]) == 2

    def test_parse_dependency_string_or_deps_mixed(self, client):
        deps = client._parse_dependency_string("libc6 >= 2.34 | libc7, python3")
        assert len(deps) == 2
        assert deps[1]["name"] == "python3"

    def test_parse_dependency_string_no_match(self, client):
        deps = client._parse_dependency_string("")
        assert deps == []

    def test_parse_packages_file_empty(self, client):
        result = client._parse_packages_file("")
        assert result == {}

    def test_parse_packages_file_single_package(self, client):
        content = "Package: nginx\nVersion: 1.24.0-1\nDescription: web server\n\n"
        result = client._parse_packages_file(content)
        assert "nginx" in result
        assert result["nginx"]["version"] == "1.24.0-1"
        assert result["nginx"]["description"] == "web server"

    def test_parse_packages_file_multiple_packages(self, client):
        content = "Package: nginx\nVersion: 1.24.0-1\n\nPackage: curl\nVersion: 7.88.1\n\n"
        result = client._parse_packages_file(content)
        assert len(result) == 2
        assert result["nginx"]["version"] == "1.24.0-1"
        assert result["curl"]["version"] == "7.88.1"

    def test_parse_packages_file_continuation_line(self, client):
        content = "Package: nginx\nDescription: small, powerful\n scalable web/proxy server\n\n"
        result = client._parse_packages_file(content)
        assert result["nginx"]["description"] == "small, powerful\nscalable web/proxy server"

    def test_parse_packages_file_skips_entry_without_package_field(self, client):
        content = "Version: 1.0\nDescription: no package name\n\n"
        result = client._parse_packages_file(content)
        assert result == {}

    def test_parse_packages_file_no_trailing_newline(self, client):
        content = "Package: nginx\nVersion: 1.24.0-1"
        result = client._parse_packages_file(content)
        assert "nginx" in result

    def test_parse_packages_file_only_whitespace_lines(self, client):
        result = client._parse_packages_file("   \n\n  \n")
        assert result == {}

    def test_extract_system_requirements_with_libc(self, client):
        pkg_data = {"depends": "libc6 (>= 2.34), libssl3 (>= 3.0)"}
        reqs = client._extract_system_requirements(pkg_data)
        assert reqs["libc_version"] == "2.34"

    def test_extract_system_requirements_with_kernel(self, client):
        pkg_data = {"depends": "linux-image (>= 5.10.0-10)"}
        reqs = client._extract_system_requirements(pkg_data)
        assert reqs["kernel_version"] == "5.10.0-10"

    def test_extract_system_requirements_with_both(self, client):
        pkg_data = {
            "depends": "libc6 (>= 2.34), linux-headers (>= 5.10.0-10)",
        }
        reqs = client._extract_system_requirements(pkg_data)
        assert reqs["libc_version"] == "2.34"
        assert reqs["kernel_version"] == "5.10.0-10"

    def test_extract_system_requirements_no_depends(self, client):
        pkg_data = {"architecture": "arm64", "essential": "yes"}
        reqs = client._extract_system_requirements(pkg_data)
        assert "libc_version" not in reqs
        assert "kernel_version" not in reqs
        assert reqs["architecture"] == "arm64"
        assert reqs["essential"] is True
        assert reqs["priority"] == "optional"

    @pytest.mark.asyncio
    async def test_get_packages_list_cache_hit(self, client, sample_package_data):
        client._packages_cache["packages:stable:main"] = {"nginx": sample_package_data}
        with patch.object(client, "_get_session") as mock_get_session:
            result = await client._get_packages_list("stable", "main")
        assert result == {"nginx": sample_package_data}
        mock_get_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_packages_list_success(self, client):
        import gzip

        content = "Package: nginx\nVersion: 1.24.0-1\n\n"
        gz_content = gzip.compress(content.encode())
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=gz_content)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._get_packages_list("stable", "main")
        assert "nginx" in result
        assert result["nginx"]["version"] == "1.24.0-1"

    @pytest.mark.asyncio
    async def test_get_packages_list_non_200(self, client):
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._get_packages_list("stable", "main")
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_packages_list_exception(self, client):
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection error")
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._get_packages_list("stable", "main")
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_packages_list_caches_result(self, client):
        import gzip

        content = "Package: nginx\nVersion: 1.24.0-1\n\n"
        gz_content = gzip.compress(content.encode())
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=gz_content)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._get_packages_list("stable", "main")
        assert client._packages_cache.get("packages:stable:main") is result

    @pytest.mark.asyncio
    async def test_search_packages_respects_limit(self, client):
        many_packages = {
            f"pkg{i}": {"version": f"1.{i}", "description": f"package {i}"} for i in range(10)
        }
        with patch.object(
            client, "_get_packages_list", new_callable=AsyncMock, return_value=many_packages
        ):
            results = await client.search_packages("pkg", limit=3)
        assert len(results) == 3
