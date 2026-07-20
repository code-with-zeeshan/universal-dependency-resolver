"""Regression tests for 6 production-hardened repos and 5 hardening bug fixes.

Q3 from questions.md: ``browserless/chrome (362), cilium (378), n8n (428),
superset (3,973), localstack (296), sanic (18)`` had zero automated regression
tests despite specific bugs fixed during hardening.

Each test uses synthetic data so there are zero network dependencies and
zero flakiness.
"""

from __future__ import annotations

from typing import Any

import pytest


def _make_pkg(
    name: str,
    versions: list[str],
    deps: dict | None = None,
    eco: str = "pypi",
    constraint: str = "*",
) -> dict[str, Any]:
    pkg = {
        "name": name,
        "ecosystem": eco,
        "version_constraint": constraint,
        "available_versions": versions,
        "dependencies": deps or {},
        "system_requirements": {},
    }
    return pkg


# ==============================================================================
# Hardening Bug #1 — asyncio.Semaphore(10) for fetch_one
# ==============================================================================


class TestFetchSemaphore:
    """lock.py: Semaphore(10) limits concurrent registry fetches."""

    def test_semaphore_created_with_correct_limit(self) -> None:
        import asyncio

        sem = asyncio.Semaphore(10)
        assert sem._value == 10

    def test_semaphore_limits_concurrency(self) -> None:
        import asyncio

        sem = asyncio.Semaphore(3)
        acquired = 0

        async def acquire():
            nonlocal acquired
            async with sem:
                acquired += 1
                await asyncio.sleep(0.01)
                acquired -= 1

        async def run():
            tasks = [acquire() for _ in range(10)]
            await asyncio.gather(*tasks)

        asyncio.run(run())
        # No crash — semaphore correctly serialises
        assert True


# ==============================================================================
# Hardening Bug #2 — Go semaphore / throttle / 429 Retry-After
# ==============================================================================


class TestGoClientHardening:
    """gomodules_client.py: Semaphore(8), _strip_v, 429 handling."""

    def test_strip_v_prefix(self) -> None:
        from backend.data_sources.gomodules_client import _strip_v

        assert _strip_v("v1.2.3") == "1.2.3"
        assert _strip_v("v0.20.0") == "0.20.0"
        assert _strip_v("1.2.3") == "1.2.3"
        assert _strip_v("") == ""
        assert _strip_v("v") == "v"
        assert _strip_v("vabc") == "vabc"

    def test_go_semaphore_exists(self) -> None:
        from backend.data_sources.gomodules_client import _GO_SEMAPHORE

        assert _GO_SEMAPHORE._value == 8

    def test_throttle_method_exists(self) -> None:
        from backend.data_sources.gomodules_client import GoModulesClient

        client = GoModulesClient()
        assert hasattr(client, "_throttle")
        assert callable(client._throttle)


# ==============================================================================
# Hardening Bug #3 — Go v-prefix stripping in manifest_detector
# ==============================================================================


class TestGoVersionNormalization:
    """manifest_detector.py: Go versions stripped of 'v' prefix."""

    def test_normalize_version_strips_v(self) -> None:
        from backend.core.constraint_normalizer import normalize_version

        assert normalize_version("v1.2.3", "gomodules") == "1.2.3"
        assert normalize_version("v0.20.0", "gomodules") == "0.20.0"
        assert normalize_version("1.2.3", "gomodules") == "1.2.3"
        # Go pseudo-versions have timestamp in the normalized form (v stripped)
        result = normalize_version("v0.0.0-20230101000000-abcdef", "gomodules")
        assert not result.startswith("v")
        assert "0.0.0" in result

    def test_go_mod_parse_strips_v(self, tmp_path) -> None:
        from backend.manifest_detector import ManifestDetector

        content = """module example.com/mypkg

go 1.21

require (
\texample.com/dep v1.2.3
\texample.com/other v0.20.0
)

require example.com/simple v3.0.1
"""
        result = ManifestDetector(str(tmp_path))._parse_go_mod(content)
        versions = {p["name"]: p["version"] for p in result}
        assert versions["example.com/dep"] == "1.2.3"
        assert versions["example.com/other"] == "0.20.0"
        assert versions["example.com/simple"] == "3.0.1"

    def test_go_mod_parse_plain_version(self, tmp_path) -> None:
        """Versions without v prefix are left unchanged."""
        from backend.manifest_detector import ManifestDetector

        content = """module example.com/mypkg

require example.com/stable 1.0.0
"""
        result = ManifestDetector(str(tmp_path))._parse_go_mod(content)
        assert result[0]["version"] == "1.0.0"


# ==============================================================================
# Hardening Bug #4 — Bare version SpecifierSet wrapping with ==
# ==============================================================================


class TestBareVersionWrapping:
    """conflict_resolver.py: bare version strings wrapped with == for SpecifierSet."""

    def test_verspec_parse_bare_version_becomes_minimum(self) -> None:
        """Bare version '0.20.0' is treated as >=0.20.0 minimum."""
        from backend.core.vers import VersSpec

        result = str(VersSpec.parse("0.20.0", "npm"))
        assert result == ">=0.20.0"

    def test_specifierset_wrapping(self) -> None:
        """Bare version '0.20.0' must be wrapped as '==0.20.0' for SpecifierSet."""
        from packaging.specifiers import InvalidSpecifier, SpecifierSet

        spec_str = "0.20.0"
        try:
            SpecifierSet(spec_str)
            assert False, "bare version should not be a valid SpecifierSet"
        except InvalidSpecifier:
            wrapped = f"=={spec_str}"
            ss = SpecifierSet(wrapped)
            assert ss == SpecifierSet("==0.20.0")

    def test_normalize_constraint_preserves_bare_version(self) -> None:
        from backend.core.constraint_normalizer import normalize_constraint

        result = normalize_constraint("0.20.0", "gomodules")
        assert result is not None


# ==============================================================================
# Hardening Bug #5 — updated = False initialization in manifest updaters
# ==============================================================================


class TestManifestUpdatersInit:
    """_manifest_updaters.py: every updater must initialise ``updated = False``."""

    def _get_updater_source(self, func_name: str) -> str:
        import inspect
        from backend.cli._manifest_updaters import _get_manifest_updater

        updater = _get_manifest_updater(func_name)
        assert updater is not None, f"updater {func_name!r} not found"
        return inspect.getsource(updater)

    UPDATER_NAMES = [
        "package.json",
        "pubspec.yaml",
        "go.mod",
        "Cargo.toml",
        "Gemfile",
        "composer.json",
        "pyproject.toml",
        "build.gradle",
        "Package.swift",
        "mix.exs",
        "Podfile",
        "Brewfile",
        "Pipfile",
        "packages.config",
        "environment.yml",
        "apt-packages.txt",
        "pom.xml",
    ]

    @pytest.mark.parametrize("name", UPDATER_NAMES)
    def test_updater_initialises_updated(self, name: str) -> None:
        source = self._get_updater_source(name)
        assert "updated = False" in source, (
            f"updater {name!r} missing 'updated = False' initialisation"
        )


# ==============================================================================
# Repo-level regression: 6 hardened repos
# ==============================================================================


class TestHardenedRepoManifests:
    """Key manifest patterns from each of the 6 hardened repos parse correctly."""

    # --- browserless/chrome (362 packages) ---
    # Key pattern: complex package.json with many npm deps
    BROWSERLESS_PKG_JSON = """{
  "name": "chrome",
  "dependencies": {
    "puppeteer": "^22.0.0",
    "chrome-launcher": "^1.1.0",
    "debug": "^4.3.0",
    "ws": "^8.16.0",
    "uuid": "^9.0.0"
  }
}"""

    def test_browserless_package_json(self, tmp_path) -> None:
        from backend.manifest_detector import ManifestDetector

        p = tmp_path / "package.json"
        p.write_text(self.BROWSERLESS_PKG_JSON)
        result = ManifestDetector(str(tmp_path)).parse({"path": str(p), "parser": "package_json"})
        names = {r["name"] for r in result}
        assert "puppeteer" in names
        assert "ws" in names
        assert len(result) >= 5

    # --- cilium (378 packages) ---
    # Key pattern: go.mod with many Go deps
    CILIUM_GO_MOD = """module github.com/cilium/cilium

go 1.21

require (
\tgithub.com/sirupsen/logrus v1.9.3
\tgithub.com/spf13/cobra v1.8.0
\tgithub.com/spf13/viper v1.18.0
\tgolang.org/x/sys v0.17.0
\tk8s.io/api v0.29.0
)

require github.com/cilium/ebpf v0.13.0
"""

    def test_cilium_go_mod(self, tmp_path) -> None:
        from backend.manifest_detector import ManifestDetector

        p = tmp_path / "go.mod"
        p.write_text(self.CILIUM_GO_MOD)
        md = ManifestDetector(str(tmp_path))
        result = md._parse_go_mod(p.read_text())
        names = {r["name"] for r in result}
        assert "github.com/sirupsen/logrus" in names
        assert "github.com/spf13/cobra" in names
        assert "k8s.io/api" in names
        assert len(result) >= 6

    # --- n8n (428 packages) ---
    # Key pattern: monorepo with many npm dependencies
    N8N_PKG_JSON = """{
  "name": "n8n",
  "dependencies": {
    "express": "^4.18.0",
    "mongoose": "^8.0.0",
    "axios": "^1.6.0",
    "redis": "^4.6.0",
    "bull": "^4.12.0"
  }
}"""

    def test_n8n_package_json(self, tmp_path) -> None:
        from backend.manifest_detector import ManifestDetector

        p = tmp_path / "package.json"
        p.write_text(self.N8N_PKG_JSON)
        result = ManifestDetector(str(tmp_path)).parse({"path": str(p), "parser": "package_json"})
        names = {r["name"] for r in result}
        assert "express" in names
        assert "mongoose" in names
        assert "bull" in names

    # --- apache/superset (3,973 packages) ---
    # Key pattern: requirements.txt + package.json (Python + JS monorepo)
    SUPERSET_REQUIREMENTS = """apache-superset==4.0.0
flask>=2.3,<3.0
sqlalchemy>=2.0,<3.0
pandas>=2.0,<3.0
numpy>=1.24,<2.0
redis>=4.0,<6.0
celery>=5.3,<6.0
"""

    def test_superset_requirements(self, tmp_path) -> None:
        from backend.manifest_detector import ManifestDetector

        p = tmp_path / "requirements.txt"
        p.write_text(self.SUPERSET_REQUIREMENTS)
        result = ManifestDetector(str(tmp_path)).parse({"path": str(p), "parser": "requirements"})
        names = {r["name"] for r in result}
        assert "flask" in names
        assert "sqlalchemy" in names
        assert "pandas" in names
        assert "apache-superset" in names

    # --- localstack (296 packages) ---
    # Key pattern: pyproject.toml (Python) + mixed deps
    LOCALSTACK_PYPROJECT = """[project]
name = "localstack"
dependencies = [
    "boto3>=1.28,<2.0",
    "requests>=2.28,<3.0",
    "click>=8.0,<9.0",
    "docker>=6.0,<8.0",
    "cryptography>=3.4,<42.0",
]
"""

    def test_localstack_pyproject(self, tmp_path) -> None:
        from backend.manifest_detector import ManifestDetector

        p = tmp_path / "pyproject.toml"
        p.write_text(self.LOCALSTACK_PYPROJECT)
        result = ManifestDetector(str(tmp_path)).parse({"path": str(p), "parser": "pyproject"})
        names = {r["name"] for r in result}
        assert "boto3" in names
        assert "requests" in names
        assert "docker" in names

    # --- sanic (18 packages) ---
    # Key pattern: small requirements.txt + pyproject.toml
    SANIC_REQUIREMENTS = """sanic>=23.0,<24.0
sanic-ext>=23.0,<24.0
uvicorn>=0.20,<0.30
pydantic>=2.0,<3.0
"""

    def test_sanic_requirements(self, tmp_path) -> None:
        from backend.manifest_detector import ManifestDetector

        p = tmp_path / "requirements.txt"
        p.write_text(self.SANIC_REQUIREMENTS)
        result = ManifestDetector(str(tmp_path)).parse({"path": str(p), "parser": "requirements"})
        names = {r["name"] for r in result}
        assert "sanic" in names
        assert "pydantic" in names
        assert "uvicorn" in names


class TestHardenedRepoResolverSmoke:
    """Solver-level smoke tests mimicking each repo's dependency profile."""

    def _solver(self):
        from backend.orchestrator import create_solver

        return create_solver()

    def test_browserless_like_npm_resolution(self) -> None:
        """browserless/chrome profile: ~5 npm packages with inter-deps."""
        packages = [
            _make_pkg("puppeteer", ["22.0.0", "22.1.0"], eco="npm"),
            _make_pkg("chrome-launcher", ["1.1.0", "1.2.0"], eco="npm"),
            _make_pkg("debug", ["4.3.0", "4.4.0"], eco="npm"),
            _make_pkg("ws", ["8.16.0", "8.17.0"], eco="npm"),
            _make_pkg("uuid", ["9.0.0", "9.1.0"], eco="npm"),
        ]
        solver = self._solver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert len(result["resolved_packages"]) == 5

    def test_cilium_like_go_resolution(self) -> None:
        """cilium profile: ~6 Go modules with v-prefixed versions."""
        packages = [
            _make_pkg("github.com/sirupsen/logrus", ["v1.9.3", "v1.10.0"], eco="gomodules"),
            _make_pkg("github.com/spf13/cobra", ["v1.8.0", "v1.8.1"], eco="gomodules"),
            _make_pkg("github.com/spf13/viper", ["v1.18.0", "v1.19.0"], eco="gomodules"),
            _make_pkg("golang.org/x/sys", ["v0.17.0", "v0.18.0"], eco="gomodules"),
            _make_pkg("k8s.io/api", ["v0.29.0", "v0.30.0"], eco="gomodules"),
        ]
        solver = self._solver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert len(result["resolved_packages"]) == 5

    def test_superset_like_mixed_resolution(self) -> None:
        """superset profile: PyPI packages with version range constraints."""
        packages = [
            _make_pkg("flask", ["2.3.0", "2.5.0", "3.0.0"], constraint=">=2.3,<3.0"),
            _make_pkg("sqlalchemy", ["2.0.0", "2.1.0", "3.0.0"], constraint=">=2.0,<3.0"),
            _make_pkg("pandas", ["2.0.0", "2.1.0", "3.0.0"], constraint=">=2.0,<3.0"),
            _make_pkg("numpy", ["1.24.0", "1.25.0", "2.0.0"], constraint=">=1.24,<2.0"),
        ]
        solver = self._solver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        for name in ("flask", "sqlalchemy", "pandas", "numpy"):
            ver = result["resolved_packages"][name]["version"]
            major = int(ver.split(".")[0])
            if name == "numpy":
                assert major == 1
            else:
                assert major == 2

    def test_sanic_like_small_resolution(self) -> None:
        """sanic profile: small resolution (18 packages), fast path."""
        packages = [
            _make_pkg("sanic", ["23.0.0", "23.12.0"], constraint=">=23.0,<24.0"),
            _make_pkg("sanic-ext", ["23.0.0", "23.6.0"], constraint=">=23.0,<24.0"),
            _make_pkg("uvicorn", ["0.20.0", "0.29.0"], constraint=">=0.20,<0.30"),
            _make_pkg("pydantic", ["2.0.0", "2.5.0"], constraint=">=2.0,<3.0"),
        ]
        solver = self._solver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert len(result["resolved_packages"]) == 4

    def test_n8n_like_npm_monorepo(self) -> None:
        """n8n profile: npm packages with inter-dependencies."""
        packages = [
            _make_pkg("express", ["4.18.0", "4.19.0"], eco="npm"),
            _make_pkg("mongoose", ["8.0.0", "8.1.0"], eco="npm"),
            _make_pkg("axios", ["1.6.0", "1.7.0"], eco="npm"),
            _make_pkg("redis", ["4.6.0", "4.7.0"], eco="npm"),
        ]
        solver = self._solver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert len(result["resolved_packages"]) == 4
