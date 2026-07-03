"""CLI end-to-end tests — run `udr` as subprocess against real registries."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UDR = [sys.executable, "-m", "backend.cli"]

ENV = {
    **os.environ,
    "PYTHONPATH": str(REPO_ROOT),
    "TESTING": "true",
    "SECRET_KEY": "test-secret-key-for-ci",
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


class TestCLIRealWorld:
    """10 real-world CLI scenarios (mirrors test_cli_realworld.sh)."""

    def test_01_single_package_resolve(self):
        """Single package resolve (basic)."""
        result = _run("resolve", "requests", timeout=60)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "requests" in result.stdout

    def test_02_version_constraint_resolve(self):
        """Resolve with version constraints."""
        result = _run("resolve", "numpy>=1.20", "pandas>=1.3", timeout=120)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "numpy" in result.stdout
        assert "pandas" in result.stdout

    def test_03_cross_ecosystem_resolve(self):
        """Cross-ecosystem resolve."""
        result = _run("resolve", "numpy@pypi", "express@npm", timeout=120)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "numpy" in result.stdout
        assert "express" in result.stdout.lower()

    def test_04_json_output(self):
        """Structured JSON output."""
        result = _run("resolve", "requests", "--format", "json", timeout=60)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert "resolved_packages" in data
        assert "requests" in data["resolved_packages"]

    def test_05_dependency_graph(self):
        """Dependency graph."""
        result = _run("graph", "requests", "flask", timeout=120)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "requests" in result.stdout.lower() or "flask" in result.stdout.lower()

    def test_06_lock_from_manifest(self):
        """Lock file from manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            (proj / "requirements.txt").write_text("requests>=2.28\nflask>=2.0\nnumpy>=1.20\n")
            result = _run("lock", "-d", str(proj), "-y", timeout=300)
            assert result.returncode == 0, f"stderr: {result.stderr}"
            assert (proj / "udr.lock").is_file()

    def test_07_verify_lock_file(self):
        """Verify lock file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            (proj / "requirements.txt").write_text("requests>=2.28\nflask>=2.0\nnumpy>=1.20\n")
            _run("lock", "-d", str(proj), "-y", timeout=300)
            result = _run("verify", str(proj / "udr.lock"), timeout=30)
            assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_08_update_package_in_lock(self):
        """Update single package in lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            (proj / "requirements.txt").write_text("requests>=2.28\nflask>=2.0\n")
            _run("lock", "-d", str(proj), "-y", timeout=300)
            result = _run("update", "requests", "-d", str(proj), timeout=120)
            assert result.returncode == 0, f"stderr: {result.stderr}"
            assert "requests" in result.stdout.lower()

    def test_09_cuda_aware_resolution(self):
        """CUDA-aware resolution."""
        result = _run("resolve", "torch", "--cuda", "12.1", timeout=180)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "torch" in result.stdout.lower()

    def test_10_full_pipeline(self):
        """Full pipeline: export + install dry-run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            (proj / "requirements.txt").write_text("requests>=2.28\nflask>=2.0\n")
            _run("lock", "-d", str(proj), "-y", timeout=300)
            r1 = _run("lock", "-d", str(proj), "--export", "requirements.txt", "--dry-run", timeout=60)
            r2 = _run("install", "-d", str(proj), "--dry-run", "-y", timeout=60)
            assert r1.returncode == 0, f"export failed: {r1.stderr}"
            assert r2.returncode == 0, f"install failed: {r2.stderr}"
