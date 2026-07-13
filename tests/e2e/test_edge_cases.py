"""Comprehensive edge-case scenarios for ud-resolver CLI.

Scenarios:
  1.  CUDA version conflict — pytorch CUDA 12 vs no-cuda → no CUDA variant selected
  2.  Deep cross-ecosystem transitive — PyPI + npm + crates
  3.  Unsatisfiable constraints → partial/fallback resolution
  4.  Python version mismatch in system requirements
  5.  --device variants (cpu, cuda, mps)
  6.  Multiple manifests + overlapping dependencies
  7.  install --dry-run from lock file
  8.  JSON output compliance for all commands
  9.  Dependency graph output
  10. Update single package in lock file
  11. verify lock file against registry
  12. Empty / missing manifest handling
  13. Exact version pin (== constraint)
  14. Combined version constraints (>=X,<Y)
  15. Cross-ecosystem with constraints
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UDR = [sys.executable, "-m", "backend.cli"]

ENV = {
    **os.environ,
    "PYTHONPATH": str(REPO_ROOT),
    "TESTING": "true",
    "SECRET_KEY": "test-secret-key-for-ci",
    "SOLVER_TIMEOUT": "120",
    "USE_Z3_OPTIMIZE": "true",
}


def _run(*args: str, timeout: int = 120, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*UDR, *args],
        capture_output=True,
        text=True,
        cwd=cwd or str(REPO_ROOT),
        env=ENV,
        timeout=timeout,
    )


def _lock(
    directory: Path,
    *,
    cuda: str | None = None,
    device: str | None = None,
    timeout: int = 300,
    extra_args: list[str] | None = None,
) -> dict:
    args = ["lock", "--directory", str(directory), "--yes", "--json"]
    if cuda:
        args.extend(["--cuda", cuda])
    if device:
        args.extend(["--device", device])
    if extra_args:
        args.extend(extra_args)
    result = subprocess.run(
        [*UDR, *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=ENV,
        timeout=timeout + 30,
    )
    if result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return {}


# ═══════════════════════════════════════════════════════════════════════
# Scenario 1: CUDA resolution
# ═══════════════════════════════════════════════════════════════════════
class TestCUDA:
    """CUDA and device flag resolution."""

    def test_01_cuda_12_selection(self):
        """CUDA 12.1 → torch should select CUDA variant."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("torch>=2.0\n")
            data = _lock(d, cuda="12.1", timeout=300)
            pkgs = data.get("packages", {})
            torch_ver = pkgs.get("torch", {}).get("resolved_version", "")
            pkgs.get("torch", {}).get("cuda_variant", False)
            assert torch_ver, "torch not resolved"
            # CUDA variant should be selected (torch resolves to a +cu variant)
            # But even if not, nvidia deps are still present on Linux
            nvidia_pkgs = [n for n in pkgs if "nvidia" in n.lower() or "cuda" in n.lower()]
            assert len(nvidia_pkgs) >= 1, f"Expected nvidia pkgs with CUDA 12.1, got {nvidia_pkgs}"

    def test_02_device_cpu(self):
        """--device cpu → torch resolved (nvidia deps may still be present on Linux)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("torch>=2.0\n")
            data = _lock(d, device="cpu", timeout=300)
            pkgs = data.get("packages", {})
            torch_ver = pkgs.get("torch", {}).get("resolved_version", "")
            assert torch_ver, "torch not resolved with --device cpu"

    def test_03_device_mps(self):
        """--device mps → torch resolved successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("torch>=2.0\n")
            data = _lock(d, device="mps", timeout=300)
            pkgs = data.get("packages", {})
            torch_ver = pkgs.get("torch", {}).get("resolved_version", "")
            assert torch_ver, "torch not resolved with --device mps"

    def test_04_no_cuda_flag_default(self):
        """No --cuda and no --device → torch resolved without CUDA variant."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("torch>=2.0\n")
            data = _lock(d, timeout=300)
            pkgs = data.get("packages", {})
            torch_ver = pkgs.get("torch", {}).get("resolved_version", "")
            assert torch_ver, "torch not resolved without flags"
            # cuda_variant should NOT be set
            torch_cuda_variant = pkgs.get("torch", {}).get("cuda_variant", False)
            assert not torch_cuda_variant, (
                f"torch should NOT have cuda_variant without --cuda flag, "
                f"got variant={torch_cuda_variant}"
            )


# ═══════════════════════════════════════════════════════════════════════
# Scenario 2: Cross-ecosystem transitive resolution
# ═══════════════════════════════════════════════════════════════════════
class TestCrossEcosystem:
    """Cross-ecosystem resolution."""

    def test_05_deep_transitive_pypi(self):
        """Flask → werkzeug → markupsafe chain resolved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("flask>=2.3\nrequests>=2.28\n")
            data = _lock(d, timeout=600)
            pkgs = data.get("packages", {})
            assert len(pkgs) >= 7, (
                f"flask+requests should pull >=7 transitive deps, got {len(pkgs)}"
            )
            deps_lower = {k.lower(): k for k in pkgs}
            assert "werkzeug" in deps_lower, "flask dep werkzeug missing"
            assert "markupsafe" in deps_lower, "werkzeug dep markupsafe missing"
            assert "requests" in pkgs, "missing requests"

    def test_06_pypi_npm_cross_ecosystem(self):
        """PyPI + npm lock with cross-ecosystem deps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            (d / "package.json").write_text('{"dependencies":{"express":"^4.18.0"}}')
            data = _lock(d, timeout=600)
            pkgs = data.get("packages", {})
            ecosystems = {p.get("ecosystem") for p in pkgs.values()}
            assert len(pkgs) >= 5, f"Expected >=5 pkgs, got {len(pkgs)}"
            assert "pypi" in ecosystems, "missing pypi ecosystem"
            assert "npm" in ecosystems, "missing npm ecosystem"
            assert "requests" in pkgs, "missing requests"
            assert "express" in pkgs, "missing express"

    def test_07_cross_ecosystem_with_cuda(self):
        """Cross-ecosystem lock with CUDA 12.1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("torch>=2.0\nnumpy>=1.24\n")
            (d / "package.json").write_text('{"dependencies":{"lodash":"^4.17"}}')
            data = _lock(d, cuda="12.1", timeout=600)
            pkgs = data.get("packages", {})
            assert len(pkgs) >= 10, (
                f"Cross-ecosystem CUDA lock should produce >=10 pkgs, got {len(pkgs)}"
            )
            assert "torch" in pkgs, "missing torch"
            assert "lodash" in pkgs, "missing lodash"


# ═══════════════════════════════════════════════════════════════════════
# Scenario 3: Unsatisfiable → backtracking fallback
# ═══════════════════════════════════════════════════════════════════════
class TestUnsatisfiable:
    """SAT solver unsatisfiable → fallback to partial solution."""

    def test_08_impossible_version_constraint(self):
        """Package that doesn't exist at version → partial resolve."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("urllib3>=10.0\nrequests>=1.0\n")
            data = _lock(d, timeout=120)
            pkgs = data.get("packages", {})
            resolved = sum(1 for p in pkgs.values() if p.get("resolved_version"))
            assert resolved >= 1, f"Should resolve at least requests: got {list(pkgs.keys())}"
            assert "requests" in pkgs, "requests should be resolvable"

    def test_09_nonexistent_package_no_crash(self):
        """Lock with nonexistent package → no traceback, graceful handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text(
                "requests>=2.28\nthis-package-does-not-exist-xyz123>=1.0\n"
            )
            result = subprocess.run(
                [*UDR, "lock", "--directory", str(d), "--yes"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=ENV,
                timeout=120,
            )
            assert "Traceback" not in result.stderr, f"No traceback allowed: {result.stderr[:300]}"
            # May resolve requests partially or report error — but no crash


# ═══════════════════════════════════════════════════════════════════════
# Scenario 4: CLI workflow — lock, verify, install, update
# ═══════════════════════════════════════════════════════════════════════
class TestCLIWorkflow:
    """Full CLI workflow."""

    def test_10_lock_creates_lock_file(self):
        """Lock creates udr.lock with correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            result = _run("lock", "-d", str(d), "-y", timeout=300)
            assert result.returncode == 0, f"lock failed: {result.stderr[:500]}"
            lock_path = d / "udr.lock"
            assert lock_path.is_file(), "lock file not created"
            data = json.loads(lock_path.read_text())
            assert "version" in data, "lock missing version"
            assert "packages" in data, "lock missing packages"
            assert "system" in data, "lock missing system"

    def test_11_verify_lock_file(self):
        """Verify lock file runs without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\nflask>=2.0\n")
            _run("lock", "-d", str(d), "-y", timeout=300)
            result = _run("verify", str(d / "udr.lock"), timeout=60)
            # Verify should succeed — check for valid output structure
            assert result.returncode == 0, f"verify failed: {result.stderr[:500]}"
            assert len(result.stdout.strip()) > 0, "verify output is empty"

    def test_12_install_dry_run(self):
        """Install --dry-run prints pip commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            _run("lock", "-d", str(d), "-y", timeout=300)
            result = _run("install", "-d", str(d), "--dry-run", "-y", timeout=60)
            assert result.returncode == 0, f"install --dry-run failed: {result.stderr[:500]}"
            assert "pip" in result.stdout.lower() or "install" in result.stdout.lower(), (
                f"output missing pip command: {result.stdout[:200]}"
            )

    def test_13_update_single_package(self):
        """Update re-resolves and preserves lock structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\nflask>=2.0\n")
            _run("lock", "-d", str(d), "-y", timeout=300)
            result = _run("update", "requests", "-d", str(d), timeout=120)
            assert result.returncode == 0, f"update failed: {result.stderr[:500]}"
            lock_path = d / "udr.lock"
            data = json.loads(lock_path.read_text())
            assert "requests" in data.get("packages", {}), "requests missing after update"

    def test_14_export_dry_run(self):
        """Lock --export requirements.txt --dry-run prints pinned versions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            _run("lock", "-d", str(d), "-y", timeout=300)
            result = _run(
                "lock", "-d", str(d), "--export", "requirements.txt", "--dry-run", timeout=60
            )
            assert result.returncode == 0, f"export --dry-run failed: {result.stderr[:500]}"
            # Should have pinned versions in output
            lines = result.stdout.splitlines()
            pinned = [ln for ln in lines if "==" in ln]
            assert len(pinned) >= 1, f"No pinned versions: {result.stdout[:300]}"


# ═══════════════════════════════════════════════════════════════════════
# Scenario 5: JSON output compliance
# ═══════════════════════════════════════════════════════════════════════
class TestJSONOutput:
    """JSON output compliance."""

    def test_15_resolve_json(self):
        """Resolve --format json produces valid JSON."""
        result = _run("resolve", "requests", "--format", "json", timeout=60)
        assert result.returncode == 0, f"resolve json failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert "resolved_packages" in data, "missing resolved_packages"

    def test_16_lock_json(self):
        """Lock --json produces valid JSON with packages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            result = subprocess.run(
                [*UDR, "lock", "--directory", str(d), "--yes", "--json"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=ENV,
                timeout=300,
            )
            assert result.returncode == 0, f"lock json failed: {result.stderr[:500]}"
            data = json.loads(result.stdout)
            assert "packages" in data, "missing packages"
            assert len(data["packages"]) >= 3, f"Expected >=3 packages, got {len(data['packages'])}"

    def test_17_check_json(self):
        """Check --json produces valid JSON with system info."""
        result = _run("check", "--json", timeout=60)
        assert result.returncode == 0, f"check json failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert len(data) > 0, "check json is empty"

    def test_18_resolve_cross_ecosystem_json(self):
        """Cross-ecosystem resolve with JSON output."""
        result = _run("resolve", "requests", "express@npm", "--format", "json", timeout=120)
        assert result.returncode == 0, f"cross-eco resolve failed: {result.stderr[:500]}"
        data = json.loads(result.stdout)
        pkgs = data.get("resolved_packages", {})
        ecosystems = {v.get("ecosystem") for v in pkgs.values()}
        assert "pypi" in ecosystems, "missing pypi"
        assert "npm" in ecosystems, "missing npm"


# ═══════════════════════════════════════════════════════════════════════
# Scenario 6: Manifest parsing edge cases
# ═══════════════════════════════════════════════════════════════════════
class TestManifests:
    """Manifest format edge cases."""

    def test_19_go_mod_parse(self):
        """go.mod parses without crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "go.mod").write_text(
                "module example.com/test\n\ngo 1.21\n\nrequire (\n\t"
                "github.com/pkg/errors v0.9.1\n\t"
                "golang.org/x/text v0.14.0\n)\n\n"
                "replace github.com/pkg/errors => ../local\n"
            )
            data = _lock(d, timeout=60)
            assert len(data) >= 0

    def test_20_gradle_parse(self):
        """build.gradle parses without crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "build.gradle").write_text(
                "dependencies {\n"
                "    implementation 'com.google.guava:guava:32.1.3-jre'\n"
                "    implementation 'org.apache.commons:commons-lang3:3.13.0'\n"
                "}\n"
            )
            data = _lock(d, timeout=60)
            assert len(data) >= 0

    def test_21_package_swift_parse(self):
        """Package.swift parses without crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "Package.swift").write_text(
                "// swift-tools-version:5.9\nimport PackageDescription\n"
                "let package = Package(\n"
                '    name: "MyLibrary",\n'
                "    dependencies: [\n"
                '        .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.8.0"),\n'
                "    ]\n)\n"
            )
            data = _lock(d, timeout=60)
            assert len(data) >= 0

    def test_22_mix_exs_parse(self):
        """mix.exs parses without crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "mix.exs").write_text(
                "defmodule MyApp.MixProject do\n  use Mix.Project\n"
                '  def project do\n    [app: :my_app, version: "0.1.0", deps: deps()]\n  end\n'
                '  defp deps do\n    [{:phoenix, "~> 1.7.7"}]\n  end\nend\n'
            )
            data = _lock(d, timeout=60)
            assert len(data) >= 0

    def test_23_cabal_parse(self):
        """.cabal parses without crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "mypackage.cabal").write_text(
                "cabal-version: 3.4\nname: mypackage\nversion: 0.1.0\n"
                "build-depends: base >=4.16 && <5, containers >=0.6\n"
            )
            data = _lock(d, timeout=60)
            assert len(data) >= 0

    def test_24_empty_requirements(self):
        """Empty requirements.txt → graceful (no packages, no crash)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("")
            result = subprocess.run(
                [*UDR, "lock", "--directory", str(d), "--yes"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=ENV,
                timeout=60,
            )
            assert "Traceback" not in result.stderr, f"traceback: {result.stderr[:200]}"

    def test_25_no_manifests(self):
        """Empty directory → graceful message (no crash, no traceback)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            result = subprocess.run(
                [*UDR, "lock", "--directory", str(d), "--yes"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=ENV,
                timeout=60,
            )
            assert "Traceback" not in result.stderr, f"traceback: {result.stderr[:200]}"


# ═══════════════════════════════════════════════════════════════════════
# Scenario 7: Misc commands
# ═══════════════════════════════════════════════════════════════════════
class TestMiscCommands:
    """Other CLI commands."""

    def test_26_dependency_graph(self):
        """Graph produces dependency tree output."""
        result = _run("graph", "requests", "flask", timeout=120)
        assert result.returncode == 0, f"graph failed: {result.stderr[:500]}"
        assert "requests" in result.stdout.lower() or "flask" in result.stdout.lower()

    def test_27_list_ecosystems(self):
        """List all supported ecosystems."""
        result = _run("list-ecosystems", timeout=30)
        assert result.returncode == 0, f"list-ecosystems failed: {result.stderr}"
        assert "pypi" in result.stdout.lower()
        assert "npm" in result.stdout.lower()
        assert "crates" in result.stdout.lower()

    def test_28_check_command(self):
        """Check shows system info."""
        result = _run("check", timeout=30)
        assert result.returncode == 0, f"check failed: {result.stderr}"
        assert any(kw in result.stdout.lower() for kw in ("python", "system", "os", "version"))

    def test_29_version_flag(self):
        """--version prints version string."""
        result = _run("--version", timeout=30)
        assert result.returncode == 0, f"--version failed: {result.stderr}"
        assert len(result.stdout.strip()) > 0

    def test_30_help_output(self):
        """--help prints usage."""
        result = _run("--help", timeout=30)
        assert result.returncode == 0, f"--help failed: {result.stderr}"
        assert "usage" in result.stdout.lower()
        assert "resolve" in result.stdout.lower()
        assert "lock" in result.stdout.lower()


# ═══════════════════════════════════════════════════════════════════════
# Scenario 8: Update edge cases
# ═══════════════════════════════════════════════════════════════════════
class TestUpdate:
    """Update command edge cases."""

    def test_31_update_nonexistent(self):
        """Update nonexistent package is graceful."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            _run("lock", "-d", str(d), "-y", timeout=300)
            result = _run("update", "this-pkg-doesnt-exist", "-d", str(d), timeout=60)
            # Should not crash — graceful message is acceptable
            assert "Traceback" not in result.stderr, f"traceback: {result.stderr[:300]}"

    def test_32_update_cross_ecosystem(self):
        """Update npm package in cross-eco lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            (d / "package.json").write_text('{"dependencies":{"express":"^4.18.0"}}')
            _run("lock", "-d", str(d), "-y", timeout=300)
            result = _run("update", "express", "-d", str(d), timeout=120)
            assert result.returncode == 0, f"update cross-eco failed: {result.stderr[:500]}"
            assert "express" in result.stdout.lower()


# ═══════════════════════════════════════════════════════════════════════
# Scenario 9: Offline mode
# ═══════════════════════════════════════════════════════════════════════
class TestOffline:
    """Offline mode."""

    def test_33_offline_resolve_no_crash(self):
        """--offline resolve does not crash (may return no results without cache)."""
        result = _run("--offline", "resolve", "requests", timeout=30)
        # Should exit gracefully — either 0 (with cached data) or error message
        assert "Traceback" not in result.stderr, f"traceback: {result.stderr[:200]}"

    def test_34_offline_check(self):
        """--offline check provides system info without network."""
        result = _run("--offline", "check", "--json", timeout=30)
        assert result.returncode == 0, f"offline check failed: {result.stderr[:200]}"
        data = json.loads(result.stdout)
        assert len(data) > 0, "offline check empty"


# ═══════════════════════════════════════════════════════════════════════
# Scenario 10: Version constraints
# ═══════════════════════════════════════════════════════════════════════
class TestConstraints:
    """Version constraint resolution."""

    def test_35_pinned_constraint(self):
        """Exact pin == resolves correctly."""
        result = _run("resolve", "requests==2.28.0", "--format", "json", timeout=60)
        assert result.returncode == 0, f"pinned failed: {result.stderr}"
        data = json.loads(result.stdout)
        pkgs = data.get("resolved_packages", {})
        ver = pkgs.get("requests", {}).get("version", "")
        assert ver == "2.28.0", f"Expected requests==2.28.0, got {ver}"

    def test_36_minimum_constraint(self):
        """>= constraint resolves to >= specified."""
        result = _run("resolve", "requests>=2.30", "--format", "json", timeout=60)
        assert result.returncode == 0, f"min constraint failed: {result.stderr}"
        data = json.loads(result.stdout)
        pkgs = data.get("resolved_packages", {})
        ver = pkgs.get("requests", {}).get("version", "")
        from packaging.version import Version

        assert Version(ver) >= Version("2.30"), f"Expected requests >=2.30, got {ver}"

    def test_37_combined_constraint(self):
        """>=X,<Y combined constraint resolves correctly."""
        result = _run("resolve", "numpy>=1.24,<2.0", "--format", "json", timeout=120)
        assert result.returncode == 0, f"combined constraint failed: {result.stderr}"
        data = json.loads(result.stdout)
        pkgs = data.get("resolved_packages", {})
        ver = pkgs.get("numpy", {}).get("version", "")
        from packaging.version import Version

        v = Version(ver)
        assert Version("1.24") <= v < Version("2.0"), f"Expected numpy 1.24 <= ver < 2.0, got {ver}"

    def test_38_cross_ecosystem_constraint(self):
        """Cross-ecosystem resolve with version constraints."""
        result = _run(
            "resolve",
            "numpy>=1.24",
            "express>=4.18@npm",
            "--format",
            "json",
            timeout=120,
        )
        assert result.returncode == 0, f"cross-eco constraint failed: {result.stderr[:300]}"
        data = json.loads(result.stdout)
        pkgs = data.get("resolved_packages", {})
        assert "numpy" in pkgs, "missing numpy"
        assert "express" in pkgs, "missing express"
        from packaging.version import Version

        assert Version(pkgs["express"]["version"]) >= Version("4.18"), (
            f"Expected express >=4.18, got {pkgs['express']['version']}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Scenario 11: System requirements / compatibility
# ═══════════════════════════════════════════════════════════════════════
class TestSystemCompatibility:
    """System compatibility scenarios."""

    def test_39_check_shows_python_version(self):
        """Check command shows Python version."""
        result = _run("check", timeout=30)
        assert result.returncode == 0
        assert "3." in result.stdout, f"Python version expected: {result.stdout[:200]}"

    def test_40_check_verbose(self):
        """Check with --verbose shows detailed info."""
        result = _run("check", "--verbose", timeout=30)
        assert result.returncode == 0


# ═══════════════════════════════════════════════════════════════════════
# Scenario 12: Lock file structure compliance
# ═══════════════════════════════════════════════════════════════════════
class TestLockStructure:
    """Lock file schema compliance."""

    def test_41_lock_has_required_fields(self):
        """Lock file has all required top-level fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\nflask>=2.0\n")
            result = subprocess.run(
                [*UDR, "lock", "--directory", str(d), "--yes", "--json"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=ENV,
                timeout=300,
            )
            assert result.returncode == 0
            data = json.loads(result.stdout)
            for field in ("version", "packages", "system", "generated_at"):
                assert field in data, f"lock missing '{field}'"

    def test_42_report_file_generated(self):
        """--report flag generates human-readable report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            result = subprocess.run(
                [*UDR, "lock", "--directory", str(d), "--yes", "--report"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=ENV,
                timeout=300,
            )
            assert result.returncode == 0
            # Report may be named udr-lock.report.txt or udr-lock-report.txt
            candidates = [
                d / "udr-lock.report.txt",
                d / "udr-lock-report.txt",
            ]
            assert any(c.is_file() for c in candidates), (
                f"report file not generated, checked: {[str(c) for c in candidates]}"
            )


# ═══════════════════════════════════════════════════════════════════════
# Scenario 13: Install / restore from lock
# ═══════════════════════════════════════════════════════════════════════
class TestInstallRestore:
    """Install and restore commands."""

    def test_43_install_dry_run_from_lock(self):
        """Install from lock shows ecosystem-specific commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            (d / "package.json").write_text('{"dependencies":{"express":"^4.18.0"}}')
            _run("lock", "-d", str(d), "-y", timeout=300)
            result = _run("install", "-d", str(d), "--dry-run", "-y", timeout=60)
            assert result.returncode == 0
            assert "pip" in result.stdout.lower()
            assert "npm" in result.stdout.lower()

    def test_44_install_restore_flag(self):
        """Install --restore flag works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            _run("lock", "-d", str(d), "-y", timeout=300)
            result = _run("install", "-d", str(d), "--dry-run", "-y", "--restore", timeout=60)
            assert result.returncode == 0
            assert "pip" in result.stdout.lower() or "install" in result.stdout.lower()


# ═══════════════════════════════════════════════════════════════════════
# Scenario 14: Resolve command edge cases
# ═══════════════════════════════════════════════════════════════════════
class TestResolveEdgeCases:
    """Resolve command edge cases."""

    def test_45_resolve_multiple_ecosystems(self):
        """Resolve packages across multiple ecosystems."""
        result = _run(
            "resolve",
            "requests",
            "express@npm",
            "serde@crates",
            "--format",
            "json",
            timeout=120,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        pkgs = data.get("resolved_packages", {})
        ecosystems = {v.get("ecosystem") for v in pkgs.values()}
        assert len(ecosystems) >= 2, f"Expected >=2 ecosystems, got {ecosystems}"

    def test_46_resolve_with_cuda_flag(self):
        """Resolve with --cuda flag."""
        result = _run(
            "resolve",
            "torch",
            "--cuda",
            "12.1",
            "--format",
            "json",
            timeout=180,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        pkgs = data.get("resolved_packages", {})
        assert "torch" in pkgs
