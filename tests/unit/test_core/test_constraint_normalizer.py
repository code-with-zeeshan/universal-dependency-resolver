# tests/unit/test_core/test_constraint_normalizer.py
import pytest

from backend.core.constraint_normalizer import (
    normalize_constraint,
    normalize_version,
    parse_semver,
)
from backend.core.vers import VersSpec, parse


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

    # --- go modules ---

    def test_go_v_prefix(self):
        result = normalize_constraint("v1.2.3", "gomodules")
        assert result == ">=1.2.3"

    def test_go_pseudo_version(self):
        result = normalize_constraint("v0.0.0-20230101000000-abc12345", "gomodules")
        assert result == ">=0.0.0-20230101000000-abc12345"

    # --- hex / elixir ---

    def test_hex_pessimistic(self):
        result = normalize_constraint("~> 1.2", "hex")
        assert result == ">=1.2,<1.3.0"

    def test_hex_pessimistic_major(self):
        result = normalize_constraint("~> 1", "hex")
        assert result == ">=1.0.0,<2.0.0"


class TestVersSpec:
    """Direct tests for the VersSpec dataclass and parsers."""

    def test_from_pip(self):
        s = VersSpec.parse(">=1.0,<2.0", "pypi")
        assert s.pep508 == ">=1.0,<2.0"
        assert s.ecosystem == "pypi"
        assert s.raw == ">=1.0,<2.0"

    def test_from_npm_caret(self):
        s = VersSpec.parse("^1.2.3", "npm")
        assert s.pep508 == ">=1.2.3,<2.0.0"

    def test_from_crates_bare(self):
        s = VersSpec.parse("0.5.0", "crates")
        assert s.pep508 == ">=0.5.0,<0.6.0"

    def test_from_rubygems(self):
        s = VersSpec.parse("~> 1.2", "rubygems")
        assert s.pep508 == ">=1.2,<2.0.0"

    def test_from_hex(self):
        s = VersSpec.parse("~> 1.2", "hex")
        assert s.pep508 == ">=1.2,<1.3.0"

    def test_from_go(self):
        s = VersSpec.parse("v1.2.3", "gomodules")
        assert s.pep508 == ">=1.2.3"

    def test_wildcard(self):
        s = VersSpec.parse("*", "npm")
        assert s.pep508 == "*"

    def test_to_specifier_set_wildcard(self):
        s = VersSpec.parse("*", "npm")
        assert s.to_specifier_set() is None

    def test_to_specifier_set_normal(self):
        s = VersSpec.parse(">=1.0,<2.0", "pypi")
        spec = s.to_specifier_set()
        assert spec is not None
        from packaging.version import parse as parse_version
        assert parse_version("1.5.0") in spec
        assert parse_version("2.0.0") not in spec

    def test_is_compatible(self):
        s = VersSpec.parse("^1.2.0", "npm")
        assert s.is_compatible("1.5.0")
        assert not s.is_compatible("2.0.0")
        assert not s.is_compatible("0.9.0")

    def test_is_compatible_wildcard(self):
        s = VersSpec.parse("*", "npm")
        assert s.is_compatible("anything")

    def test_str(self):
        s = VersSpec.parse(">=1.0", "pypi")
        assert str(s) == ">=1.0"
        s2 = VersSpec.parse("*", "npm")
        assert str(s2) == "*"

    def test_shorthand_parse(self):
        s = parse("^1.0.0", "npm")
        assert s.pep508 == ">=1.0.0,<2.0.0"
