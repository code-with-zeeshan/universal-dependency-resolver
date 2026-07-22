"""Unit tests for backend/core/swift_parser.py."""

from backend.core.swift_parser import parse_package_swift


class TestParsePackageSwift:
    def test_empty_content(self):
        result = parse_package_swift("")
        assert result["dependencies"] == {}
        assert result["targets"] == []
        assert result["platforms"] == []
        assert result["swift_tools_version"] is None

    def test_comment_only(self):
        result = parse_package_swift("// swift-tools-version:5.9")
        assert result["swift_tools_version"] == "5.9"
        assert result["dependencies"] == {}

    def test_single_package_url_dep(self):
        content = """
        // swift-tools-version:5.7
        .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.6.0")
        """
        result = parse_package_swift(content)
        assert result["swift_tools_version"] == "5.7"
        assert "Alamofire" in result["dependencies"]
        assert result["dependencies"]["Alamofire"] == "5.6.0"

    def test_exact_version(self):
        content = """
        .package(url: "https://github.com/apple/swift-argument-parser", exact: "1.2.0")
        """
        result = parse_package_swift(content)
        assert "swift-argument-parser" in result["dependencies"]
        assert result["dependencies"]["swift-argument-parser"] == "1.2.0"

    def test_branch_dependency(self):
        content = """.package(url: "https://github.com/vapor/vapor.git", branch: "main")"""
        result = parse_package_swift(content)
        assert "vapor" in result["dependencies"]
        assert result["dependencies"]["vapor"] == "main"

    def test_revision_dependency(self):
        content = """.package(url: "https://github.com/pointfreeco/swift-composable-architecture", revision: "abc123")"""
        result = parse_package_swift(content)
        assert "swift-composable-architecture" in result["dependencies"]

    def test_multiple_deps(self):
        content = """
        .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.6.0")
        .package(url: "https://github.com/SDWebImage/SDWebImage.git", from: "5.15.0")
        """
        result = parse_package_swift(content)
        assert len(result["dependencies"]) == 2

    def test_target_names(self):
        content = """
        .target(name: "MyLibrary"),
        .executableTarget(name: "MyApp"),
        .testTarget(name: "MyLibraryTests"),
        """
        result = parse_package_swift(content)
        assert "MyLibrary" in result["targets"]
        assert "MyApp" in result["targets"]
        assert "MyLibraryTests" in result["targets"]

    def test_platforms(self):
        content = """
        .macOS("13.0"),
        .iOS("16.0"),
        .watchOS("9.0"),
        .tvOS("16.0"),
        .visionOS("1.0"),
        """
        result = parse_package_swift(content)
        assert "macOS 13.0" in result["platforms"]
        assert "iOS 16.0" in result["platforms"]
        assert "watchOS 9.0" in result["platforms"]
        assert "tvOS 16.0" in result["platforms"]
        assert "visionOS 1.0" in result["platforms"]

    def test_comment_lines_skipped(self):
        content = """
        // This is a comment
        // .package(url: "https://...", from: "1.0.0")
        .package(url: "https://github.com/real/package.git", from: "2.0.0")
        """
        result = parse_package_swift(content)
        assert len(result["dependencies"]) == 1
        assert "package" in result["dependencies"]

    def test_github_url_with_trailing_slash(self):
        content = """.package(url: "https://github.com/foo/bar/", from: "1.0.0")"""
        result = parse_package_swift(content)
        assert "bar" in result["dependencies"]

    def test_non_github_url(self):
        content = """.package(url: "https://gitlab.com/group/project.git", from: "0.1.0")"""
        result = parse_package_swift(content)
        assert "project" in result["dependencies"]

    def test_no_tools_version(self):
        content = """.package(url: "https://github.com/foo/bar.git", from: "1.0.0")"""
        result = parse_package_swift(content)
        assert result["swift_tools_version"] is None
