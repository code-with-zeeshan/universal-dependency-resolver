# tests/unit/test_core/test_constraint_normalizer.py
import pytest

from backend.core.constraint_normalizer import (
    _normalize_npm,
    _normalize_pip,
    normalize_constraint,
    normalize_version,
    parse_semver,
)


class TestNormalizeVersion:
    @pytest.mark.parametrize(("input_ver", "expected"), [
        ("1.2.3", "1.2.3"),
        ("v2.0.0", "2.0.0"),
        ("=3.0.0", "3.0.0"),
        (" 1.0.0 ", "1.0.0"),
        ("V1.2.3", "1.2.3"),
        ("", "0.0.0"),
        ("1.0", "1.0.0"),
        ("2", "2.0.0"),
        ("1.2.3.4", "1.2.3"),
        ("v1.0.0-beta", "1.0.0"),
    ])
    def test_normalize(self, input_ver, expected):
        assert normalize_version(input_ver) == expected

    def test_ecosystem_passthrough(self):
        assert normalize_version("1.2.3", "npm") == "1.2.3"


class TestParseSemver:
    def test_standard(self):
        assert parse_semver("1.2.3") == (1, 2, 3)

    def test_major_only(self):
        assert parse_semver("1") == (1, 0, 0)

    def test_two_parts(self):
        assert parse_semver("2.5") == (2, 5, 0)

    def test_non_digit_parts(self):
        assert parse_semver("1.x.3") == (1, 0, 3)

    def test_empty_string(self):
        assert parse_semver("") == (0, 0, 0)

    def test_with_v_prefix(self):
        # v1 is not all digits → major=0, but minor/patch parse normally
        assert parse_semver("v1.2.3") == (0, 2, 3)


class TestNormalizeConstraint:
    def test_empty_returns_wildcard(self):
        assert normalize_constraint("", "pypi") == "*"
        assert normalize_constraint(None, "pypi") == "*"

    def test_wildcard(self):
        assert normalize_constraint("*", "pypi") == "*"
        assert normalize_constraint("any", "pypi") == "*"

    def test_pep440_simple_ge(self):
        assert normalize_constraint(">=1.0.0", "pypi") == ">=1.0.0"

    def test_pep440_simple_eq(self):
        assert normalize_constraint("==2.0", "pypi") == "==2.0"

    def test_pep440_tilde(self):
        result = normalize_constraint("~=1.2", "pypi")
        assert result == ">=1.2,<2.0.0"

    def test_pep440_not_equal(self):
        assert normalize_constraint("!=1.0.0", "pypi") == "!=1.0.0"

    def test_pep440_comma_separated(self):
        result = normalize_constraint(">=1.0,<2.0", "pypi")
        assert ">=" in result
        assert "<" in result

    def test_npm_caret_zero_major(self):
        result = normalize_constraint("^0.5.0", "npm")
        assert result == ">=0.5.0,<0.6.0"

    def test_npm_caret_nonzero_major(self):
        result = normalize_constraint("^1.2.3", "npm")
        assert result == ">=1.2.3,<2.0.0"

    def test_npm_caret_zero_minor(self):
        result = normalize_constraint("^0.0.3", "npm")
        assert result == ">=0.0.3,<0.0.4"

    def test_npm_tilde(self):
        result = normalize_constraint("~1.2.3", "npm")
        assert result == ">=1.2.3,<1.3.0"

    def test_npm_bare_version(self):
        result = normalize_constraint("1.2.3", "npm")
        assert result == ">=1.2.3"

    def test_crates_bare_version(self):
        result = normalize_constraint("0.5.0", "crates")
        assert result == ">=0.5.0,<0.6.0"

    def test_crates_bare_nonzero(self):
        result = normalize_constraint("1.0.0", "crates")
        assert result == ">=1.0.0,<2.0.0"

    def test_rubygems_pessimistic(self):
        result = normalize_constraint("~> 1.2.3", "rubygems")
        assert result == ">=1.2.3,<2.0.0"

    def test_star_dot_star(self):
        result = normalize_constraint("1.*", "npm")
        assert result == ">=1.0.0,<2.0.0"

    def test_rust_like_version(self):
        result = normalize_constraint("0.8", "crates")
        assert result.startswith(">=")

    def test_unknown_format_returns_raw(self):
        assert normalize_constraint("totally-unknown-format", "pypi") == "totally-unknown-format"


class TestNormalizePip:
    def test_tilde(self):
        assert _normalize_pip("~=1.2") == ">=1.2,<2.0.0"

    def test_not_equal(self):
        assert _normalize_pip("!=2.0") == "!=2.0"

    def test_comparison_ops(self):
        assert _normalize_pip(">=1.0") == ">=1.0"
        assert _normalize_pip("<=2.0") == "<=2.0"
        assert _normalize_pip(">1.5") == ">1.5"
        assert _normalize_pip("<3.0") == "<3.0"
        assert _normalize_pip("==2.0.0") == "==2.0.0"

    def test_bare_equal(self):
        assert _normalize_pip("=1.2.3") == "==1.2.3"

    def test_dot_star(self):
        assert _normalize_pip("1.*") == ">=1.0.0,<2.0.0"

    def test_comma_separated(self):
        result = _normalize_pip(">=1.0,<2.0")
        assert ">=" in result
        assert "<" in result

    def test_none_on_unrecognized(self):
        assert _normalize_pip("something-weird") is None


class TestNormalizeNpm:
    def test_skips_non_target_ecosystem(self):
        assert _normalize_npm("^1.0", "pypi") is None

    def test_caret(self):
        result = _normalize_npm("^1.2.3", "npm")
        assert result == ">=1.2.3,<2.0.0"

    def test_tilde(self):
        result = _normalize_npm("~1.2.3", "npm")
        assert result == ">=1.2.3,<1.3.0"

    def test_bare_version_npm(self):
        result = _normalize_npm("1.2.3", "npm")
        assert result == ">=1.2.3"

    def test_bare_version_crates(self):
        result = _normalize_npm("0.5.0", "crates")
        assert result == ">=0.5.0,<0.6.0"

    def test_comparison_ops(self):
        assert _normalize_npm(">=1.0", "npm") == ">=1.0"
        assert _normalize_npm("<=2.0", "npm") == "<=2.0"
        assert _normalize_npm(">1.5", "npm") == ">1.5"
        assert _normalize_npm("<3.0", "npm") == "<3.0"
        assert _normalize_npm("==2.0", "npm") == "==2.0"
        assert _normalize_npm("!=1.0", "npm") == "!=1.0"

    def test_none_on_unrecognized(self):
        assert _normalize_npm("garbage", "npm") is None
