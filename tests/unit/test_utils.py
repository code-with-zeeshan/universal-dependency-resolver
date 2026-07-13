"""Tests for backend.core.utils — targeting all uncovered lines."""

import asyncio

import pytest

from backend.core.utils import (
    compare_versions,
    download_github_repo,
    extract_requirements,
    hash_system_info,
    is_compatible_version,
    normalize_package_name,
    parse_version,
    parse_version_key,
    run_async,
    run_async_await,
    sanitize_ecosystem_name,
)


class TestRunAsync:
    @pytest.mark.asyncio
    async def test_run_async_await(self):
        async def foo():
            return 42

        result = await run_async_await(foo())
        assert result == 42

    def test_run_async(self):
        async def foo():
            return 42

        result = run_async(foo())
        assert result == 42


class TestParseVersion:
    def test_parse_version_valid(self):
        v = parse_version("1.2.3")
        assert v is not None
        assert v.major == 1
        assert v.minor == 2

    def test_parse_version_invalid(self):
        v = parse_version("not-a-version")
        assert v is None

    def test_parse_version_empty(self):
        v = parse_version("")
        assert v is None


class TestParseVersionKey:
    def test_parse_version_key_valid(self):
        v = parse_version_key("2.0.0")
        assert v.major == 2

    def test_parse_version_key_invalid_fallback(self):
        v = parse_version_key("invalid")
        assert v == parse_version_key("0.0.0")
        assert v.major == 0

    def test_parse_version_key_empty(self):
        v = parse_version_key("")
        assert v.major == 0


class TestIsCompatibleVersion:
    def test_compatible(self):
        assert is_compatible_version("1.5.0", ">=1.0.0") is True

    def test_incompatible(self):
        assert is_compatible_version("0.9.0", ">=1.0.0") is False

    def test_invalid_version(self):
        assert is_compatible_version("not-a-version", ">=1.0.0") is False

    def test_invalid_spec(self):
        assert is_compatible_version("1.0.0", "not-a-spec") is False


class TestNormalizePackageName:
    def test_normalize(self):
        assert normalize_package_name("Foo_Bar") == "foo-bar"

    def test_already_normalized(self):
        assert normalize_package_name("foo-bar") == "foo-bar"

    def test_underscores(self):
        assert normalize_package_name("foo__bar") == "foo-bar"

    def test_dots(self):
        assert normalize_package_name("foo.bar") == "foo-bar"


class TestExtractRequirements:
    def test_requirements_txt(self):
        content = "requests>=2.28\nflask>=2.0\n# comment\nnumpy\n"
        reqs = extract_requirements(content, "requirements.txt")
        assert len(reqs) == 3
        assert reqs[0]["name"] == "requests"

    def test_requirements_txt_blank_lines(self):
        content = "\n\nrequests\n\n"
        reqs = extract_requirements(content, "requirements.txt")
        assert len(reqs) == 1

    def test_requirements_txt_empty(self):
        assert extract_requirements("", "requirements.txt") == []

    def test_environment_yml(self):
        content = "dependencies:\n  - requests>=2.28\n  - flask\n"
        reqs = extract_requirements(content, "environment.yml")
        assert len(reqs) == 2

    def test_environment_yml_invalid(self):
        reqs = extract_requirements("invalid: {", "environment.yml")
        assert reqs == []


class TestHashSystemInfo:
    def test_hash(self):
        h = hash_system_info({"os": "linux", "arch": "x86_64"})
        assert isinstance(h, str)
        assert len(h) == 64  # sha256 hex

    def test_deterministic(self):
        info = {"os": "linux", "arch": "x86_64"}
        assert hash_system_info(info) == hash_system_info(info)

    def test_empty(self):
        h = hash_system_info({})
        assert isinstance(h, str)
        assert len(h) == 64


class TestSanitizeEcosystemName:
    def test_pypi_aliases(self):
        assert sanitize_ecosystem_name("pip") == "pypi"
        assert sanitize_ecosystem_name("python") == "pypi"
        assert sanitize_ecosystem_name("py") == "pypi"

    def test_npm_aliases(self):
        assert sanitize_ecosystem_name("node") == "npm"
        assert sanitize_ecosystem_name("nodejs") == "npm"
        assert sanitize_ecosystem_name("js") == "npm"

    def test_crates_aliases(self):
        assert sanitize_ecosystem_name("cargo") == "crates"
        assert sanitize_ecosystem_name("rust") == "crates"
        assert sanitize_ecosystem_name("crates.io") == "crates"

    def test_maven_aliases(self):
        assert sanitize_ecosystem_name("java") == "maven"
        assert sanitize_ecosystem_name("mvn") == "maven"

    def test_conda_aliases(self):
        assert sanitize_ecosystem_name("anaconda") == "conda"
        assert sanitize_ecosystem_name("miniconda") == "conda"

    def test_go_aliases(self):
        assert sanitize_ecosystem_name("go") == "gomodules"
        assert sanitize_ecosystem_name("golang") == "gomodules"
        assert sanitize_ecosystem_name("gomod") == "gomodules"

    def test_apt_aliases(self):
        assert sanitize_ecosystem_name("debian") == "apt"
        assert sanitize_ecosystem_name("ubuntu") == "apt"
        assert sanitize_ecosystem_name("deb") == "apt"

    def test_apk_alias(self):
        assert sanitize_ecosystem_name("alpine") == "apk"

    def test_cocoapods_aliases(self):
        assert sanitize_ecosystem_name("pods") == "cocoapods"
        assert sanitize_ecosystem_name("cocoa") == "cocoapods"
        assert sanitize_ecosystem_name("ios") == "cocoapods"

    def test_rubygems_aliases(self):
        assert sanitize_ecosystem_name("ruby") == "rubygems"
        assert sanitize_ecosystem_name("gem") == "rubygems"
        assert sanitize_ecosystem_name("gems") == "rubygems"

    def test_packagist_aliases(self):
        assert sanitize_ecosystem_name("php") == "packagist"
        assert sanitize_ecosystem_name("composer") == "packagist"

    def test_nuget_aliases(self):
        assert sanitize_ecosystem_name("dotnet") == "nuget"
        assert sanitize_ecosystem_name(".net") == "nuget"
        assert sanitize_ecosystem_name("csharp") == "nuget"
        assert sanitize_ecosystem_name("c#") == "nuget"

    def test_homebrew_aliases(self):
        assert sanitize_ecosystem_name("brew") == "homebrew"
        assert sanitize_ecosystem_name("osx") == "homebrew"
        assert sanitize_ecosystem_name("macos") == "homebrew"

    def test_gradle_aliases(self):
        assert sanitize_ecosystem_name("gradle") == "gradle"
        assert sanitize_ecosystem_name("groovy") == "gradle"
        assert sanitize_ecosystem_name("kotlin") == "gradle"

    def test_swift_aliases(self):
        assert sanitize_ecosystem_name("swift") == "swift"
        assert sanitize_ecosystem_name("spm") == "swift"

    def test_hex_aliases(self):
        assert sanitize_ecosystem_name("elixir") == "hex"
        assert sanitize_ecosystem_name("exlixir") == "hex"  # typo alias

    def test_haskell_aliases(self):
        assert sanitize_ecosystem_name("cabal") == "haskell"
        assert sanitize_ecosystem_name("haskell") == "haskell"
        assert sanitize_ecosystem_name("stack") == "haskell"

    def test_pub_aliases(self):
        assert sanitize_ecosystem_name("dart") == "pub"
        assert sanitize_ecosystem_name("flutter") == "pub"
        assert sanitize_ecosystem_name("pub.dev") == "pub"

    def test_unknown_passthrough(self):
        assert sanitize_ecosystem_name("unknown") == "unknown"

    def test_case_insensitive(self):
        assert sanitize_ecosystem_name("NODE") == "npm"
        assert sanitize_ecosystem_name("Python") == "pypi"


class TestCompareVersions:
    def test_less_than(self):
        assert compare_versions("1.0.0", "2.0.0") == -1

    def test_greater_than(self):
        assert compare_versions("2.0.0", "1.0.0") == 1

    def test_equal(self):
        assert compare_versions("1.0.0", "1.0.0") == 0

    def test_invalid(self):
        assert compare_versions("invalid", "1.0.0") == 0

    def test_both_invalid(self):
        assert compare_versions("a", "b") == 0


class TestDownloadGithubRepo:
    def test_download_random(self):
        """Only test that the function exists and has the right signature."""
        import inspect

        sig = inspect.signature(download_github_repo)
        assert "url" in sig.parameters
        assert "branch" in sig.parameters
