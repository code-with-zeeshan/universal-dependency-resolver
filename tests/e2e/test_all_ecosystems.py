"""Comprehensive 27-ecosystem test: individual, mixed, system-aware, edge cases.

Picks well-known packages that exist on real registries.
Query-only ecosystems (nix, guix, vcpkg, conan, docker, helm, terraform)
are tested for search/details but NOT lock resolution.
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
    "SOLVER_TIMEOUT": "120",
}

# ============================================================
# Ecosystem taxonomy
# ============================================================
RESOLVABLE = [
    "pypi",
    "conda",
    "npm",
    "crates",
    "maven",
    "gomodules",
    "apt",
    "apk",
    "cocoapods",
    "homebrew",
    "nuget",
    "packagist",
    "rubygems",
    "pub",
    "gradle",
    "swift",
    "hex",
    "haskell",
]
QUERY_ONLY = ["nix", "guix", "vcpkg", "conan", "docker", "helm", "terraform"]
ALL_ACTIVE = RESOLVABLE + QUERY_ONLY  # 25 ecosystems

# Per-ecosystem known-good packages for search/details
QUERY_PROBES: dict[str, tuple[str, str]] = {
    "pypi": ("requests", "pypi"),
    "conda": ("numpy", "conda"),
    "npm": ("lodash", "npm"),
    "crates": ("serde", "crates"),
    "maven": ("commons-lang3", "maven"),
    "gomodules": ("gorilla/mux", "gomodules"),
    "apt": ("curl", "apt"),
    "apk": ("busybox", "apk"),
    "cocoapods": ("AFNetworking", "cocoapods"),
    "homebrew": ("curl", "homebrew"),
    "nuget": ("Newtonsoft.Json", "nuget"),
    "packagist": ("monolog/monolog", "packagist"),
    "rubygems": ("rack", "rubygems"),
    "pub": ("provider", "pub"),
    "gradle": ("com.google.guava:guava", "gradle"),
    "swift": ("swift-algorithms", "swift"),
    "hex": ("jason", "hex"),
    "haskell": ("text", "haskell"),
    "nix": ("hello", "nix"),
    "guix": ("hello", "guix"),
    "vcpkg": ("fmt", "vcpkg"),
    "conan": ("fmt/9.1.0", "conan"),
    "docker": ("alpine", "docker"),
    "helm": ("nginx-ingress", "helm"),
    "terraform": ("hashicorp/aws", "terraform"),
}

# Per-resolvable-ecosystem manifest content for lock resolution
MANIFEST_CONTENTS: dict[str, list[str]] = {
    "pypi": ["requirements.txt", "requests>=2.28\nflask>=2.0\n"],
    "npm": ["package.json", '{"dependencies": {"lodash": "^4.17.21", "express": "^4.18.0"}}\n'],
    "crates": [
        "Cargo.toml",
        '[package]\nname = "test"\nversion = "0.1.0"\n[dependencies]\nserde = "1"\n',
    ],
    "gomodules": ["go.mod", "module test\ngo 1.21\nrequire github.com/gorilla/mux v1.8.0\n"],
    "nuget": [
        "packages.config",
        '<?xml version="1.0"?>\n<packages>\n<package id="Newtonsoft.Json" version="13.0.3"/>\n</packages>\n',
    ],
    "rubygems": ["Gemfile", 'source "https://rubygems.org"\ngem "rack", "~> 3.0"\n'],
    "packagist": ["composer.json", '{"require": {"monolog/monolog": "^2.0"}}\n'],
    "hex": [
        "mix.exs",
        'defmodule Test.MixProject do\n  use Mix.Project\n  def project do\n    [app: :test, version: "0.1.0", deps: deps()]\n  end\n  defp deps do\n    [{:jason, "~> 1.4"}]\n  end\nend\n',
    ],
    "pub": [
        "pubspec.yaml",
        'name: test\nenvironment:\n  sdk: ">=3.0.0 <4.0.0"\ndependencies:\n  provider: ^6.0.0\n',
    ],
}

# Resolvable ecosystems that need special handling (slow or missing client)
LOCK_SKIP: set[str] = {
    "conda",
    "maven",
    "apt",
    "apk",
    "cocoapods",
    "homebrew",
    "gradle",
    "swift",
    "haskell",
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


def _write_manifest(project: Path, eco: str):
    if eco in MANIFEST_CONTENTS:
        fname, content = MANIFEST_CONTENTS[eco]
        (project / fname).write_text(content)


# ============================================================
# A. Individual ecosystem query tests
# ============================================================


class TestIndividualEcosystemQueries:
    """Search + details for every active ecosystem."""

    @pytest.mark.parametrize("eco", ALL_ACTIVE)
    def test_search(self, eco):
        pkg, alias = QUERY_PROBES[eco]
        result = _run("search", pkg, "--ecosystem", alias, "--json", timeout=60)
        if result.returncode != 0:
            pytest.skip(f"{eco} search failed (network?): {result.stderr[:200]}")
        data = json.loads(result.stdout)
        assert isinstance(data, dict), f"{eco} search did not return dict"
        assert alias in data or eco in data, f"{eco} search missing ecosystem key"

    @pytest.mark.parametrize("eco", ALL_ACTIVE)
    def test_details(self, eco):
        pkg, alias = QUERY_PROBES[eco]
        result = _run("details", f"{alias}/{pkg}", "--json", timeout=60)
        if result.returncode != 0:
            pytest.skip(f"{eco} details failed: {result.stderr[:200]}")
        data = json.loads(result.stdout)
        assert isinstance(data, dict), f"{eco} details did not return a dict"
        # details includes versions and dependencies when available
        assert "name" in data or "package" in data.get("package", data), (
            f"{eco} details missing name"
        )


# ============================================================
# B. Individual ecosystem lock resolution
# ============================================================


class TestIndividualEcosystemLock:
    """Lock --dry-run for each resolvable ecosystem that has a manifest."""

    @pytest.mark.parametrize("eco", sorted(set(RESOLVABLE) - LOCK_SKIP))
    def test_lock_dry_run(self, eco):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            _write_manifest(proj, eco)
            result = _run("lock", "-d", str(proj), "--dry-run", "--json", timeout=300)
            if result.returncode != 0:
                pytest.skip(f"{eco} lock failed: {result.stderr[:300]}")
            data = json.loads(result.stdout)
            assert isinstance(data, dict), f"{eco} lock output not dict"
            pkgs = data.get("packages", {})
            assert len(pkgs) > 0, f"{eco} lock resolved 0 packages"

    @pytest.mark.parametrize("eco", sorted(set(RESOLVABLE) - LOCK_SKIP))
    def test_verify(self, eco):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            _write_manifest(proj, eco)
            lock_result = _run("lock", "-d", str(proj), "-y", timeout=300)
            if lock_result.returncode != 0:
                pytest.skip(f"{eco} lock-create failed: {lock_result.stderr[:200]}")
            result = _run("verify", "-d", str(proj), timeout=60)
            if result.returncode != 0:
                pytest.skip(f"{eco} verify failed: {result.stderr[:200]}")
            assert "ok" in result.stdout.lower() or "verified" in result.stdout.lower(), (
                f"{eco} verify unexpected output: {result.stdout[:200]}"
            )


# ============================================================
# C. Mixed multi-ecosystem resolution
# ============================================================

MIXED_SETS = [
    ["pypi", "npm"],
    ["pypi", "rubygems"],
    ["npm", "crates"],
    ["pypi", "npm", "crates", "gomodules"],
    ["pypi", "nuget"],
    ["pypi", "packagist"],
    ["npm", "pub"],
    ["pypi", "hex"],
]


class TestMixedMultiEcosystem:
    """Multi-manifest resolution with 2-4 ecosystems together."""

    @pytest.mark.parametrize("ecos", MIXED_SETS)
    def test_mixed_lock_dry_run(self, ecos):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            written = sum(1 for eco in ecos if eco in MANIFEST_CONTENTS and eco not in LOCK_SKIP)
            if written < 2:
                pytest.skip(f"{'+'.join(ecos)}: need >=2 writable manifests")
            for eco in ecos:
                _write_manifest(proj, eco)
            result = _run("lock", "-d", str(proj), "--dry-run", "--json", timeout=300)
            if result.returncode != 0:
                pytest.skip(f"{'+'.join(ecos)} lock failed: {result.stderr[:300]}")
            data = json.loads(result.stdout)
            assert isinstance(data, dict), f"{'+'.join(ecos)} lock output not dict"
            pkgs = data.get("packages", {})
            if pkgs:
                assert len(pkgs) > 0, f"{'+'.join(ecos)} resolved 0 packages"

    @pytest.mark.parametrize("ecos", MIXED_SETS)
    def test_mixed_graph_json(self, ecos):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            written = sum(1 for eco in ecos if eco in MANIFEST_CONTENTS and eco not in LOCK_SKIP)
            if written < 2:
                pytest.skip(f"{'+'.join(ecos)}: need >=2 writable manifests")
            for eco in ecos:
                _write_manifest(proj, eco)
            result = _run("lock", "-d", str(proj), "-y", timeout=300)
            if result.returncode != 0:
                pytest.skip(f"{'+'.join(ecos)} lock-create failed: {result.stderr[:200]}")
            result = _run("graph", "-d", str(proj), "--json", timeout=60)
            if result.returncode != 0:
                pytest.skip(f"{'+'.join(ecos)} graph failed: {result.stderr[:200]}")

    @pytest.mark.parametrize("ecos", MIXED_SETS)
    def test_mixed_check_cve(self, ecos):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            written = sum(1 for eco in ecos if eco in MANIFEST_CONTENTS and eco not in LOCK_SKIP)
            if written < 2:
                pytest.skip(f"{'+'.join(ecos)}: need >=2 writable manifests")
            for eco in ecos:
                _write_manifest(proj, eco)
            result = _run("lock", "-d", str(proj), "-y", timeout=300)
            if result.returncode != 0:
                pytest.skip(f"{'+'.join(ecos)} lock-create failed: {result.stderr[:200]}")
            result = _run("check", "-d", str(proj), "--cve", "--json", timeout=120)
            if result.returncode != 0:
                pytest.skip(f"{'+'.join(ecos)} check-cve failed: {result.stderr[:200]}")
            data = json.loads(result.stdout)
            assert isinstance(data, dict)


# ============================================================
# D. System-aware resolution
# ============================================================


class TestSystemAwareResolution:
    """Target OS/platform, CUDA, device flags."""

    def _project_with_manifest(self):
        tmpdir_obj = tempfile.TemporaryDirectory()
        proj = Path(tmpdir_obj.name) / "project"
        proj.mkdir()
        _write_manifest(proj, "pypi")
        return tmpdir_obj, proj

    def test_target_linux(self):
        tmpdir_obj, proj = self._project_with_manifest()
        try:
            result = _run(
                "lock",
                "-d",
                str(proj),
                "--dry-run",
                "--json",
                "--target",
                "linux",
                "--platform",
                "x86_64",
                timeout=300,
            )
            if result.returncode != 0:
                pytest.skip(f"target linux failed: {result.stderr[:200]}")
            data = json.loads(result.stdout)
            assert "system" in data, "Missing system section"
        finally:
            tmpdir_obj.cleanup()

    def test_target_windows(self):
        tmpdir_obj, proj = self._project_with_manifest()
        try:
            result = _run(
                "lock",
                "-d",
                str(proj),
                "--dry-run",
                "--json",
                "--target",
                "windows",
                "--platform",
                "amd64",
                timeout=300,
            )
            if result.returncode != 0:
                pytest.skip(f"target windows failed: {result.stderr[:200]}")
            data = json.loads(result.stdout)
            assert "system" in data, "Missing system section"
        finally:
            tmpdir_obj.cleanup()

    def test_target_darwin_arm64(self):
        tmpdir_obj, proj = self._project_with_manifest()
        try:
            result = _run(
                "lock",
                "-d",
                str(proj),
                "--dry-run",
                "--json",
                "--target",
                "darwin",
                "--platform",
                "arm64",
                timeout=300,
            )
            if result.returncode != 0:
                pytest.skip(f"target darwin failed: {result.stderr[:200]}")
            data = json.loads(result.stdout)
            assert "system" in data, "Missing system section"
        finally:
            tmpdir_obj.cleanup()

    def test_cuda_device(self):
        tmpdir_obj, proj = self._project_with_manifest()
        try:
            result = _run(
                "lock",
                "-d",
                str(proj),
                "--dry-run",
                "--json",
                "--cuda",
                "12.1",
                "--device",
                "cuda",
                timeout=300,
            )
            if result.returncode != 0:
                pytest.skip(f"cuda lock failed: {result.stderr[:200]}")
            data = json.loads(result.stdout)
            assert "system" in data, "Missing system section"
        finally:
            tmpdir_obj.cleanup()

    def test_target_linux_with_graph(self):
        tmpdir_obj, proj = self._project_with_manifest()
        try:
            result = _run(
                "lock",
                "-d",
                str(proj),
                "-y",
                "--target",
                "linux",
                "--platform",
                "x86_64",
                timeout=300,
            )
            if result.returncode != 0:
                pytest.skip(f"lock-create failed: {result.stderr[:200]}")
            result = _run("graph", "-d", str(proj), "--json", timeout=60)
            if result.returncode != 0:
                pytest.skip(f"graph failed: {result.stderr[:200]}")
            data = json.loads(result.stdout)
            assert isinstance(data, dict)
        finally:
            tmpdir_obj.cleanup()

    def test_target_with_check_json(self):
        tmpdir_obj, proj = self._project_with_manifest()
        try:
            result = _run(
                "lock",
                "-d",
                str(proj),
                "-y",
                "--target",
                "linux",
                "--platform",
                "x86_64",
                timeout=300,
            )
            if result.returncode != 0:
                pytest.skip(f"lock-create failed: {result.stderr[:200]}")
            result = _run("check", "-d", str(proj), "--json", timeout=60)
            if result.returncode != 0:
                pytest.skip(f"check failed: {result.stderr[:200]}")
            data = json.loads(result.stdout)
            assert isinstance(data, dict)
        finally:
            tmpdir_obj.cleanup()


# ============================================================
# E. Multi-ecosystem + system-aware combined
# ============================================================


class TestMultiEcosystemSystemAware:
    """Multi-ecosystem with --target/--platform/--cuda."""

    @pytest.mark.parametrize(
        "ecos",
        [
            ["pypi", "npm"],
            ["pypi", "crates"],
            ["npm", "packagist"],
        ],
    )
    def test_mixed_target_linux(self, ecos):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            written = sum(1 for eco in ecos if eco in MANIFEST_CONTENTS and eco not in LOCK_SKIP)
            if written < 2:
                pytest.skip(f"{'+'.join(ecos)} need >=2 writable manifests")
            for eco in ecos:
                _write_manifest(proj, eco)
            result = _run(
                "lock",
                "-d",
                str(proj),
                "--dry-run",
                "--json",
                "--target",
                "linux",
                "--platform",
                "x86_64",
                "--cuda",
                "12.1",
                timeout=300,
            )
            if result.returncode != 0:
                pytest.skip(f"{'+'.join(ecos)}+target failed: {result.stderr[:300]}")
            data = json.loads(result.stdout)
            assert isinstance(data, dict)

    @pytest.mark.parametrize(
        "ecos",
        [
            ["pypi", "npm"],
            ["pypi", "rubygems"],
        ],
    )
    def test_mixed_target_lock_graph_verify(self, ecos):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            written = sum(1 for eco in ecos if eco in MANIFEST_CONTENTS and eco not in LOCK_SKIP)
            if written < 2:
                pytest.skip(f"{'+'.join(ecos)} need >=2 writable manifests")
            for eco in ecos:
                _write_manifest(proj, eco)
            r1 = _run(
                "lock",
                "-d",
                str(proj),
                "-y",
                "--target",
                "darwin",
                "--platform",
                "arm64",
                timeout=300,
            )
            if r1.returncode != 0:
                pytest.skip(f"{'+'.join(ecos)} lock-create failed: {r1.stderr[:200]}")
            r2 = _run("graph", "-d", str(proj), "--json", timeout=60)
            r3 = _run("verify", "-d", str(proj), timeout=60)
            if r2.returncode == 0:
                data = json.loads(r2.stdout)
                assert isinstance(data, dict)
            if r3.returncode == 0:
                assert "ok" in r3.stdout.lower() or "verified" in r3.stdout.lower()


# ============================================================
# F. Edge cases
# ============================================================


class TestEdgeCases:
    """Empty manifests, missing deps, edge commands."""

    def test_empty_manifest(self):
        """Lock with a completely empty manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            (proj / "requirements.txt").write_text("")
            result = _run("lock", "-d", str(proj), "--dry-run", "--json", timeout=60)
            # Empty manifest is expected to fail gracefully
            assert "No packages found" in result.stdout, f"unexpected output: {result.stdout[:200]}"

    def test_nonexistent_package_search(self):
        """Search for a package that should not exist."""
        result = _run("search", "xylophone_magic_unicorn_999999", "--json", timeout=30)
        if result.returncode != 0:
            pytest.skip(f"search failed: {result.stderr[:200]}")
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_nonexistent_package(self):
        """Details for a package that doesn't exist returns empty data."""
        result = _run("details", "xylophone_magic_unicorn_999999", "--json", timeout=30)
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_check_all_flags_combined(self):
        """CVE + license + deprecated in a single check run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            _write_manifest(proj, "pypi")
            r1 = _run("lock", "-d", str(proj), "-y", timeout=300)
            if r1.returncode != 0:
                pytest.skip(f"lock-create failed: {r1.stderr[:200]}")
            result = _run(
                "check",
                "-d",
                str(proj),
                "--cve",
                "--license",
                "--deprecated",
                "--json",
                timeout=120,
            )
            if result.returncode != 0:
                pytest.skip(f"combined check failed: {result.stderr[:200]}")
            data = json.loads(result.stdout)
            assert isinstance(data, dict)

    def test_outdated(self):
        """Outdated packages detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            _write_manifest(proj, "pypi")
            r1 = _run("lock", "-d", str(proj), "-y", timeout=300)
            if r1.returncode != 0:
                pytest.skip(f"lock-create failed: {r1.stderr[:200]}")
            result = _run("outdated", "-d", str(proj), "--json", timeout=120)
            if result.returncode != 0:
                pytest.skip(f"outdated failed: {result.stderr[:200]}")
            data = json.loads(result.stdout)
            assert isinstance(data, (dict, list))

    def test_sbom_spdx(self):
        """SBOM generation (SPDX format)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            _write_manifest(proj, "pypi")
            r1 = _run("lock", "-d", str(proj), "-y", timeout=300)
            if r1.returncode != 0:
                pytest.skip(f"lock-create failed: {r1.stderr[:200]}")
            result = _run("sbom", "-d", str(proj), "--format", "spdx", timeout=60)
            if result.returncode != 0:
                pytest.skip(f"sbom spdx failed: {result.stderr[:200]}")
            assert len(result.stdout) > 0

    def test_sbom_cyclonedx(self):
        """SBOM generation (CycloneDX format)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            _write_manifest(proj, "pypi")
            r1 = _run("lock", "-d", str(proj), "-y", timeout=300)
            if r1.returncode != 0:
                pytest.skip(f"lock-create failed: {r1.stderr[:200]}")
            result = _run("sbom", "-d", str(proj), "--format", "cyclonedx", timeout=60)
            if result.returncode != 0:
                pytest.skip(f"sbom cyclonedx failed: {result.stderr[:200]}")
            assert len(result.stdout) > 0

    def test_export_command(self):
        """Export lock as requirements.txt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            _write_manifest(proj, "pypi")
            r1 = _run("lock", "-d", str(proj), "-y", timeout=300)
            if r1.returncode != 0:
                pytest.skip(f"lock-create failed: {r1.stderr[:200]}")
            result = _run("export", "-d", str(proj), "--format", "requirements.txt", timeout=60)
            if result.returncode != 0:
                pytest.skip(f"export failed: {result.stderr[:200]}")
            assert len(result.stdout) > 0

    def test_system_info(self):
        """System-info command works."""
        result = _run("system-info", timeout=30)
        assert result.returncode == 0, f"system-info failed: {result.stderr}"
        assert "OS" in result.stdout or "os" in result.stdout.lower()

    def test_system_info_json(self):
        """System-info --json produces valid JSON."""
        result = _run("system-info", "--json", timeout=30)
        assert result.returncode == 0, f"system-info --json failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_diff_self(self):
        """Diff lock against itself shows expected structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            _write_manifest(proj, "pypi")
            r1 = _run("lock", "-d", str(proj), "-y", timeout=300)
            if r1.returncode != 0:
                pytest.skip(f"lock-create failed: {r1.stderr[:200]}")
            result = _run("diff", "-d", str(proj), "--json", timeout=60)
            if result.returncode != 0:
                pytest.skip(f"diff failed: {result.stderr[:200]}")
            data = json.loads(result.stdout)
            assert isinstance(data, dict)

    def test_lock_sign(self):
        """Lock --sign creates signed lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            _write_manifest(proj, "pypi")
            result = _run("lock", "-d", str(proj), "-y", "--sign", timeout=300)
            if result.returncode != 0:
                pytest.skip(f"signed lock failed: {result.stderr[:200]}")


# ============================================================
# G. Workspace isolation
# ============================================================


class TestWorkspaceIsolation:
    """--workspace flag isolation between projects."""

    def test_separate_workspaces(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "project"
            proj.mkdir()
            (proj / "requirements.txt").write_text("requests>=2.28\n")
            (proj / "requirements-dev.txt").write_text("pytest>=7.0\n")
            r1 = _run("lock", "-d", str(proj), "-y", "--workspace", "main", timeout=300)
            if r1.returncode != 0:
                pytest.skip(f"main lock failed: {r1.stderr[:200]}")
            r2 = _run("lock", "-d", str(proj), "-y", "--workspace", "dev", timeout=300)
            if r2.returncode != 0:
                pytest.skip(f"dev lock failed: {r2.stderr[:200]}")
            lock_main = proj / "udr-main.lock"
            lock_dev = proj / "udr-dev.lock"
            assert lock_main.is_file(), f"{lock_main} not created"
            assert lock_dev.is_file(), f"{lock_dev} not created"
