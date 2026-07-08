"""Tests for backend.core.license_checker."""

from backend.core.license_checker import (
    check_license_compatibility,
    normalize_license,
)


class TestNormalizeLicense:
    def test_mit(self):
        assert normalize_license("MIT") == "MIT"

    def test_mit_lowercase(self):
        assert normalize_license("mit") == "MIT"

    def test_mit_with_license_suffix(self):
        assert normalize_license("MIT License") == "MIT"

    def test_apache_20(self):
        assert normalize_license("Apache 2.0") == "Apache-2.0"

    def test_apache_with_hyphen(self):
        assert normalize_license("Apache-2.0") == "Apache-2.0"

    def test_bsd_defaults_to_3_clause(self):
        assert normalize_license("BSD") == "BSD-3-Clause"

    def test_bsd_2_clause(self):
        assert normalize_license("BSD-2-Clause") == "BSD-2-Clause"

    def test_gpl_30(self):
        assert normalize_license("GPL 3.0") == "GPL-3.0-only"

    def test_lgpl_21(self):
        assert normalize_license("LGPL 2.1") == "LGPL-2.1-only"

    def test_mpl_20(self):
        assert normalize_license("MPL 2.0") == "MPL-2.0"

    def test_unlicense(self):
        assert normalize_license("Unlicense") == "Unlicense"

    def test_custom_string_preserved(self):
        assert normalize_license("Proprietary") == "Proprietary"

    def test_empty_string(self):
        assert normalize_license("") == ""

    def test_period_stripped(self):
        assert normalize_license("MIT.") == "MIT"

    def test_isc(self):
        assert normalize_license("ISC") == "ISC"

    def test_zlib(self):
        assert normalize_license("zlib/libpng") == "Zlib"

    def test_psf(self):
        assert normalize_license("PSF") == "PSF-2.0"

    def test_public_domain(self):
        assert normalize_license("public domain") == "Unlicense"

    def test_quoted_mit(self):
        assert normalize_license('"MIT"') == "MIT"


class TestCheckLicenseCompatibility:
    def test_all_permissive_allowed(self):
        pkg_licenses = {
            "requests": "Apache-2.0",
            "flask": "BSD-3-Clause",
            "click": "MIT",
        }
        results = check_license_compatibility(pkg_licenses)
        for name, r in results.items():
            assert r["status"] == "allowed", f"{name}: {r}"

    def test_gpl_denied(self):
        results = check_license_compatibility({"foo": "GPL-3.0-only"})
        assert results["foo"]["status"] == "denied"
        assert "copyleft" in results["foo"]["reason"]

    def test_lgpl_warning(self):
        results = check_license_compatibility({"bar": "LGPL-2.1-only"})
        assert results["bar"]["status"] == "warning"

    def test_mpl_warning(self):
        results = check_license_compatibility({"baz": "MPL-2.0"})
        assert results["baz"]["status"] == "warning"

    def test_unknown_license(self):
        results = check_license_compatibility({"qux": "Proprietary"})
        assert results["qux"]["status"] == "warning"

    def test_list_of_licenses_or(self):
        results = check_license_compatibility({"pkg": ["MIT", "GPL-3.0-only"]})
        assert results["pkg"]["status"] == "denied"

    def test_policy_override_allow_gpl(self):
        policy = {"permissive": "allow", "weak_copyleft": "allow", "strong_copyleft": "allow"}
        results = check_license_compatibility({"foo": "GPL-3.0-only"}, policy=policy)
        assert results["foo"]["status"] == "allowed"

    def test_policy_override_deny_all(self):
        policy = {
            "permissive": "deny",
            "weak_copyleft": "deny",
            "strong_copyleft": "deny",
            "unknown": "deny",
        }
        results = check_license_compatibility({"foo": "MIT"}, policy=policy)
        assert results["foo"]["status"] == "denied"

    def test_normalized_field_is_string_for_single_license(self):
        results = check_license_compatibility({"foo": "MIT"})
        assert isinstance(results["foo"]["normalized"], str)

    def test_normalized_field_is_list_for_multi_license(self):
        results = check_license_compatibility({"foo": ["MIT", "Apache-2.0"]})
        assert isinstance(results["foo"]["normalized"], list)

    def test_empty_packages(self):
        results = check_license_compatibility({})
        assert results == {}

    def test_mit_alias(self):
        results = check_license_compatibility({"x": "mit license"})
        assert results["x"]["normalized"] == "MIT"
        assert results["x"]["status"] == "allowed"

    def test_permissive_variants_allowed(self):
        variants = ["ISC", "Zlib", "Unlicense", "CC0-1.0", "BSL-1.0", "PostgreSQL"]
        results = check_license_compatibility({v: v for v in variants})
        for name, r in results.items():
            assert r["status"] == "allowed", f"{name}: {r}"
