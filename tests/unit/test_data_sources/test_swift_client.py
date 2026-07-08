from unittest.mock import AsyncMock, patch

import pytest

from backend.data_sources.swift_client import SwiftClient


class TestSwiftClient:
    @pytest.fixture
    def client(self):
        return SwiftClient()

    @pytest.fixture
    def mock_versions(self):
        return [{"version": "1.0.0"}, {"version": "0.9.0"}]

    @pytest.fixture
    def mock_manifest(self):
        return """
        // swift-tools-version:5.5
        import PackageDescription

        let package = Package(
            name: "TestPackage",
            dependencies: [
                .package(url: "https://github.com/alamofire/Alamofire", from: "5.0.0"),
                .package(url: "https://github.com/pointfreeco/swift-composable-architecture", exact: "0.40.0"),
            ]
        )
        """

    # --- get_package_info ---

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, client, mock_versions, mock_manifest):
        with (
            patch.object(
                client, "_list_versions", new_callable=AsyncMock, return_value=mock_versions
            ),
            patch.object(
                client, "_fetch_manifest", new_callable=AsyncMock, return_value=mock_manifest
            ),
        ):
            result = await client.get_package_info("owner/repo")
        assert result is not None
        assert result["name"] == "owner/repo"
        assert result["version"] == "1.0.0"
        assert result["versions"] == mock_versions
        assert "dependencies" in result
        deps = result["dependencies"].get("dependencies", {})
        assert "Alamofire" in deps
        assert deps["Alamofire"] == "5.0.0"
        assert "swift-composable-architecture" in deps
        assert deps["swift-composable-architecture"] == "0.40.0"

    @pytest.mark.asyncio
    async def test_get_package_info_no_deps(self, client, mock_versions):
        with patch.object(
            client, "_list_versions", new_callable=AsyncMock, return_value=mock_versions
        ):
            result = await client.get_package_info("owner/repo", include_dependencies=False)
        assert result is not None
        assert result["version"] == "1.0.0"
        assert result["dependencies"] == {}

    @pytest.mark.asyncio
    async def test_get_package_info_not_found(self, client):
        with patch.object(client, "_list_versions", new_callable=AsyncMock, return_value=[]):
            result = await client.get_package_info("owner/nonexistent")
        assert result is not None
        assert result["version"] == "unknown"
        assert result["versions"] == []

    @pytest.mark.asyncio
    async def test_get_package_info_exception(self, client):
        with patch.object(
            client, "_list_versions", new_callable=AsyncMock, side_effect=Exception("API error")
        ):
            result = await client.get_package_info("owner/broken")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info_no_slash(self, client, mock_versions):
        with patch.object(
            client, "_list_versions", new_callable=AsyncMock, return_value=mock_versions
        ):
            result = await client.get_package_info("single")
        assert result is not None
        assert result["name"] == "single"
        assert result["version"] == "1.0.0"

    # --- get_package_versions ---

    @pytest.mark.asyncio
    async def test_get_package_versions_success(self, client, mock_versions):
        with patch.object(
            client, "_list_versions", new_callable=AsyncMock, return_value=mock_versions
        ):
            versions = await client.get_package_versions("owner/repo")
        assert len(versions) == 2
        assert versions[0]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_package_versions_not_found(self, client):
        with patch.object(client, "_list_versions", new_callable=AsyncMock, return_value=[]):
            versions = await client.get_package_versions("owner/nonexistent")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_package_versions_exception(self, client):
        with patch.object(
            client, "_list_versions", new_callable=AsyncMock, side_effect=Exception("API error")
        ):
            versions = await client.get_package_versions("owner/broken")
        assert versions == []

    # --- resolve_package ---

    @pytest.mark.parametrize(
        "input_str,expected",
        [
            ("owner/repo", ("owner", "repo")),
            ("scope.name", ("scope", "name")),
            ("plain", ("plain", "plain")),
            ("https://github.com/apple/swift-algorithms", ("apple", "swift-algorithms")),
            ("https://github.com/apple/swift-algorithms.git", ("apple", "swift-algorithms")),
            ("git@github.com:apple/swift-algorithms.git", ("apple", "swift-algorithms")),
        ],
    )
    def test_resolve_package(self, input_str, expected):
        assert SwiftClient._resolve_package(input_str) == expected

    # --- parse_swift_deps ---

    def test_parse_swift_deps_from(self):
        content = """
        .package(url: "https://github.com/alamofire/Alamofire", from: "5.0.0"),
        """
        deps = SwiftClient._parse_swift_deps(content)
        assert deps == {"Alamofire": "5.0.0"}

    def test_parse_swift_deps_exact(self):
        content = """
        .package(url: "https://github.com/pointfreeco/swift-composable-architecture", exact: "0.40.0"),
        """
        deps = SwiftClient._parse_swift_deps(content)
        assert deps == {"swift-composable-architecture": "0.40.0"}

    def test_parse_swift_deps_branch(self):
        content = """
        .package(url: "https://github.com/apple/swift-log.git", branch: "main"),
        """
        deps = SwiftClient._parse_swift_deps(content)
        assert deps == {"swift-log": "main"}

    def test_parse_swift_deps_multiple(self):
        content = """
        .package(url: "https://github.com/alamofire/Alamofire", from: "5.0.0"),
        .package(url: "https://github.com/apple/swift-argument-parser", from: "1.0.0"),
        """
        deps = SwiftClient._parse_swift_deps(content)
        assert deps == {"Alamofire": "5.0.0", "swift-argument-parser": "1.0.0"}

    def test_parse_swift_deps_skip_comments(self):
        content = """
        // .package(url: "https://github.com/evil/package", from: "1.0.0"),
        .package(url: "https://github.com/good/package", from: "2.0.0"),
        """
        deps = SwiftClient._parse_swift_deps(content)
        assert deps == {"package": "2.0.0"}

    def test_parse_swift_deps_empty(self):
        assert SwiftClient._parse_swift_deps("") == {}
        assert SwiftClient._parse_swift_deps("// nothing here") == {}
