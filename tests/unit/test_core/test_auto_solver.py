"""Tests for AutoSolver — Automated solver selection by profiling."""

import pytest

from backend.core.auto_solver import AutoSolver, _profile_packages


def make_pkg(name, ecosystem="pypi", system_requirements=None):
    return {
        "name": name,
        "ecosystem": ecosystem,
        "version": "*",
        "system_requirements": system_requirements or {},
    }


class TestProfilePackages:
    def test_small_single_eco(self):
        pkgs = [make_pkg("a"), make_pkg("b")]
        prof = _profile_packages(pkgs)
        assert prof["pkg_count"] == 2
        assert prof["eco_count"] == 1
        assert prof["has_cross_eco_deps"] is False

    def test_multi_eco(self):
        pkgs = [make_pkg("a", "pypi"), make_pkg("b", "npm")]
        prof = _profile_packages(pkgs)
        assert prof["eco_count"] == 2
        assert prof["multi_eco"] is True

    def test_cuda_in_system_info(self):
        system_info = {"gpu": {"cuda": "12.1", "available": True}}
        pkgs = [make_pkg("torch")]
        prof = _profile_packages(pkgs, system_info)
        assert prof["has_cuda"] is True

    def test_cuda_in_system_requirements(self):
        pkgs = [make_pkg("torch", system_requirements={"cuda": "12.1"})]
        prof = _profile_packages(pkgs)
        assert prof["has_cuda"] is True

    def test_no_cuda(self):
        pkgs = [make_pkg("requests")]
        prof = _profile_packages(pkgs)
        assert prof["has_cuda"] is False

    def test_large_count(self):
        pkgs = [make_pkg(f"pkg{i}") for i in range(600)]
        prof = _profile_packages(pkgs)
        assert prof["is_large"] is True
        assert prof["is_small"] is False

    def test_small_count(self):
        pkgs = [make_pkg(f"pkg{i}") for i in range(10)]
        prof = _profile_packages(pkgs)
        assert prof["is_small"] is True
        assert prof["is_large"] is False

    def test_empty_packages(self):
        prof = _profile_packages([])
        assert prof["pkg_count"] == 0
        assert prof["is_small"] is True


class TestAutoSolverDecision:
    def test_override_z3(self, monkeypatch):
        monkeypatch.setattr("backend.core.auto_solver.USE_Z3_SOLVER", True)
        monkeypatch.setattr("backend.core.auto_solver.USE_HYBRID_SOLVER", False)
        monkeypatch.setattr("backend.core.auto_solver.USE_PUBGRUB_SOLVER", False)
        profile = {
            "is_small": True,
            "is_large": False,
            "has_cuda": False,
            "has_cross_eco_deps": False,
            "multi_eco": False,
            "pkg_count": 2,
        }
        solver = AutoSolver()
        _, name = solver._select_solver(profile)
        assert name == "z3-override"

    def test_override_hybrid(self, monkeypatch):
        monkeypatch.setattr("backend.core.auto_solver.USE_HYBRID_SOLVER", True)
        monkeypatch.setattr("backend.core.auto_solver.USE_Z3_SOLVER", False)
        monkeypatch.setattr("backend.core.auto_solver.USE_PUBGRUB_SOLVER", False)
        profile = {
            "is_small": True,
            "has_cuda": False,
            "has_cross_eco_deps": False,
            "multi_eco": False,
            "is_large": False,
            "pkg_count": 2,
        }
        solver = AutoSolver()
        _, name = solver._select_solver(profile)
        assert name == "hybrid-override"

    def test_override_pubgrub(self, monkeypatch):
        monkeypatch.setattr("backend.core.auto_solver.USE_PUBGRUB_SOLVER", True)
        monkeypatch.setattr("backend.core.auto_solver.USE_Z3_SOLVER", False)
        monkeypatch.setattr("backend.core.auto_solver.USE_HYBRID_SOLVER", False)
        profile = {
            "is_small": False,
            "has_cuda": True,
            "multi_eco": True,
            "has_cross_eco_deps": True,
            "is_large": False,
            "pkg_count": 10,
        }
        solver = AutoSolver()
        _, name = solver._select_solver(profile)
        assert name == "pubgrub-override"

    def test_small_selects_pubgrub(self):
        profile = {
            "is_small": True,
            "is_large": False,
            "has_cuda": False,
            "has_cross_eco_deps": False,
            "multi_eco": False,
            "pkg_count": 3,
        }
        solver = AutoSolver()
        _, name = solver._select_solver(profile)
        assert name == "pubgrub-small"

    def test_cuda_selects_z3(self):
        profile = {
            "is_small": False,
            "is_large": False,
            "has_cuda": True,
            "has_cross_eco_deps": False,
            "multi_eco": False,
            "pkg_count": 10,
        }
        solver = AutoSolver()
        _, name = solver._select_solver(profile)
        assert name == "z3-cuda"

    def test_cuda_large_selects_z3(self):
        profile = {
            "is_small": False,
            "is_large": True,
            "has_cuda": True,
            "has_cross_eco_deps": False,
            "multi_eco": False,
            "pkg_count": 600,
        }
        solver = AutoSolver()
        _, name = solver._select_solver(profile)
        assert name == "z3-cuda"

    def test_multi_eco_with_cuda_selects_hybrid(self):
        profile = {
            "is_small": False,
            "is_large": False,
            "has_cuda": True,
            "has_cross_eco_deps": True,
            "multi_eco": True,
            "pkg_count": 10,
        }
        solver = AutoSolver()
        _, name = solver._select_solver(profile)
        assert name == "hybrid-multi-eco"

    def test_multi_eco_cross_deps_selects_hybrid(self):
        profile = {
            "is_small": False,
            "is_large": False,
            "has_cuda": False,
            "has_cross_eco_deps": True,
            "multi_eco": True,
            "pkg_count": 10,
        }
        solver = AutoSolver()
        _, name = solver._select_solver(profile)
        assert name == "hybrid-multi-eco"

    def test_large_no_cuda_selects_pubgrub(self):
        profile = {
            "is_small": False,
            "is_large": True,
            "has_cuda": False,
            "has_cross_eco_deps": False,
            "multi_eco": False,
            "pkg_count": 600,
        }
        solver = AutoSolver()
        _, name = solver._select_solver(profile)
        assert name == "pubgrub-large"

    def test_default_pubgrub(self):
        profile = {
            "is_small": False,
            "is_large": False,
            "has_cuda": False,
            "has_cross_eco_deps": False,
            "multi_eco": False,
            "pkg_count": 100,
        }
        solver = AutoSolver()
        _, name = solver._select_solver(profile)
        assert name == "pubgrub-default"

    def test_fallback_chain_prefers_pubgrub(self):
        profile = {
            "is_small": True,
            "has_cuda": False,
            "multi_eco": False,
            "is_large": False,
            "has_cross_eco_deps": False,
            "pkg_count": 2,
        }
        solver = AutoSolver()
        chain = solver._fallback_chain(profile)
        names = [n for n, _ in chain]
        assert "z3-fallback" in names
        assert "hybrid-fallback" in names

    def test_fallback_chain_for_cuda(self):
        profile = {
            "is_small": False,
            "has_cuda": True,
            "multi_eco": False,
            "is_large": False,
            "has_cross_eco_deps": False,
            "pkg_count": 10,
        }
        solver = AutoSolver()
        chain = solver._fallback_chain(profile)
        names = [n for n, _ in chain]
        assert "pubgrub-fallback" in names
        assert "z3-fallback" in names

    def test_solver_field_in_result(self):
        solver = AutoSolver()
        result = solver.resolve_dependencies(
            [make_pkg("requests")],
            {"gpu": {"available": False, "cuda": None}},
        )
        assert "solver" in result
        assert "pubgrub" in result["solver"]

    def test_fallback_injects_solver_field(self, monkeypatch):
        call_log = []

        class FailingSolver:
            def resolve_dependencies(self, pkgs, system_info=None, **kw):
                call_log.append("first")
                return {"status": "unsatisfiable"}

        class PassingSolver:
            def resolve_dependencies(self, pkgs, system_info=None, **kw):
                call_log.append("fallback")
                return {"status": "satisfiable", "resolved_packages": {}}

        solver = AutoSolver()
        # _select_solver returns (solver_instance, name_string)
        monkeypatch.setattr(solver, "_select_solver", lambda profile: (FailingSolver(), "failing"))
        monkeypatch.setattr(
            solver, "_fallback_chain", lambda profile: [("passing", PassingSolver())]
        )
        result = solver.resolve_dependencies([make_pkg("requests")], None)
        assert result["solver"] == "passing"
        assert result["status"] == "satisfiable"
        assert call_log == ["first", "fallback"]
