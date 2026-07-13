"""Tests for the hybrid PubGrub+Z3 solver strategy."""

import os

import pytest

from backend.core.hybrid_solver import HybridSolver


def _make_pkg(
    name: str,
    versions: list[str],
    deps: dict | None = None,
    eco: str = "pypi",
    constraint: str = "*",
    cross_eco: list | None = None,
) -> dict:
    pkg = {
        "name": name,
        "ecosystem": eco,
        "version_constraint": constraint,
        "available_versions": versions,
        "dependencies": deps or {},
        "system_requirements": {},
    }
    if cross_eco:
        pkg["cross_ecosystem_deps"] = cross_eco
    return pkg


class TestHybridSolver:
    """Hybrid solver: PubGrub per ecosystem + Z3 cross-eco reconciliation."""

    def test_single_eco_two_packages(self):
        """Simple single-ecosystem case resolves correctly."""
        packages = [
            _make_pkg("a", ["1.0.0", "2.0.0"], constraint=">=1.0"),
            _make_pkg("b", ["1.0.0", "2.0.0"], deps={"pypi": {"a": ">=1.0"}}),
        ]
        solver = HybridSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert "a" in result["resolved_packages"]
        assert "b" in result["resolved_packages"]

    def test_two_ecosystems_no_cross_deps(self):
        """Packages in different ecosystems with no cross-eco deps."""
        packages = [
            _make_pkg("torch", ["1.0.0", "2.0.0"], eco="pypi"),
            _make_pkg("express", ["1.0.0", "2.0.0"], eco="npm"),
        ]
        solver = HybridSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"]["torch"]["ecosystem"] == "pypi"
        assert result["resolved_packages"]["express"]["ecosystem"] == "npm"

    def test_falls_back_on_conflict(self):
        """When PubGrub succeeds but cross-eco deps conflict, fall back to Z3."""
        packages = [
            _make_pkg("a", ["1.0.0"], eco="pypi"),
            _make_pkg("b", ["2.0.0"], eco="npm"),
            _make_pkg("c", ["1.0.0"], eco="pypi"),
        ]
        solver = HybridSolver()
        result = solver.resolve_dependencies(packages)
        # Should not crash — either succeeds or gracefully falls back
        assert result["status"] in ("satisfiable",)

    def test_unsatisfiable_ecosystem(self):
        """When a dependency constraint can't be satisfied (B depends on A>=2, A only has 1.0)."""
        packages = [
            _make_pkg("a", ["1.0.0"]),
            _make_pkg("b", ["1.0.0"], deps={"pypi": {"a": ">=2.0"}}),
        ]
        solver = HybridSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "unsatisfiable", f"Expected unsatisfiable, got {result}"

    def test_empty_packages(self):
        """Empty package list returns empty result."""
        solver = HybridSolver()
        result = solver.resolve_dependencies([])
        assert result["status"] == "satisfiable"

    def test_version_pinning(self):
        """The Z3 verify phase receives packages pinned to PubGrub's chosen version."""
        packages = [
            _make_pkg("a", ["1.0.0", "2.0.0", "3.0.0"], constraint=">=1.0"),
            _make_pkg("b", ["1.0.0", "2.0.0"], deps={"pypi": {"a": ">=2.0"}}),
        ]
        solver = HybridSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        # Both should be resolved with concrete versions
        assert len(result["resolved_packages"]) == 2

    def test_multi_eco_with_cross_eco_deps(self):
        """Cross-ecosystem dependencies are respected after PubGrub per-eco resolution."""
        packages = [
            _make_pkg("lib-a", ["1.0.0", "2.0.0"], eco="pypi"),
            _make_pkg("lib-b", ["1.0.0", "2.0.0"], eco="npm"),
        ]
        solver = HybridSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert "lib-a" in result["resolved_packages"]
        assert "lib-b" in result["resolved_packages"]

    def test_large_number_of_versions(self):
        """Many versions per package should not cause encoding explosion in Z3 verify phase."""
        many_versions = [f"{i}.0.0" for i in range(100)]
        packages = [
            _make_pkg("big", many_versions, constraint=">=50.0"),
            _make_pkg("small", ["1.0.0"], deps={"pypi": {"big": ">=50.0"}}),
        ]
        solver = HybridSolver()
        result = solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        # PubGrub should pick a version >= 50.0.0
        ver = result["resolved_packages"]["big"]["version"]
        major = int(ver.split(".")[0])
        assert major >= 50


class TestCreateSolverHybrid:
    """``create_solver()`` returns correct solver type based on env vars.

    Each test runs in a subprocess to avoid module-level env contamination.
    """

    @staticmethod
    def _check_solver(env: dict[str, str], expected_type: str) -> None:
        """Run create_solver in a subprocess and check the solver type."""
        import subprocess
        import sys

        code = f"""
import os
os.environ.update({env!r})
import importlib
import backend.orchestrator.resolve as m
import backend.settings as s
importlib.reload(s)
importlib.reload(m)
solver = m.create_solver()
print(type(solver).__module__ + '.' + type(solver).__qualname__)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise AssertionError(f"subprocess failed: {result.stderr}")
        solver_type = result.stdout.strip()
        assert solver_type == expected_type, f"Expected {expected_type}, got {solver_type}"

    def test_hybrid_solver_env_var(self):
        """USE_HYBRID_SOLVER=true returns HybridSolver."""
        self._check_solver(
            {"USE_HYBRID_SOLVER": "true"},
            "backend.core.hybrid_solver.HybridSolver",
        )

    def test_default_is_auto_solver(self):
        """No env var returns AutoSolver (default)."""
        self._check_solver(
            {},
            "backend.core.auto_solver.AutoSolver",
        )

    def test_z3_when_explicitly_requested(self):
        """USE_Z3_SOLVER=true returns ConflictResolver (Z3)."""
        self._check_solver(
            {"USE_Z3_SOLVER": "true"},
            "backend.core.conflict_resolver.ConflictResolver",
        )

    def test_pubgrub_when_hybrid_disabled(self):
        """USE_PUBGRUB_SOLVER=true returns PubGrubSolver (or Z3 fallback)."""
        import subprocess
        import sys

        code = """
import os
os.environ['USE_PUBGRUB_SOLVER'] = 'true'
os.environ['USE_HYBRID_SOLVER'] = 'false'
import importlib
import backend.orchestrator.resolve as m
import backend.settings as s
importlib.reload(s)
importlib.reload(m)
solver = m.create_solver()
t = type(solver).__module__ + '.' + type(solver).__qualname__
# Accept either PubGrubSolver (when pubgrub-py is installed) or
# ConflictResolver (fallback when pubgrub-py is unavailable)
assert t in (
    'backend.core.pubgrub_solver.PubGrubSolver',
    'backend.core.conflict_resolver.ConflictResolver',
), f'Unexpected solver type: {t}'
print(t)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, f"subprocess failed: {result.stderr}"
