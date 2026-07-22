"""Unit tests for api/routes/sbom.py (direct function tests)."""

import pytest

from backend.api.routes.sbom import _build_spdx, _build_cyclonedx


@pytest.fixture
def sample_lock_data():
    return {
        "packages": {
            "requests": {
                "ecosystem": "pypi",
                "resolved_version": "2.31.0",
                "license": "Apache-2.0",
                "depends_on": {"urllib3": {}},
            },
            "urllib3": {
                "ecosystem": "pypi",
                "resolved_version": "2.0.7",
                "depends_on": {},
            },
        },
    }


class TestAPISbomSpdx:
    def test_spdx_success(self, sample_lock_data):
        result = _build_spdx(sample_lock_data)
        assert result["spdxVersion"] == "SPDX-2.3"
        assert len(result["packages"]) == 2

    def test_spdx_includes_relationships(self, sample_lock_data):
        result = _build_spdx(sample_lock_data)
        assert len(result["relationships"]) == 1

    def test_spdx_handles_integrity(self):
        data = {
            "packages": {
                "foo": {
                    "ecosystem": "pypi",
                    "resolved_version": "1.0.0",
                    "integrity": {"algorithm": "sha256", "value": "abcdef"},
                    "depends_on": {},
                },
            },
        }
        result = _build_spdx(data)
        pkg = result["packages"][0]
        assert pkg["checksums"][0]["value"] == "abcdef"

    def test_spdx_empty_packages(self):
        result = _build_spdx({"packages": {}})
        assert result["packages"] == []

    def test_spdx_no_license_falls_back(self):
        data = {
            "packages": {
                "foo": {
                    "ecosystem": "pypi",
                    "resolved_version": "1.0.0",
                    "depends_on": {},
                },
            },
        }
        result = _build_spdx(data)
        assert result["packages"][0]["licenseConcluded"] == "NOASSERTION"


class TestAPISbomCycloneDx:
    def test_cyclonedx_success(self, sample_lock_data):
        result = _build_cyclonedx(sample_lock_data)
        assert result["bomFormat"] == "CycloneDX"
        assert len(result["components"]) == 2

    def test_cyclonedx_components_have_purl(self, sample_lock_data):
        result = _build_cyclonedx(sample_lock_data)
        for comp in result["components"]:
            assert "purl" in comp
            assert comp["purl"].startswith("pkg:pypi/")

    def test_cyclonedx_dependencies(self, sample_lock_data):
        result = _build_cyclonedx(sample_lock_data)
        assert len(result["dependencies"]) == 1
