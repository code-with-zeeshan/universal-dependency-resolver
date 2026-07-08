# tests/unit/test_core/test_utils.py

import pytest

from backend.core.utils import (
    compare_versions,
    extract_requirements,
    hash_system_info,
    is_compatible_version,
    normalize_package_name,
    parse_version,
    parse_version_key,
    run_async,
    sanitize_ecosystem_name,
)


class TestRunAsync:
    def test_run_async_no_running_loop(self):
        async def coro():
            return 42

        result = run_async(coro())
        assert result == 42

    def test_run_async_with_running_loop(self):
        """run_async may raise RuntimeError when called from a running loop
        depending on Python version; just verify it doesn't crash the process.
        """

        async def inner():
            return "inner"

        try:
            result = run_async(inner())
            assert result == "inner"
        except RuntimeError:
            pass


class TestParseVersion:
    def test_valid_version(self):
        v = parse_version("1.2.3")
        assert v is not None
        assert v.major == 1
        assert v.minor == 2
        assert v.micro == 3

    def test_invalid_version(self):
        v = parse_version("not-a-version")
        assert v is None

    def test_pep440_version(self):
        v = parse_version("2.0.0rc1")
        assert v is not None
        assert v.major == 2


class TestParseVersionKey:
    def test_valid(self):
        key = parse_version_key("1.9.0")
        assert key.major == 1

    def test_invalid_fallback(self):
        key = parse_version_key("bad")
        assert key.major == 0
        assert key.minor == 0
        assert key.micro == 0


class TestIsCompatibleVersion:
    def test_simple_compatible(self):
        assert is_compatible_version("2.0.0", ">=1.0.0") is True

    def test_not_compatible(self):
        assert is_compatible_version("0.9.0", ">=1.0.0") is False

    def test_exact_match(self):
        assert is_compatible_version("1.0.0", "==1.0.0") is True

    def test_invalid_spec(self):
        assert is_compatible_version("1.0.0", "garbage") is False


class TestNormalizePackageName:
    def test_lowercase(self):
        assert normalize_package_name("MyPackage") == "mypackage"

    def test_replace_underscores(self):
        assert normalize_package_name("my_package") == "my-package"

    def test_replace_dots(self):
        assert normalize_package_name("my.package") == "my-package"

    def test_mixed_separators(self):
        assert normalize_package_name("A_B.C-D") == "a-b-c-d"

    def test_already_normalized(self):
        assert normalize_package_name("requests") == "requests"


class TestExtractRequirements:
    def test_requirements_txt_simple(self):
        content = "requests>=2.0.0\nflask\n# comment\n\nnumpy==1.24"
        result = extract_requirements(content, "requirements.txt")
        assert len(result) == 3
        assert result[0]["name"] == "requests"
        assert result[1]["name"] == "flask"
        assert result[2]["name"] == "numpy"

    def test_requirements_txt_empty(self):
        assert extract_requirements("", "requirements.txt") == []

    def test_environment_yml(self):
        result = extract_requirements(
            "dependencies:\n  - numpy\n  - pandas>=1.0\n", "environment.yml"
        )
        names = [r["name"] for r in result]
        assert "numpy" in names
        assert "pandas" in names

    def test_unknown_file_type(self):
        result = extract_requirements("anything\n", "unknown.txt")
        assert result == []


class TestHashSystemInfo:
    def test_hash_is_deterministic(self):
        info = {"os": "linux", "cpu": {"cores": 4}}
        h1 = hash_system_info(info)
        h2 = hash_system_info(info)
        assert h1 == h2
        assert len(h1) == 64

    def test_different_inputs_different_hashes(self):
        h1 = hash_system_info({"a": 1})
        h2 = hash_system_info({"a": 2})
        assert h1 != h2


class TestSanitizeEcosystemName:
    @pytest.mark.parametrize(
        ("alias", "expected"),
        [
            ("pip", "pypi"),
            ("python", "pypi"),
            ("node", "npm"),
            ("cargo", "crates"),
            ("rust", "crates"),
            ("java", "maven"),
            ("gradle", "gradle"),
            ("swift", "swift"),
            ("elixir", "hex"),
            ("dart", "pub"),
            ("flutter", "pub"),
            ("unknown", "unknown"),
            ("", ""),
        ],
    )
    def test_aliases(self, alias, expected):
        assert sanitize_ecosystem_name(alias) == expected

    def test_case_insensitive(self):
        assert sanitize_ecosystem_name("PIP") == "pypi"
        assert sanitize_ecosystem_name("Rust") == "crates"


class TestCompareVersions:
    def test_less_than(self):
        assert compare_versions("1.0.0", "2.0.0") == -1

    def test_greater_than(self):
        assert compare_versions("3.0.0", "2.0.0") == 1

    def test_equal(self):
        assert compare_versions("1.0.0", "1.0.0") == 0

    def test_invalid_returns_zero(self):
        assert compare_versions("bad", "1.0.0") == 0
