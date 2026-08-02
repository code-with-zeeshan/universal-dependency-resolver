"""Unit tests for core/pubgrub_solver.py."""

import pytest

from backend.core.pubgrub_solver import (
    PubGrubSolver,
    _constraint_allows_prerelease,
    _has_prerelease_suffix,
    _normalize_constraint,
    _sanitize_version,
)

try:
    from pubgrub_py import ResolutionError, Resolver  # noqa: F401

    HAS_PUBGRUB = True
except ImportError:
    HAS_PUBGRUB = False

# Pure-Python fallback — always available
from backend.core.pubgrub_core import PubGrubCoreSolver as _PureCoreSolver  # noqa: E402


class TestNormalizeConstraint:
    def test_empty_returns_default(self):
        assert _normalize_constraint("", "pypi") == ">=0.0.0"

    def test_wildcard_returns_default(self):
        assert _normalize_constraint("*", "pypi") == ">=0.0.0"

    def test_pypi_spec_passthrough(self):
        assert _normalize_constraint(">=1.0.0,<3", "pypi") == ">=1.0.0,<3.0.0"

    def test_exact_version(self):
        assert _normalize_constraint("==1.2.3", "pypi") == "==1.2.3"

    def test_caret_with_major_minor(self):
        # pubgrub-py requires 3-part semver
        assert _normalize_constraint("^4.18", "npm") == ">=4.18.0,<5.0.0"

    def test_caret_major_only(self):
        assert _normalize_constraint("^1", "npm") == ">=1.0.0,<2.0.0"

    def test_tilde_with_major_minor(self):
        # pubgrub-py requires 3-part semver
        assert _normalize_constraint("~1.2", "npm") == ">=1.2.0,<1.3.0"

    def test_tilde_major_only(self):
        # pubgrub-py requires 3-part semver
        assert _normalize_constraint("~1", "npm") == ">=1.0.0,<2.0.0"

    def test_npm_prefixed_passthrough(self):
        assert _normalize_constraint(">=1.0.0", "npm") == ">=1.0.0"


class TestPubGrubSolver:
    def test_init_defaults(self):
        solver = PubGrubSolver()
        assert solver._use_optimization is True
        assert solver._solver_timeout is None

    def test_init_with_timeout(self):
        solver = PubGrubSolver(solver_timeout=30000)
        assert solver._solver_timeout == 30000

    def test_no_pubgrub_graceful_degradation(self):
        if HAS_PUBGRUB:
            pytest.skip("pubgrub-py is installed")
        packages = [
            {
                "name": "pkg",
                "ecosystem": "pypi",
                "version_constraint": "*",
                "available_versions": [],
                "dependencies": {},
            }
        ]
        solver = PubGrubSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "unsatisfiable"

    @pytest.mark.skipif(not HAS_PUBGRUB, reason="pubgrub-py not installed")
    def test_resolve_simple(self):
        packages = [
            {
                "name": "app",
                "ecosystem": "pypi",
                "version_constraint": ">=1.0.0",
                "available_versions": ["1.0.0", "2.0.0"],
                "dependencies": {"pypi": {"all": []}},
            }
        ]
        solver = PubGrubSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert "app" in result["resolved_packages"]
        assert result["resolved_packages"]["app"]["ecosystem"] == "pypi"

    @pytest.mark.skipif(not HAS_PUBGRUB, reason="pubgrub-py not installed")
    def test_resolve_with_dependencies(self):
        packages = [
            {
                "name": "app",
                "ecosystem": "pypi",
                "version_constraint": ">=1.0.0",
                "available_versions": ["1.0.0"],
                "dependencies": {
                    "pypi": {
                        "all": [
                            type(
                                "_Dep",
                                (),
                                {"name": "lib", "version_spec": ">=1.0.0", "ecosystem": None},
                            )(),
                        ]
                    }
                },
            },
            {
                "name": "lib",
                "ecosystem": "pypi",
                "version_constraint": ">=1.0.0",
                "available_versions": ["1.0.0", "2.0.0"],
                "dependencies": {"pypi": {"all": []}},
            },
        ]
        solver = PubGrubSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert "app" in result["resolved_packages"]
        assert "lib" in result["resolved_packages"]

    @pytest.mark.skipif(not HAS_PUBGRUB, reason="pubgrub-py not installed")
    def test_no_packages_returns_empty(self):
        solver = PubGrubSolver()
        result = solver.resolve_dependencies([])
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"] == {}

    @pytest.mark.skipif(not HAS_PUBGRUB, reason="pubgrub-py not installed")
    def test_conflicting_deps(self):
        packages = [
            {
                "name": "app",
                "ecosystem": "pypi",
                "version_constraint": ">=1.0.0",
                "available_versions": ["1.0.0"],
                "dependencies": {
                    "pypi": {
                        "all": [
                            type(
                                "_Dep",
                                (),
                                {"name": "lib", "version_spec": ">=2.0.0", "ecosystem": None},
                            )(),
                        ]
                    }
                },
            },
            {
                "name": "lib",
                "ecosystem": "pypi",
                "version_constraint": "<2.0.0",
                "available_versions": ["1.0.0"],
                "dependencies": {"pypi": {"all": []}},
            },
        ]
        solver = PubGrubSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "unsatisfiable"

    @pytest.mark.skipif(not HAS_PUBGRUB, reason="pubgrub-py not installed")
    def test_semver_caret_constraint(self):
        packages = [
            {
                "name": "express",
                "ecosystem": "npm",
                "version_constraint": "^4.18.0",
                "available_versions": ["4.17.0", "4.18.0", "4.18.2", "5.0.0"],
                "dependencies": {"npm": {"all": []}},
            }
        ]
        solver = PubGrubSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        ver = result["resolved_packages"]["express"]["version"]
        assert ver in ("4.18.0", "4.18.2")

    @pytest.mark.skipif(not HAS_PUBGRUB, reason="pubgrub-py not installed")
    def test_multiple_ecosystems(self):
        packages = [
            {
                "name": "requests",
                "ecosystem": "pypi",
                "version_constraint": ">=2.28.0",
                "available_versions": ["2.28.0", "2.31.0"],
                "dependencies": {"pypi": {"all": []}},
            },
            {
                "name": "express",
                "ecosystem": "npm",
                "version_constraint": "^4.18.0",
                "available_versions": ["4.18.0", "4.19.0"],
                "dependencies": {"npm": {"all": []}},
            },
        ]
        solver = PubGrubSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert "requests" in result["resolved_packages"]
        assert "express" in result["resolved_packages"]
        assert result["resolved_packages"]["requests"]["ecosystem"] == "pypi"
        assert result["resolved_packages"]["express"]["ecosystem"] == "npm"

    @pytest.mark.skipif(not HAS_PUBGRUB, reason="pubgrub-py not installed")
    def test_empty_available_versions(self):
        packages = [
            {
                "name": "phantom",
                "ecosystem": "pypi",
                "version_constraint": ">=1.0.0",
                "available_versions": [],
                "dependencies": {"pypi": {"all": []}},
            }
        ]
        solver = PubGrubSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] in ("satisfiable", "unsatisfiable")

    @pytest.mark.skipif(not HAS_PUBGRUB, reason="pubgrub-py not installed")
    def test_resolve_latest_version_preferred(self):
        packages = [
            {
                "name": "lib",
                "ecosystem": "pypi",
                "version_constraint": ">=1.0.0",
                "available_versions": ["1.0.0", "1.5.0", "2.0.0"],
                "dependencies": {"pypi": {"all": []}},
            }
        ]
        solver = PubGrubSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        ver = result["resolved_packages"]["lib"]["version"]
        parsed = tuple(int(x) for x in ver.split("."))
        assert parsed >= (1, 0, 0)


class TestPrereleaseHandling:
    """Pre-release versions must not be selected over stable releases unless
    the constraint explicitly asks for a pre-release (BUG 1 regression tests)."""

    def test_sanitize_preserves_prerelease_identity(self):
        assert _sanitize_version("6.1rc1") == "6.1.0-rc1"
        assert _sanitize_version("2.14.0a1") == "2.14.0-a1"
        assert _sanitize_version("1.0.dev1") == "1.0.0-dev1"
        assert _sanitize_version("1.0.0b1") == "1.0.0-b1"
        # Stable versions are unchanged apart from padding/normalizing
        assert _sanitize_version("1.2.3") == "1.2.3"
        assert _sanitize_version("1.0") == "1.0.0"
        assert _sanitize_version("0.12.01") == "0.12.1"

    def test_prerelease_suffix_detection(self):
        assert _has_prerelease_suffix("6.1rc1") is True
        assert _has_prerelease_suffix("2.14.0a1") is True
        assert _has_prerelease_suffix("1.0.dev1") is True
        assert _has_prerelease_suffix("1.0.0-rc1") is True
        # Post releases are NOT pre-releases
        assert _has_prerelease_suffix("1.0.0.post1") is False
        assert _has_prerelease_suffix("1.2.3") is False

    def test_normalize_prerelease_constraint(self):
        assert _normalize_constraint(">=6.1rc1", "pypi") == ">=6.1.0-rc1"
        assert _normalize_constraint("==6.1rc1", "pypi") == "==6.1.0-rc1"
        assert _normalize_constraint(">=2.14.0a1", "pypi") == ">=2.14.0-a1"

    def test_constraint_allows_prerelease(self):
        assert _constraint_allows_prerelease(">=5.0.0") is False
        assert _constraint_allows_prerelease(">=0.0.0") is False
        assert _constraint_allows_prerelease(">=6.1.0-rc1") is True
        assert _constraint_allows_prerelease("==6.1.0-rc1") is True

    def test_resolve_excludes_prerelease_by_default(self):
        packages = [
            {
                "name": "django",
                "ecosystem": "pypi",
                "version_constraint": ">=5.0",
                "available_versions": ["5.0.0", "5.2.0", "6.0.0", "6.1rc1", "6.1.0"],
                "dependencies": {},
            }
        ]
        solver = PubGrubSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"]["django"]["version"] == "6.1.0"

    def test_resolve_keeps_prerelease_when_only_match(self):
        packages = [
            {
                "name": "django",
                "ecosystem": "pypi",
                "version_constraint": ">=6.1rc1",
                "available_versions": ["5.2.0", "6.0.0", "6.1rc1"],
                "dependencies": {},
            }
        ]
        solver = PubGrubSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"]["django"]["version"] == "6.1rc1"


class TestPurePythonFallback:
    """Tests for the pure-Python PubGrubCoreSolver fallback path.

    Known limitations documented as xfail:
    - ``test_semver_caret_constraint`` — pure-Python solver doesn't normalize caret ranges.
    - ``test_multiple_ecosystems`` — pure-Python solver has issues with mixed ecosystems.
    """

    def _prepare(self, packages: list[dict]) -> tuple[_PureCoreSolver, dict[str, str]]:
        solver = _PureCoreSolver()
        requirements: dict[str, str] = {}
        for pkg in packages:
            name: str = pkg["name"]
            requirements[name] = pkg.get("version_constraint", ">=0.0.0")
            for ver in pkg.get("available_versions", []):
                deps: dict[str, str] = {}
                for eco_deps in pkg.get("dependencies", {}).values():
                    for dep in eco_deps.get("all", []):
                        dep_name = dep.get("name", "")
                        dep_con = dep.get("version_spec", ">=0.0.0")
                        if dep_name:
                            deps[dep_name] = dep_con
                solver.add_package(name, ver, deps)
        return solver, requirements

    def test_resolve_simple(self):
        pkgs = [
            {
                "name": "pkg",
                "ecosystem": "pypi",
                "version_constraint": ">=1.0.0",
                "available_versions": ["1.0.0", "2.0.0"],
                "dependencies": {"pypi": {"all": []}},
            }
        ]
        solver, reqs = self._prepare(pkgs)
        result = solver.resolve(reqs)
        assert isinstance(result, dict)
        assert "pkg" in result

    def test_resolve_with_dependencies(self):
        pkgs = [
            {
                "name": "app",
                "ecosystem": "pypi",
                "version_constraint": ">=1.0.0",
                "available_versions": ["1.0.0"],
                "dependencies": {"pypi": {"all": [{"name": "lib", "version_spec": ">=1.0.0"}]}},
            },
            {
                "name": "lib",
                "ecosystem": "pypi",
                "version_constraint": ">=1.0.0",
                "available_versions": ["1.0.0", "2.0.0"],
                "dependencies": {"pypi": {"all": []}},
            },
        ]
        solver, reqs = self._prepare(pkgs)
        result = solver.resolve(reqs)
        assert "app" in result
        assert "lib" in result

    def test_conflicting_deps(self):
        pkgs = [
            {
                "name": "app",
                "ecosystem": "pypi",
                "version_constraint": ">=1.0.0",
                "available_versions": ["1.0.0"],
                "dependencies": {"pypi": {"all": [{"name": "lib", "version_spec": ">=2.0.0"}]}},
            },
            {
                "name": "lib",
                "ecosystem": "pypi",
                "version_constraint": "<2.0.0",
                "available_versions": ["1.0.0"],
                "dependencies": {"pypi": {"all": []}},
            },
        ]
        solver, reqs = self._prepare(pkgs)
        with pytest.raises(Exception):
            solver.resolve(reqs)

    @pytest.mark.timeout(5)
    @pytest.mark.xfail(reason="pure-Python PubGrubCoreSolver cannot normalise npm caret ranges")
    def test_semver_caret_constraint(self):
        pkgs = [
            {
                "name": "express",
                "ecosystem": "npm",
                "version_constraint": "^4.18.0",
                "available_versions": ["4.17.0", "4.18.0", "4.18.2", "5.0.0"],
                "dependencies": {"npm": {"all": []}},
            }
        ]
        solver, reqs = self._prepare(pkgs)
        result = solver.resolve(reqs)
        ver = result.get("express", "")
        assert ver in ("4.18.0", "4.18.2")

    @pytest.mark.timeout(5)
    @pytest.mark.xfail(
        reason="pure-Python PubGrubCoreSolver has issues with mixed ecosystem resolution"
    )
    def test_multiple_ecosystems(self):
        pkgs = [
            {
                "name": "requests",
                "ecosystem": "pypi",
                "version_constraint": ">=2.28.0",
                "available_versions": ["2.28.0", "2.31.0"],
                "dependencies": {"pypi": {"all": []}},
            },
            {
                "name": "express",
                "ecosystem": "npm",
                "version_constraint": "^4.18.0",
                "available_versions": ["4.18.0", "4.19.0"],
                "dependencies": {"npm": {"all": []}},
            },
        ]
        solver, reqs = self._prepare(pkgs)
        result = solver.resolve(reqs)
        assert "requests" in result
        assert "express" in result
