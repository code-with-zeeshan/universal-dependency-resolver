"""Integration tests for the CLI pipeline - end-to-end resolve/lock/install flow."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI = [sys.executable, "-m", "backend.cli"]

TEST_DIR = Path("/tmp/opencode/test-all-ecosystems")


def run_cli(*args, timeout=60):
    result = subprocess.run(
        CLI + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(TEST_DIR),
    )
    return result.stdout + result.stderr


class TestCLICommands:
    """Validate all CLI commands produce expected output."""

    def test_list_ecosystems(self):
        output = run_cli("list-ecosystems")
        assert "pypi" in output
        assert "npm" in output
        assert "crates" in output
        assert "pub" in output
        assert "16" in output or "Supported Ecosystems" in output

    def test_check_command(self):
        output = run_cli("check")
        assert "System Compatibility" in output
        assert "Linux" in output or "OS" in output
        assert "Python" in output

    def test_resolve_single_pypi(self):
        output = run_cli("resolve", "numpy", "--ecosystem", "pypi", timeout=90)
        assert "Resolved" in output
        assert "numpy" in output
        assert "pypi" in output

    def test_resolve_cross_ecosystem(self):
        output = run_cli("resolve", "fastapi@pypi", "express@npm", "--ecosystem", "pypi", timeout=90)
        assert "Resolved" in output
        assert "fastapi" in output
        assert "express" in output
        assert "npm" in output

    def test_resolve_with_constraint(self):
        output = run_cli("resolve", "fastapi@pypi", "--ecosystem", "pypi", timeout=90)
        assert "fastapi" in output
        assert "pypi" in output
        # Should pick latest available version
        assert "0." in output

    def test_lock_requirements_txt(self):
        output = run_cli("lock", "--dry-run", "--directory", str(TEST_DIR), "--manifest", "requirements.txt", timeout=120)
        assert "Resolved 8/8" in output or "Resolved" in output
        assert "flask" in output
        assert "django" in output
        assert "direct" in output

    def test_lock_pyproject_toml(self):
        output = run_cli("lock", "--dry-run", "--directory", str(TEST_DIR), "--manifest", "pyproject.toml", timeout=120)
        assert "fastapi" in output
        assert "pydantic" in output
        assert "direct" in output

    def test_graph_command(self):
        output = run_cli("graph", "numpy", "--ecosystem", "pypi", timeout=60)
        assert "Dependency Tree" in output
        assert "numpy" in output

    def test_install_dry_run(self):
        output = run_cli("install", "--directory", str(TEST_DIR), "--dry-run", "-e", "pypi", timeout=30)
        assert "Install Plan" in output
        assert "pip install" in output
        assert "dry run" in output


class TestPackageSpecParsing:
    """Validate package@ecosystem parsing."""

    def test_parse_spec(self):
        from backend.cli import _parse_package_spec
        name, eco = _parse_package_spec("numpy@conda")
        assert name == "numpy"
        assert eco == "conda"

    def test_default_ecosystem(self):
        from backend.cli import _parse_package_spec
        name, eco = _parse_package_spec("numpy")
        assert name == "numpy"
        assert eco == "pypi"

    def test_scoped_npm_package(self):
        from backend.cli import _parse_package_spec
        name, eco = _parse_package_spec("@angular/core@npm")
        assert name == "@angular/core"
        assert eco == "npm"


class TestNameNormalization:
    """Validate package name normalization across the pipeline."""

    def test_normalize_flask(self):
        from backend.core.utils import normalize_package_name
        assert normalize_package_name("Flask") == "flask"
        assert normalize_package_name("Django") == "django"

    def test_normalize_with_dashes(self):
        from backend.core.utils import normalize_package_name
        assert normalize_package_name("My-Package") in ("my-package", "my_package")

    def test_manifest_detector_normalization(self):
        from backend.manifest_detector import ManifestDetector
        detector = ManifestDetector(str(TEST_DIR))
        packages = [{"name": "Flask", "_ecosystem": "pypi", "version": ">=2.0"}]
        norm = detector.normalize(packages)
        assert len(norm) == 1
        assert norm[0]["name"] == "flask"


class TestEcosystemAliasing:
    """Validate cargo->crates, go->gomodules alias mapping."""

    def test_cargo_alias_in_detect(self):
        from backend.manifest_detector import ManifestDetector
        detector = ManifestDetector(str(TEST_DIR))
        manifests = detector.detect()
        names = [m["ecosystem"] for m in manifests]
        assert "crates" in names
        assert "cargo" not in names
        assert "gomodules" in names
        assert "go" not in names

    def test_cargo_alias_in_normalize(self):
        from backend.manifest_detector import ManifestDetector
        detector = ManifestDetector(str(TEST_DIR))
        packages = [{"name": "serde", "_ecosystem": "cargo"}]
        norm = detector.normalize(packages)
        assert norm[0]["ecosystem"] == "crates"


class TestConstraintNormalizer:
    """Validate constraint normalization for npm/crates/rubygems."""

    def test_npm_caret(self):
        from backend.core.constraint_normalizer import normalize_constraint
        result = normalize_constraint("^4.18.0", "npm")
        assert ">=4.18.0" in result
        assert "<5.0.0" in result or "<4.19" in result

    def test_crates_tilde(self):
        from backend.core.constraint_normalizer import normalize_constraint
        result = normalize_constraint("~1.2.3", "crates")
        assert ">=1.2.3" in result

    def test_rubygems_pessimistic(self):
        from backend.core.constraint_normalizer import normalize_constraint
        result = normalize_constraint("~> 3.0", "rubygems")
        assert result != "~> 3.0"

    def test_pep440_passthrough(self):
        from backend.core.constraint_normalizer import normalize_constraint
        result = normalize_constraint(">=2.0,<3.0", "pypi")
        assert result == ">=2.0,<3.0"


class TestInstallCommand:
    """Validate the install command generates correct commands."""

    def test_generate_pip_command(self):
        from backend.cli import _generate_install_command
        cmd = _generate_install_command("pypi", [("flask", "2.3.0"), ("django", "4.2")])
        assert "pip install" in cmd
        assert "flask==2.3.0" in cmd
        assert "django==4.2" in cmd

    def test_generate_npm_command(self):
        from backend.cli import _generate_install_command
        cmd = _generate_install_command("npm", [("express", "4.18.0")])
        assert "npm install" in cmd
        assert "express@4.18.0" in cmd

    def test_generate_unknown_ecosystem(self):
        from backend.cli import _generate_install_command
        cmd = _generate_install_command("nonexistent", [("pkg", "1.0")])
        assert cmd is None


class TestTransitiveResolution:
    """Validate transitive dependency resolution features."""

    def test_aggregator_to_resolver_input_includes_cross_eco(self):
        from backend.cli import _aggregator_to_resolver_input
        data = {
            "name": "test-pkg",
            "dependencies": {"pypi": {"all": []}},
            "versions": {"pypi": [{"version": "1.0.0"}]},
            "cross_ecosystem_deps": [{"dependency": "node-pkg", "target_ecosystem": "npm"}],
        }
        rinput = _aggregator_to_resolver_input(data, "pypi")
        assert "cross_ecosystem_deps" in rinput
        assert rinput["cross_ecosystem_deps"] == [{"dependency": "node-pkg", "target_ecosystem": "npm"}]
