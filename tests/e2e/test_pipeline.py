"""End-to-end pipeline test: create manifests → resolve → audit."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UDR = [sys.executable, "-m", "backend.cli"]

ENV = {
    **os.environ,
    "PYTHONPATH": str(REPO_ROOT),
    "TESTING": "true",
    "SECRET_KEY": "test-secret-key-for-ci",
    "SOLVER_TIMEOUT": "120",
}


@pytest.mark.e2e
class TestPipeline:
    """User workflow: manifests → lock → CVE check → verify."""

    def _run(self, *args: str, timeout: int = 300, cwd: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [*UDR, *args],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=ENV,
            timeout=timeout,
        )

    def test_full_pipeline(self, tmp_path: Path) -> None:
        proj = tmp_path / "project"
        proj.mkdir()

        # 1. Create manifest files
        (proj / "requirements.txt").write_text("requests>=2.28\nflask>=2.0\n")
        assert (proj / "requirements.txt").is_file()

        # 2. Run udr lock
        lock_result = self._run("lock", "-d", str(proj), "-y", "--json", cwd=str(proj))
        assert lock_result.returncode == 0, f"lock failed: {lock_result.stderr}"

        # 3. Assert lock file exists and contains expected packages
        lock_file = proj / "udr.lock"
        assert lock_file.is_file(), f"lock file not found at {lock_file}"

        lock_data = json.loads(lock_file.read_text())
        lock_packages = lock_data.get("packages", {})
        pkg_names = {v["name"].lower() for v in lock_packages.values()}
        assert "requests" in pkg_names, f"requests not in lock packages: {pkg_names}"
        assert "flask" in pkg_names, f"flask not in lock packages: {pkg_names}"

        # 4. Run udr check --cve
        cve_result = self._run("check", "--cve", "-d", str(proj), cwd=str(proj))
        assert cve_result.returncode == 0, f"CVE check failed: {cve_result.stderr}"

        # 5. Run udr verify
        verify_result = self._run("verify", "-d", str(proj), cwd=str(proj))
        assert verify_result.returncode == 0, f"verify failed: {verify_result.stderr}"
