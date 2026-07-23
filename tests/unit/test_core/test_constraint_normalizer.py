# tests/unit/test_core/test_constraint_normalizer.py
import pytest

from backend.core.constraint_normalizer import (
    compare_versions_with_prerelease,
    normalize_constraint,
    normalize_prerelease_weight,
    normalize_version,
    parse_semver,
)
from backend.core.vers import VersSpec, parse


class TestNormalizeVersion:
    @pytest.mark.parametrize(
        ("input_ver", "expected"),
        [
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
        ],
    )
    def test_normalize(self, input_ver, expected):
        assert normalize_version(input_ver) == expected

    def test_ecosystem_passthrough(self):
        assert normalize_version("1.2.3", "npm") == "1.2.3"

    # --- Debian epoch ---

    def test_debian_epoch_stripped(self):
        assert normalize_version("2:1.2.3-4", "apt") == "2:1.2.3"

    def test_debian_epoch_no_revision(self):
        assert normalize_version("1:2.0.0", "apt") == "1:2.0.0"

    def test_debian_no_epoch(self):
        assert normalize_version("1.2.3-4", "apt") == "1.2.3"

    def test_debian_epoch_ignored_for_pypi(self):
        result = normalize_version("2:1.2.3-4", "pypi")
        assert isinstance(result, str)
        assert len(result) > 0

    # --- Conda glob ---

    def test_conda_glob_handled(self):
        assert normalize_version("1.2.*", "conda") == "1.2.0"

    def test_conda_star_suffix(self):
        assert normalize_version("3.9*", "conda") == "3.9.0"

    # --- RPM ---

    def test_rpm_evr_full(self):
        assert normalize_version("1:2.3.4-5.el8", "rpm") == "2.3.4"

    def test_rpm_no_epoch(self):
        assert normalize_version("2.3.4-5.el8", "rpm") == "2.3.4"

    def test_rpm_no_release(self):
        assert normalize_version("2.3.4", "rpm") == "2.3.4"

    # --- Go pseudo-versions ---

    def test_go_pseudo_version(self):
        assert normalize_version("v0.0.0-0.20230101000000-abcdefabcdef") == "0.0.0"

    def test_go_pseudo_version_no_v(self):
        assert normalize_version("1.2.3-0.20230101000000-abcdefabcdef") == "1.2.3"

    # --- Apt/apk revision strip ---

    def test_apt_revision_stripped(self):
        assert normalize_version("1.2.3-4ubuntu1", "apt") == "1.2.3"

    def test_apk_revision_stripped(self):
        assert normalize_version("2.0.0-r1", "apk") == "2.0.0"


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


class TestNormalizePrereleaseWeight:
    def test_stable_release(self):
        assert normalize_prerelease_weight("1.2.3") == 100

    def test_dev_release(self):
        assert normalize_prerelease_weight("1.0.0.dev1") == 0

    def test_alpha(self):
        assert normalize_prerelease_weight("1.0.0a1") == 1

    def test_beta(self):
        assert normalize_prerelease_weight("1.0.0b2") == 2

    def test_rc(self):
        assert normalize_prerelease_weight("1.0.0rc3") == 3

    def test_alpha_long(self):
        assert normalize_prerelease_weight("1.0.0alpha1") == 1

    def test_beta_long(self):
        assert normalize_prerelease_weight("1.0.0beta1") == 2

    def test_preview(self):
        assert normalize_prerelease_weight("1.0.0-preview.1") == 3

    def test_dev_dash(self):
        assert normalize_prerelease_weight("1.0.0-dev.1") == 0

    def test_npm_prerelease(self):
        assert normalize_prerelease_weight("1.0.0-alpha.1") == 1

    def test_npm_rc(self):
        assert normalize_prerelease_weight("1.0.0-rc.1") == 3

    def test_v_prefix(self):
        assert normalize_prerelease_weight("v2.0.0") == 100

    def test_empty_returns_100(self):
        assert normalize_prerelease_weight("") == 100

    def test_epoch_stripped(self):
        assert normalize_prerelease_weight("1:1.0.0") == 100

    def test_version_with_prerelease_contains(self):
        assert normalize_prerelease_weight("1.0.0.beta1") == 2

    def test_npm_semver_dev(self):
        assert normalize_prerelease_weight("3.0.0-dev") >= 0

    def test_standalone_a(self):
        assert normalize_prerelease_weight("1.0.0a1") == 1

    def test_standalone_b(self):
        assert normalize_prerelease_weight("1.0.0b1") == 2


class TestCompareVersionsWithPrerelease:
    def test_stable_equal(self):
        assert compare_versions_with_prerelease("1.0.0", "1.0.0") == 0

    def test_stable_greater(self):
        assert compare_versions_with_prerelease("2.0.0", "1.0.0") == 1

    def test_stable_less(self):
        assert compare_versions_with_prerelease("1.0.0", "2.0.0") == -1

    def test_dev_less_than_alpha(self):
        assert compare_versions_with_prerelease("1.0.0.dev1", "1.0.0a1") == -1

    def test_alpha_less_than_beta(self):
        assert compare_versions_with_prerelease("1.0.0a1", "1.0.0b1") == -1

    def test_beta_less_than_rc(self):
        assert compare_versions_with_prerelease("1.0.0b1", "1.0.0rc1") == -1

    def test_rc_less_than_stable(self):
        assert compare_versions_with_prerelease("1.0.0rc1", "1.0.0") == -1

    def test_dev_less_than_stable(self):
        assert compare_versions_with_prerelease("1.0.0.dev1", "1.0.0") == -1

    def test_same_phase_compare(self):
        assert compare_versions_with_prerelease("1.0.0a1", "1.0.0a2") == -1

    def test_invalid_versions_fallback(self):
        result = compare_versions_with_prerelease("not-a-version", "also-not")
        assert isinstance(result, int)

    def test_invalid_vs_valid(self):
        result = compare_versions_with_prerelease("abc", "1.0.0")
        assert isinstance(result, int)

    def test_npm_prerelease_ordering(self):
        assert compare_versions_with_prerelease("1.0.0-alpha.1", "1.0.0") == -1
        assert compare_versions_with_prerelease("1.0.0-alpha.1", "1.0.0-beta.1") == -1
