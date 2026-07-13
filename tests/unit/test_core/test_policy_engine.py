"""Tests for backend.core.policy_engine — all 10 policy rule types."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.policy_engine import (
    load_policy,
    check_policy,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_lock():
    return {
        "packages": {
            "flask": {
                "resolved_version": "2.3.0",
                "direct": True,
                "license": "BSD-3-Clause",
                "vendor": "pallets",
            },
            "requests": {
                "resolved_version": "2.31.0",
                "direct": True,
                "license": "Apache-2.0",
                "vendor": "psf",
            },
            "click": {
                "resolved_version": "8.1.7",
                "direct": False,
                "license": "BSD-3-Clause",
                "vendor": "pallets",
                "original_constraint": "*",
            },
        },
    }


@pytest.fixture
def deprecated_lock(clean_lock):
    clean_lock["packages"]["flask"]["deprecated"] = True
    return clean_lock


@pytest.fixture
def yanked_lock(clean_lock):
    clean_lock["packages"]["flask"]["yanked"] = True
    return clean_lock


@pytest.fixture
def gpl_lock(clean_lock):
    clean_lock["packages"]["flask"]["license"] = "gpl"
    return clean_lock


@pytest.fixture
def agpl_lock(clean_lock):
    clean_lock["packages"]["flask"]["license"] = "agpl"
    return clean_lock


@pytest.fixture
def vuln_lock():
    return {
        "packages": {
            "flask": {
                "resolved_version": "2.3.0",
                "vulnerabilities": [
                    {"id": "CVE-001", "severity": "HIGH"},
                    {"id": "CVE-002", "severity": "CRITICAL"},
                ],
            },
            "requests": {
                "resolved_version": "2.31.0",
                "vulnerabilities": [
                    {"id": "CVE-003", "severity": "CRITICAL"},
                ],
            },
        },
    }


@pytest.fixture
def unpinned_transitives_lock(clean_lock):
    clean_lock["packages"]["click"]["original_constraint"] = ">=8.0"
    return clean_lock


@pytest.fixture
def allowed_licenses_policy():
    return {"policies": [{"rule": "allowed-licenses", "licenses": ["mit", "apache-2.0"]}]}


@pytest.fixture
def blocked_packages_policy():
    return {"policies": [{"rule": "blocked-packages", "packages": ["flask"]}]}


@pytest.fixture
def require_vendor_lock_no_vendor(clean_lock):
    del clean_lock["packages"]["flask"]["vendor"]
    return clean_lock


@pytest.fixture
def no_rules_policy():
    return {"policies": []}


# ---------------------------------------------------------------------------
# load_policy
# ---------------------------------------------------------------------------


class TestLoadPolicy:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="Policy file not found"):
            load_policy("/nonexistent/policy.yaml")

    def test_missing_policies_key(self, tmp_path: Path):
        f = tmp_path / "bad.yaml"
        f.write_text("rules: []")
        with pytest.raises(ValueError, match="top-level 'policies' list"):
            load_policy(f)

    def test_policies_not_a_list(self, tmp_path: Path):
        f = tmp_path / "bad.yaml"
        f.write_text("policies: not-a-list")
        with pytest.raises(ValueError, match="'policies' must be a list"):
            load_policy(f)

    def test_entry_missing_rule_key(self, tmp_path: Path):
        f = tmp_path / "bad.yaml"
        f.write_text("policies:\n  - severity: error\n")
        with pytest.raises(ValueError, match="must have a 'rule' key"):
            load_policy(f)

    def test_unknown_rule(self, tmp_path: Path):
        f = tmp_path / "bad.yaml"
        f.write_text("policies:\n  - rule: unknown-rule\n")
        with pytest.raises(ValueError, match="unknown rule"):
            load_policy(f)

    def test_invalid_severity(self, tmp_path: Path):
        f = tmp_path / "bad.yaml"
        f.write_text("policies:\n  - rule: no-deprecated\n    severity: critical\n")
        with pytest.raises(ValueError, match="severity must be"):
            load_policy(f)

    def test_valid_policy(self, tmp_path: Path):
        f = tmp_path / "good.yaml"
        f.write_text(
            "policies:\n  - rule: no-deprecated\n  - rule: no-gpl\n    severity: warning\n"
        )
        result = load_policy(f)
        assert len(result["policies"]) == 2
        assert result["policies"][0]["rule"] == "no-deprecated"
        assert result["policies"][1]["severity"] == "warning"


# ---------------------------------------------------------------------------
# check_policy — no violations
# ---------------------------------------------------------------------------


class TestCheckPolicyNoViolations:
    def test_empty_policy_list(self, clean_lock):
        assert check_policy(clean_lock, {"policies": []}) == []

    def test_clean_lock_no_deprecated(self, clean_lock):
        policy = {"policies": [{"rule": "no-deprecated"}]}
        assert check_policy(clean_lock, policy) == []

    def test_clean_lock_no_yanked(self, clean_lock):
        policy = {"policies": [{"rule": "no-yanked"}]}
        assert check_policy(clean_lock, policy) == []

    def test_no_gpl_clean(self, clean_lock):
        policy = {"policies": [{"rule": "no-gpl"}]}
        assert check_policy(clean_lock, policy) == []

    def test_no_agpl_clean(self, clean_lock):
        policy = {"policies": [{"rule": "no-agpl"}]}
        assert check_policy(clean_lock, policy) == []

    def test_max_vulns_under(self, vuln_lock):
        policy = {"policies": [{"rule": "max-vulnerabilities", "max": 10}]}
        assert check_policy(vuln_lock, policy) == []

    def test_max_critical_under(self, vuln_lock):
        policy = {"policies": [{"rule": "max-critical-vulns", "max": 5}]}
        assert check_policy(vuln_lock, policy) == []

    def test_must_pin_transitives_clean(self, clean_lock):
        policy = {"policies": [{"rule": "must-pin-transitives"}]}
        assert check_policy(clean_lock, policy) == []

    def test_allowed_licenses_all_match(self, clean_lock):
        policy = {
            "policies": [{"rule": "allowed-licenses", "licenses": ["bsd-3-clause", "apache-2.0"]}]
        }
        assert check_policy(clean_lock, policy) == []

    def test_blocked_packages_none_present(self, clean_lock):
        policy = {"policies": [{"rule": "blocked-packages", "packages": ["evil"]}]}
        assert check_policy(clean_lock, policy) == []

    def test_require_vendor_has_vendor(self, clean_lock):
        policy = {"policies": [{"rule": "require-vendor"}]}
        assert check_policy(clean_lock, policy) == []


# ---------------------------------------------------------------------------
# check_policy — with violations
# ---------------------------------------------------------------------------


class TestCheckNoDeprecated:
    def test_deprecated_detected(self, deprecated_lock):
        policy = {"policies": [{"rule": "no-deprecated"}]}
        violations = check_policy(deprecated_lock, policy)
        assert len(violations) == 1
        v = violations[0]
        assert v["rule"] == "no-deprecated"
        assert v["package"] == "flask"
        assert "deprecated" in v["message"]

    def test_deprecated_default_severity_is_error(self, deprecated_lock):
        policy = {"policies": [{"rule": "no-deprecated"}]}
        violations = check_policy(deprecated_lock, policy)
        assert violations[0]["severity"] == "error"

    def test_deprecated_custom_severity(self, deprecated_lock):
        policy = {"policies": [{"rule": "no-deprecated", "severity": "warning"}]}
        violations = check_policy(deprecated_lock, policy)
        assert violations[0]["severity"] == "warning"


class TestCheckNoYanked:
    def test_yanked_detected(self, yanked_lock):
        policy = {"policies": [{"rule": "no-yanked"}]}
        violations = check_policy(yanked_lock, policy)
        assert len(violations) == 1
        assert violations[0]["rule"] == "no-yanked"
        assert violations[0]["package"] == "flask"
        assert "yanked" in violations[0]["message"]


class TestCheckNoGPL:
    def test_gpl_detected(self, gpl_lock):
        policy = {"policies": [{"rule": "no-gpl"}]}
        violations = check_policy(gpl_lock, policy)
        assert len(violations) == 1
        assert violations[0]["rule"] == "no-gpl"
        assert violations[0]["package"] == "flask"
        assert "GPL" in violations[0]["message"]

    def test_gpl_skips_mit(self, clean_lock):
        policy = {"policies": [{"rule": "no-gpl"}]}
        assert check_policy(clean_lock, policy) == []

    def test_gpl_skips_no_license(self, clean_lock):
        clean_lock["packages"]["flask"]["license"] = None
        policy = {"policies": [{"rule": "no-gpl"}]}
        assert check_policy(clean_lock, policy) == []


class TestCheckNoAGPL:
    def test_agpl_detected(self, agpl_lock):
        policy = {"policies": [{"rule": "no-agpl"}]}
        violations = check_policy(agpl_lock, policy)
        assert len(violations) == 1
        assert violations[0]["rule"] == "no-agpl"
        assert violations[0]["package"] == "flask"
        assert "AGPL" in violations[0]["message"]

    def test_agpl_not_gpl(self, gpl_lock):
        policy = {"policies": [{"rule": "no-agpl"}]}
        violations = check_policy(gpl_lock, policy)
        assert len(violations) == 0


class TestCheckMaxVulnerabilities:
    def test_exceeded(self, vuln_lock):
        policy = {"policies": [{"rule": "max-vulnerabilities", "max": 1, "severity": "error"}]}
        violations = check_policy(vuln_lock, policy)
        assert len(violations) == 1
        assert violations[0]["rule"] == "max-vulnerabilities"
        assert "3" in violations[0]["message"]
        assert violations[0]["severity"] == "error"

    def test_equal_to_max_is_okay(self, vuln_lock):
        policy = {"policies": [{"rule": "max-vulnerabilities", "max": 3}]}
        assert check_policy(vuln_lock, policy) == []


class TestCheckMaxCriticalVulns:
    def test_exceeded(self, vuln_lock):
        policy = {"policies": [{"rule": "max-critical-vulns", "max": 1}]}
        violations = check_policy(vuln_lock, policy)
        assert len(violations) == 1
        assert violations[0]["rule"] == "max-critical-vulns"
        assert "2" in violations[0]["message"]

    def test_equal_to_max_is_okay(self, vuln_lock):
        policy = {"policies": [{"rule": "max-critical-vulns", "max": 2}]}
        assert check_policy(vuln_lock, policy) == []

    def test_no_vulnerabilities_key(self, clean_lock):
        policy = {"policies": [{"rule": "max-critical-vulns", "max": 0}]}
        assert check_policy(clean_lock, policy) == []


class TestCheckMustPinTransitives:
    def test_unpinned_detected(self, unpinned_transitives_lock):
        policy = {"policies": [{"rule": "must-pin-transitives"}]}
        violations = check_policy(unpinned_transitives_lock, policy)
        assert len(violations) == 1
        assert violations[0]["rule"] == "must-pin-transitives"
        assert violations[0]["package"] == "click"
        assert "unpinned" in violations[0]["message"]

    def test_direct_deps_ignored(self, unpinned_transitives_lock):
        unpinned_transitives_lock["packages"]["flask"]["direct"] = True
        unpinned_transitives_lock["packages"]["flask"]["original_constraint"] = ">=2.0"
        policy = {"policies": [{"rule": "must-pin-transitives"}]}
        violations = check_policy(unpinned_transitives_lock, policy)
        flask_violations = [v for v in violations if v["package"] == "flask"]
        assert len(flask_violations) == 0


class TestCheckAllowedLicenses:
    def test_unapproved_license(self, clean_lock):
        policy = {"policies": [{"rule": "allowed-licenses", "licenses": ["mit"]}]}
        violations = check_policy(clean_lock, policy)
        assert len(violations) == 3
        assert all(v["rule"] == "allowed-licenses" for v in violations)

    def test_missing_license_reported(self, clean_lock):
        clean_lock["packages"]["flask"]["license"] = None
        policy = {"policies": [{"rule": "allowed-licenses", "licenses": ["mit", "apache-2.0"]}]}
        violations = check_policy(clean_lock, policy)
        assert len(violations) == 2
        assert any("no license info" in v["message"].lower() for v in violations)

    def test_all_allowed(self, clean_lock):
        policy = {
            "policies": [{"rule": "allowed-licenses", "licenses": ["bsd-3-clause", "apache-2.0"]}]
        }
        assert check_policy(clean_lock, policy) == []


class TestCheckBlockedPackages:
    def test_blocked_detected(self, clean_lock):
        policy = {"policies": [{"rule": "blocked-packages", "packages": ["flask"]}]}
        violations = check_policy(clean_lock, policy)
        assert len(violations) == 1
        assert violations[0]["rule"] == "blocked-packages"
        assert violations[0]["package"] == "flask"
        assert "Blocked package" in violations[0]["message"]

    def test_multiple_blocked(self, clean_lock):
        policy = {"policies": [{"rule": "blocked-packages", "packages": ["flask", "requests"]}]}
        violations = check_policy(clean_lock, policy)
        assert len(violations) == 2

    def test_no_match(self, clean_lock):
        policy = {"policies": [{"rule": "blocked-packages", "packages": ["nonexistent"]}]}
        assert check_policy(clean_lock, policy) == []


class TestCheckRequireVendor:
    def test_missing_vendor(self, require_vendor_lock_no_vendor):
        policy = {"policies": [{"rule": "require-vendor"}]}
        violations = check_policy(require_vendor_lock_no_vendor, policy)
        assert len(violations) == 1
        assert violations[0]["rule"] == "require-vendor"
        assert violations[0]["package"] == "flask"
        assert "vendor" in violations[0]["message"].lower()

    def test_has_vendor(self, clean_lock):
        policy = {"policies": [{"rule": "require-vendor"}]}
        assert check_policy(clean_lock, policy) == []

    def test_indirect_deps_ignored(self, require_vendor_lock_no_vendor):
        """require-vendor only checks direct deps."""
        del require_vendor_lock_no_vendor["packages"]["flask"]["direct"]
        policy = {"policies": [{"rule": "require-vendor"}]}
        assert check_policy(require_vendor_lock_no_vendor, policy) == []


# ---------------------------------------------------------------------------
# check_policy — multiple rules
# ---------------------------------------------------------------------------


class TestMultipleRules:
    def test_multiple_violations_across_rules(self, deprecated_lock):
        policy = {
            "policies": [
                {"rule": "no-deprecated"},
                {"rule": "no-yanked"},
            ]
        }
        deprecated_lock["packages"]["requests"]["yanked"] = True
        violations = check_policy(deprecated_lock, policy)
        assert len(violations) == 2
        rules = {v["rule"] for v in violations}
        assert rules == {"no-deprecated", "no-yanked"}

    def test_severity_per_entry(self, deprecated_lock):
        policy = {
            "policies": [
                {"rule": "no-deprecated", "severity": "warning"},
                {"rule": "blocked-packages", "packages": ["flask"]},
            ]
        }
        violations = check_policy(deprecated_lock, policy)
        sevs = {v["severity"] for v in violations}
        assert sevs == {"warning", "error"}

    def test_no_rules(self, clean_lock):
        assert check_policy(clean_lock, {"policies": []}) == []


# ---------------------------------------------------------------------------
# check_policy — edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_packages(self):
        lock = {"packages": {}}
        policy = {"policies": [{"rule": "no-deprecated"}]}
        assert check_policy(lock, policy) == []

    def test_lock_without_packages_key(self):
        policy = {"policies": [{"rule": "no-deprecated"}]}
        assert check_policy({}, policy) == []

    def test_allowed_licenses_empty_licenses_list(self, clean_lock):
        policy = {"policies": [{"rule": "allowed-licenses", "licenses": []}]}
        violations = check_policy(clean_lock, policy)
        assert len(violations) == 3
