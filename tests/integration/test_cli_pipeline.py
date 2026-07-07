"""Integration tests for the CLI pipeline - end-to-end resolve/lock/install flow.

Generates its own test manifests in a temporary directory so it's portable.
"""

import subprocess
import sys
from pathlib import Path

import pytest

CLI = [sys.executable, "-m", "backend.cli"]


def _create_manifests(base: Path) -> Path:
    """Generate test manifests under base/ and return the path."""
    base.mkdir(parents=True, exist_ok=True)

    (base / "requirements.txt").write_text(
        "Flask>=2.3,<4\nDjango>=4.2,<6\nnumpy>=1.24,<3\npandas>=2.0,<3\n"
        "scipy>=1.11,<2\nrequests>=2.28,<3\nbeautifulsoup4>=4.12,<5\nmatplotlib>=3.7,<4\n"
    )
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test-project"\nversion = "0.1.0"\n'
        "dependencies = [\n"
        '    "fastapi>=0.115.0,<0.137", "pydantic>=2.5.0,<3", "uvicorn>=0.24,<0.50",\n'
        '    "sqlalchemy>=2.0.23,<3", "alembic>=1.12,<2", "httpx>=0.27,<1",\n'
        '    "pytest>=8.0,<9", "ruff>=0.3.0,<1", "rich>=13.7,<14", "click>=8.1,<9",\n'
        "]\n"
    )

    (base / "conda").mkdir(exist_ok=True)
    (base / "conda" / "environment.yml").write_text(
        "name: test-conda\nchannels:\n  - conda-forge\n  - defaults\n"
        "dependencies:\n  - numpy>=1.24\n  - scipy>=1.11\n  - pandas>=2.0\n"
        "  - matplotlib>=3.7\n  - pip\n  - requests>=2.28\n  - httpx>=0.27\n"
    )

    (base / "dart").mkdir(exist_ok=True)
    (base / "dart" / "pubspec.yaml").write_text(
        "name: test_dart\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\n"
        "dependencies:\n  http: ^1.1.0\n  path: ^1.9.0\n  provider: ^6.1.0\n"
        "  riverpod: ^2.5.0\n  json_annotation: ^4.8.0\n"
    )

    (base / "go").mkdir(exist_ok=True)
    (base / "go" / "go.mod").write_text(
        "module test-go\ngo 1.21\nrequire (\n"
        "    github.com/spf13/cobra v1.8.0\n    k8s.io/klog/v2 v2.120.0\n"
        "    github.com/gorilla/mux v1.8.1\n    github.com/prometheus/client_golang v1.19.0\n"
        "    golang.org/x/sync v0.7.0\n)\n"
    )

    (base / "node").mkdir(exist_ok=True)
    (base / "node" / "package.json").write_text(
        '{"dependencies": {"express": "^4.18.0", "lodash": "^4.17.21", '
        '"axios": "^1.6.0", "react": "^18.2.0", "vue": "^3.4.0"}, '
        '"devDependencies": {"typescript": "^5.4.0", "eslint": "^8.56.0", "webpack": "^5.90.0"}}'
    )

    (base / "php").mkdir(exist_ok=True)
    (base / "php" / "composer.json").write_text(
        '{\n    "require": {\n'
        '        "laravel/framework": ">=10.0",\n        "phpunit/phpunit": ">=10.5",\n'
        '        "monolog/monolog": ">=3.5",\n        "guzzlehttp/guzzle": ">=7.8",\n'
        '        "doctrine/orm": ">=3.0",\n        "mockery/mockery": ">=1.6"\n    }\n}\n'
    )

    (base / "ruby").mkdir(exist_ok=True)
    (base / "ruby" / "Gemfile").write_text(
        'source "https://rubygems.org"\n'
        'gem "rails", ">= 7.0"\ngem "rspec", ">= 3.12"\n'
        'gem "devise", ">= 4.9"\ngem "sidekiq", ">= 7.2"\ngem "nokogiri", ">= 1.16"\n'
    )

    (base / "rust").mkdir(exist_ok=True)
    (base / "rust" / "Cargo.toml").write_text(
        '[package]\nname = "test-rust"\nversion = "0.1.0"\n'
        '[dependencies]\nserde = "1.0"\ntokio = "1.35"\nreqwest = "0.12"\n'
        'clap = "4.5"\nanyhow = "1.0"\nthiserror = "1.0"\n'
    )

    return base


@pytest.fixture(scope="session")
def test_dir(tmp_path_factory):
    return _create_manifests(tmp_path_factory.mktemp("test-ecosystems"))


def run_cli(*args, cwd=None, timeout=60):
    result = subprocess.run(
        CLI + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(cwd),
    )
    return result.stdout + result.stderr


class TestCLICommands:
    """Validate all CLI commands produce expected output."""

    def test_list_ecosystems(self, test_dir):
        output = run_cli("list-ecosystems", cwd=test_dir)
        assert "pypi" in output
        assert "npm" in output
        assert "crates" in output
        assert "pub" in output
        assert "16" in output or "Supported Ecosystems" in output

    def test_check_command(self, test_dir):
        output = run_cli("check", cwd=test_dir)
        assert "System Compatibility" in output
        assert "Linux" in output or "OS" in output
        assert "Python" in output

    def test_resolve_single_pypi(self, test_dir):
        output = run_cli("resolve", "numpy", "--ecosystem", "pypi", timeout=90, cwd=test_dir)
        assert "Resolved" in output
        assert "numpy" in output
        assert "pypi" in output

    def test_resolve_cross_ecosystem(self, test_dir):
        output = run_cli("resolve", "fastapi@pypi", "express@npm", "--ecosystem", "pypi", timeout=300, cwd=test_dir)
        assert "Resolved" in output
        assert "fastapi" in output
        assert "express" in output
        assert "npm" in output

    def test_resolve_with_constraint(self, test_dir):
        output = run_cli("resolve", "fastapi@pypi", "--ecosystem", "pypi", timeout=90, cwd=test_dir)
        assert "fastapi" in output
        assert "pypi" in output
        assert "0." in output

    def test_lock_requirements_txt(self, test_dir):
        output = run_cli("lock", "--dry-run", "--directory", str(test_dir), "--manifest", "requirements.txt", timeout=120, cwd=test_dir)
        assert "Resolved" in output
        assert "flask" in output
        assert "django" in output
        assert "direct" in output

    def test_lock_pyproject_toml(self, test_dir):
        output = run_cli("lock", "--dry-run", "--directory", str(test_dir), "--manifest", "pyproject.toml", timeout=120, cwd=test_dir)
        assert "fastapi" in output
        assert "pydantic" in output
        assert "direct" in output

    def test_graph_command(self, test_dir):
        output = run_cli("graph", "numpy", "--ecosystem", "pypi", timeout=60, cwd=test_dir)
        assert "Dependency Tree" in output
        assert "numpy" in output

    def test_install_dry_run(self, test_dir):
        output = run_cli("install", "--directory", str(test_dir), "--dry-run", "-e", "pypi", timeout=30, cwd=test_dir)
        assert "Install Plan" in output
        assert "pip install" in output
        assert "dry run" in output


class TestPackageSpecParsing:
    """Validate package@ecosystem parsing."""

    def test_parse_spec(self):
        from backend.cli import _parse_package_spec
        name, eco, constraint = _parse_package_spec("numpy@conda")
        assert name == "numpy"
        assert eco == "conda"
        assert constraint is None

    def test_default_ecosystem(self):
        from backend.cli import _parse_package_spec
        name, eco, constraint = _parse_package_spec("numpy")
        assert name == "numpy"
        assert eco == "pypi"
        assert constraint is None

    def test_scoped_npm_package(self):
        from backend.cli import _parse_package_spec
        name, eco, constraint = _parse_package_spec("@angular/core@npm")
        assert name == "@angular/core"
        assert eco == "npm"
        assert constraint is None


class TestNameNormalization:
    """Validate package name normalization across the pipeline."""

    def test_normalize_flask(self):
        from backend.core.utils import normalize_package_name
        assert normalize_package_name("Flask") == "flask"
        assert normalize_package_name("Django") == "django"

    def test_normalize_with_dashes(self):
        from backend.core.utils import normalize_package_name
        assert normalize_package_name("My-Package") in ("my-package", "my_package")

    def test_manifest_detector_normalization(self, test_dir):
        from backend.manifest_detector import ManifestDetector
        detector = ManifestDetector(str(test_dir))
        packages = [{"name": "Flask", "_ecosystem": "pypi", "version": ">=2.0"}]
        norm = detector.normalize(packages)
        assert len(norm) == 1
        assert norm[0]["name"] == "flask"


class TestEcosystemAliasing:
    """Validate cargo->crates, go->gomodules alias mapping."""

    def test_cargo_alias_in_detect(self, test_dir):
        from backend.manifest_detector import ManifestDetector
        detector = ManifestDetector(str(test_dir))
        manifests = detector.detect()
        names = [m["ecosystem"] for m in manifests]
        assert "crates" in names
        assert "cargo" not in names
        assert "gomodules" in names
        assert "go" not in names

    def test_cargo_alias_in_normalize(self, test_dir):
        from backend.manifest_detector import ManifestDetector
        detector = ManifestDetector(str(test_dir))
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
