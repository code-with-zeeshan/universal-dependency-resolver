"""Unit tests for cli/commands/sbom.py."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def sample_lock_data():
    return {
        "version": "2.1",
        "packages": {
            "requests": {
                "ecosystem": "pypi",
                "resolved_version": "2.31.0",
                "license": "Apache-2.0",
                "depends_on": {"urllib3": {}, "chardet": {}},
            },
            "urllib3": {
                "ecosystem": "pypi",
                "resolved_version": "2.0.7",
                "depends_on": {},
            },
            "chardet": {
                "ecosystem": "pypi",
                "resolved_version": "5.2.0",
                "depends_on": {},
            },
        },
    }


@pytest.fixture
def sample_lock_data_with_integrity():
    return {
        "version": "2.1",
        "packages": {
            "requests": {
                "ecosystem": "pypi",
                "resolved_version": "2.31.0",
                "integrity": {"algorithm": "sha256", "value": "abc123"},
                "depends_on": {},
            },
        },
    }


class TestBuildSpdx:
    def test_basic_spdx_structure(self, sample_lock_data):
        from backend.cli.commands.sbom import _build_spdx

        lock_path = MagicMock()
        lock_path.name = "udr.lock"
        result = _build_spdx(sample_lock_data, lock_path)

        assert result["spdxVersion"] == "SPDX-2.3"
        assert result["dataLicense"] == "CC0-1.0"
        assert result["SPDXID"] == "SPDXRef-DOCUMENT"
        assert "creationInfo" in result
        assert "Tool: universal-dependency-resolver" in result["creationInfo"]["creators"]

    def test_spdx_packages(self, sample_lock_data):
        from backend.cli.commands.sbom import _build_spdx

        lock_path = MagicMock()
        lock_path.name = "udr.lock"
        result = _build_spdx(sample_lock_data, lock_path)

        pkgs = result["packages"]
        pkg_names = {p["name"] for p in pkgs}
        assert pkg_names == {"requests", "urllib3", "chardet"}
        for pkg in pkgs:
            assert "SPDXID" in pkg
            assert pkg["SPDXID"].startswith("SPDXRef-")
            assert pkg["supplier"] == "NOASSERTION"
            if pkg["name"] == "requests":
                assert pkg["versionInfo"] == "2.31.0"
                assert pkg["licenseConcluded"] == "Apache-2.0"
            else:
                assert pkg["licenseConcluded"] == "NOASSERTION"

    def test_spdx_relationships(self, sample_lock_data):
        from backend.cli.commands.sbom import _build_spdx

        lock_path = MagicMock()
        lock_path.name = "udr.lock"
        result = _build_spdx(sample_lock_data, lock_path)

        rels = result["relationships"]
        assert len(rels) == 2
        rel_types = {r["relationshipType"] for r in rels}
        assert rel_types == {"DEPENDS_ON"}
        request_deps = [r for r in rels if r["spdxElementId"] == "SPDXRef-requests"]
        assert len(request_deps) == 2

    def test_spdx_integrity_checksums(self, sample_lock_data_with_integrity):
        from backend.cli.commands.sbom import _build_spdx

        lock_path = MagicMock()
        lock_path.name = "udr.lock"
        result = _build_spdx(sample_lock_data_with_integrity, lock_path)

        pkgs = result["packages"]
        requests_pkg = next(p for p in pkgs if p["name"] == "requests")
        assert "checksums" in requests_pkg
        assert requests_pkg["checksums"][0]["algorithm"] == "sha256"
        assert requests_pkg["checksums"][0]["value"] == "abc123"

    def test_spdx_empty_packages(self):
        from backend.cli.commands.sbom import _build_spdx

        lock_path = MagicMock()
        lock_path.name = "empty.lock"
        result = _build_spdx({"packages": {}}, lock_path)

        assert result["packages"] == []
        assert result["relationships"] == []

    def test_spdx_name_includes_lock_filename(self, sample_lock_data):
        from backend.cli.commands.sbom import _build_spdx

        lock_path = MagicMock()
        lock_path.name = "udr-backend.lock"
        result = _build_spdx(sample_lock_data, lock_path)

        assert "udr-backend.lock" in result["name"]


class TestBuildCycloneDx:
    def test_basic_cyclonedx_structure(self, sample_lock_data):
        from backend.cli.commands.sbom import _build_cyclonedx

        result = _build_cyclonedx(sample_lock_data)

        assert result["bomFormat"] == "CycloneDX"
        assert result["specVersion"] == "1.5"
        assert result["version"] == 1
        assert "tools" in result["metadata"]

    def test_cyclonedx_components(self, sample_lock_data):
        from backend.cli.commands.sbom import _build_cyclonedx

        result = _build_cyclonedx(sample_lock_data)

        comps = result["components"]
        comp_names = {c["name"] for c in comps}
        assert comp_names == {"requests", "urllib3", "chardet"}
        for comp in comps:
            assert comp["type"] == "library"
            assert "purl" in comp
            assert comp["purl"].startswith("pkg:pypi/")
            if comp["name"] == "requests":
                assert comp["version"] == "2.31.0"
                assert "licenses" in comp
                assert comp["licenses"][0]["license"]["id"] == "Apache-2.0"

    def test_cyclonedx_dependencies(self, sample_lock_data):
        from backend.cli.commands.sbom import _build_cyclonedx

        result = _build_cyclonedx(sample_lock_data)

        deps = result["dependencies"]
        assert len(deps) == 1
        assert "pkg:pypi/requests@2.31.0" in deps[0]["ref"]
        assert len(deps[0]["dependsOn"]) == 2

    def test_cyclonedx_empty_packages(self):
        from backend.cli.commands.sbom import _build_cyclonedx

        result = _build_cyclonedx({"packages": {}})

        assert result["components"] == []
        assert result["dependencies"] == []

    def test_cyclonedx_handles_missing_license(self):
        from backend.cli.commands.sbom import _build_cyclonedx

        data = {
            "packages": {
                "nolicense": {
                    "ecosystem": "pypi",
                    "resolved_version": "1.0.0",
                    "depends_on": {},
                },
            },
        }
        result = _build_cyclonedx(data)
        comp = result["components"][0]
        assert "licenses" not in comp

    def test_cyclonedx_different_ecosystem_purl(self):
        from backend.cli.commands.sbom import _build_cyclonedx

        data = {
            "packages": {
                "express": {
                    "ecosystem": "npm",
                    "resolved_version": "4.18.2",
                    "depends_on": {},
                },
            },
        }
        result = _build_cyclonedx(data)
        comp = result["components"][0]
        assert comp["purl"].startswith("pkg:npm/")


class TestCmdSbom:
    def test_no_lock_file_exits(self):
        with patch("pathlib.Path.is_file", return_value=False):
            with pytest.raises(SystemExit):
                args = MagicMock()
                args.directory = "/tmp"
                args.workspace = None
                args.lock_file = None
                from backend.cli.commands.sbom import cmd_sbom

                cmd_sbom(args)

    def test_lock_file_exists_calls_builders(self):
        mock_lock_data = {
            "packages": {
                "requests": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.31.0",
                    "depends_on": {},
                },
            },
        }
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.sbom._read_lock_file", return_value=mock_lock_data):
                with patch("backend.cli.commands.sbom._build_cyclonedx") as mock_cdx:
                    mock_cdx.return_value = {"bomFormat": "CycloneDX"}
                    args = MagicMock()
                    args.directory = "/tmp"
                    args.workspace = None
                    args.lock_file = None
                    args.format = "cyclonedx"
                    args.output = None

                    with pytest.raises(SystemExit):
                        from backend.cli.commands.sbom import cmd_sbom

                        cmd_sbom(args)

                    mock_cdx.assert_called_once()

    def test_spdx_format_selection(self):
        mock_lock_data = {
            "packages": {
                "requests": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.31.0",
                    "depends_on": {},
                },
            },
        }
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.sbom._read_lock_file", return_value=mock_lock_data):
                with patch("backend.cli.commands.sbom._build_spdx") as mock_spdx:
                    mock_spdx.return_value = {"spdxVersion": "SPDX-2.3"}
                    args = MagicMock()
                    args.directory = "/tmp"
                    args.workspace = None
                    args.lock_file = None
                    args.format = "spdx"
                    args.output = None

                    with pytest.raises(SystemExit):
                        from backend.cli.commands.sbom import cmd_sbom

                        cmd_sbom(args)

                    mock_spdx.assert_called_once()

    def test_output_writes_to_file(self, tmp_path):
        mock_lock_data = {
            "packages": {
                "requests": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.31.0",
                    "depends_on": {},
                },
            },
        }
        output_path = tmp_path / "out.json"
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("backend.cli.commands.sbom._read_lock_file", return_value=mock_lock_data):
                with patch("backend.cli.commands.sbom._build_cyclonedx") as mock_cdx:
                    mock_cdx.return_value = {"bomFormat": "CycloneDX", "components": []}
                    args = MagicMock()
                    args.directory = str(tmp_path)
                    args.workspace = None
                    args.lock_file = None
                    args.format = "cyclonedx"
                    args.output = str(output_path)

                    with pytest.raises(SystemExit):
                        from backend.cli.commands.sbom import cmd_sbom

                        cmd_sbom(args)

                    assert output_path.is_file()
                    content = json.loads(output_path.read_text())
                    assert content["bomFormat"] == "CycloneDX"
