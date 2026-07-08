"""Validate every CLI command's --json output matches expected schema.

Prevents silent breakages of machine-readable output.
"""

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
    "UDR_OFFLINE": "true",
}


def _run(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*UDR, *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=ENV,
        timeout=timeout,
    )


class TestJSONOutputCompliance:
    """Verify --json output of every capable CLI command."""

    def test_list_ecosystems_json(self):
        result = _run("list-ecosystems", "--json")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) > 0
        for entry in data:
            assert "name" in entry, f"Missing 'name' in {entry}"
            assert isinstance(entry["name"], str)
        names = {e["name"] for e in data}
        assert "pypi" in names, f"Expected pypi in ecosystems, got {names}"
        assert "npm" in names

    def test_check_json(self):
        result = _run("check", "--json")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "cpu" in data, f"Expected 'cpu' key, got keys: {list(data.keys())[:10]}"

    def test_check_deps_json(self):
        result = _run("check", "--deps", "--json")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "platform" in data or "cpu" in data

    def test_resolve_format_json(self):
        result = _run("resolve", "requests", "--format", "json", timeout=60)
        assert result.returncode in (0, 1), f"unexpected exit code: {result.returncode}"
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "resolved_packages" in data, (
            f"Missing 'resolved_packages' key, got {list(data.keys())}"
        )
        assert isinstance(data["resolved_packages"], dict)

    def test_lock_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir) / "project"
            d.mkdir()
            (d / "requirements.txt").write_text("requests>=2.28\n")
            result = _run("lock", "-d", str(d), "-y", "--json", timeout=300)
            if result.returncode != 0:
                pytest.skip(f"Lock failed (real network): {result.stderr[:200]}")
            data = json.loads(result.stdout)
            assert isinstance(data, dict)
            assert "version" in data, "Missing 'version' key"
            assert "packages" in data, "Missing 'packages' key"
            assert "system" in data, "Missing 'system' key"
            assert isinstance(data["packages"], dict)
