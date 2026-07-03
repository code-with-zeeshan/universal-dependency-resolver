"""Black-box CLI tests — run `udr` as a subprocess."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENV = {
    **os.environ,
    "PYTHONPATH": REPO_ROOT,
    "TESTING": "true",
    "SECRET_KEY": "test-secret-key-for-ci",
    "UDR_OFFLINE": "true",
    "REQUEST_TIMEOUT": "3",
}


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "backend.cli", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=ENV,
    )


class TestHelp:
    def test_help_exit_code(self):
        result = _run("--help")
        assert result.returncode == 0

    def test_help_contains_usage(self):
        result = _run("--help")
        assert "usage: udr" in result.stdout


class TestVersion:
    def test_version_exit_code(self):
        result = _run("--version")
        assert result.returncode == 0

    def test_version_contains_version(self):
        result = _run("--version")
        assert "udr" in result.stdout
        # Should contain a semver-like string (e.g. 1.2.5)
        assert any(c.isdigit() for c in result.stdout)


class TestListEcosystems:
    def test_list_ecosystems_exit_code(self):
        result = _run("list-ecosystems")
        assert result.returncode == 0

    def test_list_ecosystems_shows_pypi(self):
        result = _run("list-ecosystems")
        assert "pypi" in result.stdout or "PyPI" in result.stdout

    def test_list_ecosystems_json(self):
        result = _run("list-ecosystems", "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        names = {item["name"] for item in data}
        assert "pypi" in names
        assert "npm" in names


class TestCheck:
    def test_check_exit_code(self):
        result = _run("check")
        assert result.returncode == 0


class TestServeHelp:
    def test_serve_help_exit_code(self):
        result = _run("serve", "--help")
        assert result.returncode == 0

    def test_serve_help_contains_serve(self):
        result = _run("serve", "--help")
        assert "serve" in result.stdout.lower()


class TestCompletionHelp:
    def test_completion_help_exit_code(self):
        result = _run("completion", "--help")
        assert result.returncode == 0

    def test_completion_help_shows_choices(self):
        result = _run("completion", "--help")
        assert "bash" in result.stdout
        assert "zsh" in result.stdout
        assert "fish" in result.stdout


class TestCompletionBash:
    def test_completion_bash_exit_code(self):
        result = _run("completion", "bash")
        assert result.returncode == 0

    def test_completion_bash_contains_function(self):
        result = _run("completion", "bash")
        assert "_completion" in result.stdout
        assert "complete -F" in result.stdout


class TestCompletionZsh:
    def test_completion_zsh_exit_code(self):
        result = _run("completion", "zsh")
        assert result.returncode == 0

    def test_completion_zsh_contains_compdef(self):
        result = _run("completion", "zsh")
        assert "#compdef" in result.stdout


class TestCompletionFish:
    def test_completion_fish_exit_code(self):
        result = _run("completion", "fish")
        assert result.returncode == 0

    def test_completion_fish_contains_function(self):
        result = _run("completion", "fish")
        assert "_completion" in result.stdout
        assert "complete -c" in result.stdout


class TestResolveHelp:
    def test_resolve_help_exit_code(self):
        result = _run("resolve", "--help")
        assert result.returncode == 0

    def test_resolve_help_contains_usage(self):
        result = _run("resolve", "--help")
        assert "usage: udr resolve" in result.stdout


class TestManifestDetection:
    def test_brewfile_detected(self, tmp_path):
        (tmp_path / "Brewfile").write_text('brew "curl"\nbrew "wget"\n')
        result = _run("lock", "--directory", str(tmp_path))
        assert "Brewfile" in result.stdout
        assert "curl" in result.stdout
        assert "wget" in result.stdout

    def test_brewfile_with_versions(self, tmp_path):
        (tmp_path / "Brewfile").write_text('brew "python" "3.12"\nbrew "node"\n')
        result = _run("lock", "--directory", str(tmp_path))
        assert "Brewfile" in result.stdout
        assert "python" in result.stdout

    def test_apt_packages_txt_detected(self, tmp_path):
        (tmp_path / "apt-packages.txt").write_text("curl\nbuild-essential\n")
        result = _run("lock", "--directory", str(tmp_path))
        assert "apt-packages.txt" in result.stdout
        assert "curl" in result.stdout
        assert "build-essential" in result.stdout

    def test_apt_packages_with_versions(self, tmp_path):
        (tmp_path / "apt-packages.txt").write_text("curl>=7.68\npython3==3.9\n")
        result = _run("lock", "--directory", str(tmp_path))
        assert "apt-packages.txt" in result.stdout

    def test_apk_packages_txt_detected(self, tmp_path):
        (tmp_path / "apk-packages.txt").write_text("curl\nnginx\n")
        result = _run("lock", "--directory", str(tmp_path))
        assert "apk-packages.txt" in result.stdout
        assert "curl" in result.stdout
        assert "nginx" in result.stdout

    def test_apk_packages_with_versions(self, tmp_path):
        (tmp_path / "apk-packages.txt").write_text("curl>=7.68\npython3==3.9\n")
        result = _run("lock", "--directory", str(tmp_path))
        assert "apk-packages.txt" in result.stdout
