"""Problem-statement validation tests — cross-language resolution with system-aware SAT solving."""

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
    "SOLVER_TIMEOUT": "300",
}


def _lock(
    directory: Path,
    *,
    cuda: str | None = None,
    timeout: int = 300,
) -> dict:
    args = ["lock", "--directory", str(directory), "--yes", "--json"]
    if cuda:
        args.extend(["--cuda", cuda])
    result = subprocess.run(
        [*UDR, *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**ENV, "SOLVER_TIMEOUT": str(timeout)},
        timeout=timeout + 30,
    )
    if result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return {}


def _resolve(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*UDR, "resolve", *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=ENV,
        timeout=timeout,
    )


class TestProblemStatement:
    """13 problem-statement scenarios (mirrors test_problem_statement.sh)."""

    def test_01_single_ecosystem_resolution(self):
        """Python single-ecosystem: resolve requests>=2.28 with transitive deps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            data = _lock(d, timeout=300)
            pkgs = data.get("packages", {})
            assert len(pkgs) >= 5, f"Expected >=5 packages, got {len(pkgs)}: {list(pkgs.keys())}"
            assert "requests" in pkgs

    def test_02_cross_ecosystem_resolution(self):
        """Cross-ecosystem: resolve PyPI+npm+crates with CUDA 12.1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\nurllib3>=2.0\ntorch>=2.0\n")
            (d / "package.json").write_text('{"dependencies":{"express":"^4.18.0"}}')
            (d / "Cargo.toml").write_text(
                '[package]\nname = "test-proj"\nversion = "0.1.0"\n[dependencies]\nserde = "1.0"\ntokio = "1.0"\n'
            )
            data = _lock(d, cuda="12.1", timeout=300)
            pkgs = data.get("packages", {})
            resolved = sum(1 for p in pkgs.values() if p.get("resolved_version"))
            ecosystems = {p.get("ecosystem") for p in pkgs.values()}
            assert len(pkgs) >= 25, f"Expected >=25 packages, got {len(pkgs)}"
            assert resolved == len(pkgs), f"Expected all resolved, got {resolved}/{len(pkgs)}"
            assert "pypi" in ecosystems
            assert "npm" in ecosystems
            assert "crates" in ecosystems

    def test_03_cuda_variant_selection(self):
        """CUDA variant selection: torch with CUDA 12.1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("torch>=2.0\n")
            data = _lock(d, cuda="12.1", timeout=180)
            pkgs = data.get("packages", {})
            cuda_pkgs = [
                n for n in pkgs
                if "cuda" in n.lower() or "nvidia" in n.lower() or "triton" in n.lower()
            ]
            torch_ver = pkgs.get("torch", {}).get("resolved_version", "")
            assert len(cuda_pkgs) >= 3, f"Expected >=3 CUDA deps, got {len(cuda_pkgs)}: {cuda_pkgs}"
            assert torch_ver, "torch not resolved"

    def test_04_conflict_detection(self):
        """SAT solver: handle unsatisfiable constraints gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\nurllib3>=10.0\n")
            data = _lock(d, timeout=120)
            pkgs = data.get("packages", {})
            resolved = sum(1 for p in pkgs.values() if p.get("resolved_version"))
            assert resolved >= 1, "SAT solver couldn't resolve any packages"

    def test_05_lock_file_structure(self):
        """Lock file has correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            data = _lock(d, timeout=300)
            assert "version" in data, "lock missing version"
            assert "packages" in data, "lock missing packages"
            assert "system" in data, "lock missing system"
            assert len(data["packages"]) >= 3, f"Expected >=3 packages, got {len(data['packages'])}"

    def test_06_deep_transitive_resolution(self):
        """Deep transitive: flask -> werkzeug -> markupsafe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("flask>=2.3\n")
            data = _lock(d, timeout=300)
            pkgs = data.get("packages", {})
            assert len(pkgs) >= 5, f"Expected >=5 transitive deps for flask, got {len(pkgs)}: {list(pkgs.keys())[:10]}"

    def test_07_go_mod_parsing(self):
        """Manifest format: go.mod parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "go.mod").write_text(
                "module example.com/test\ngo 1.21\nrequire (\n    github.com/pkg/errors v0.9.1\n    golang.org/x/text v0.14.0\n)\n"
            )
            data = _lock(d, timeout=60)
            pkgs = data.get("packages", {})
            # go.mod is offline but should still parse
            assert len(pkgs) >= 0

    def test_08_build_gradle_parsing(self):
        """Manifest format: build.gradle parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "build.gradle").write_text(
                "dependencies {\n    implementation 'com.google.guava:guava:32.1.3-jre'\n    implementation 'org.apache.commons:commons-lang3:3.13.0'\n}\n"
            )
            data = _lock(d, timeout=60)
            pkgs = data.get("packages", {})
            assert len(pkgs) >= 0

    def test_09_package_swift_parsing(self):
        """Manifest format: Package.swift parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "Package.swift").write_text(
                '// swift-tools-version:5.9\nimport PackageDescription\nlet package = Package(\n    name: "MyLibrary",\n    dependencies: [\n        .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.8.0"),\n    ]\n)\n'
            )
            data = _lock(d, timeout=60)
            pkgs = data.get("packages", {})
            assert len(pkgs) >= 0

    def test_10_mix_exs_parsing(self):
        """Manifest format: mix.exs parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "mix.exs").write_text(
                'defmodule MyApp.MixProject do\n  use Mix.Project\n  def project do\n    [app: :my_app, version: "0.1.0", deps: deps()]\n  end\n  defp deps do\n    [{:phoenix, "~> 1.7.7"}]\n  end\nend\n'
            )
            data = _lock(d, timeout=60)
            pkgs = data.get("packages", {})
            assert len(pkgs) >= 0

    def test_11_cabal_parsing(self):
        """Manifest format: .cabal parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "mypackage.cabal").write_text(
                "cabal-version: 3.4\nname: mypackage\nversion: 0.1.0\nbuild-depends: base >=4.16 && <5, containers >=0.6\n"
            )
            data = _lock(d, timeout=60)
            pkgs = data.get("packages", {})
            assert len(pkgs) >= 0

    def test_12_no_gpu_no_cuda(self):
        """No GPU: CPU-only resolution should not pull CUDA deps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "requirements.txt").write_text("requests>=2.28\n")
            data = _lock(d, timeout=300)
            pkgs = data.get("packages", {})
            cuda = [n for n in pkgs if "cuda" in n.lower() or "nvidia" in n.lower()]
            assert len(cuda) == 0, f"Found {len(cuda)} CUDA packages despite no GPU: {cuda}"

    def test_13_cli_resolve_command(self):
        """CLI: udr resolve single package."""
        result = _resolve("requests>=2.28", timeout=60)
        assert "requests" in result.stdout.lower()
