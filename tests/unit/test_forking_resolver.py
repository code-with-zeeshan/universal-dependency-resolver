"""Unit tests for backend/core/forking_resolver.py — cross-solver validator."""

import pytest

from backend.core.forking_resolver import ForkingResolver
from backend.orchestrator.resolve import _maybe_wrap_forking


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mk_solvers():
    """Return a pair of (primary, alternate) solver factories.

    Each factory returns (solver_instance, call_counter).
    """

    def _make(status_map, alt_status_map=None):
        class _Solver:
            def __init__(self, label, status):
                self._label = label
                self._status = status
                self._call_count = 0
                self._use_optimization = True

            def _get_default_system_info(self):
                return {}

            def resolve_dependencies(self, packages, system_info=None, **kwargs):
                self._call_count += 1
                s = self._status
                return {"status": s, "resolved_packages": {}, "solver": self._label}

        primary = _Solver("primary", status_map)
        alt = _Solver("alternate", alt_status_map or status_map)
        return primary, alt

    return _make


# ── Tests: ForkingResolver (cross-solver validation) ────────────────────────


class TestForkingResolver:
    def test_returns_primary_on_success(self, mk_solvers):
        primary, alt = mk_solvers("satisfiable")
        resolver = ForkingResolver(primary, alternate_solver_factory=lambda: alt)
        result = resolver.resolve_dependencies([])
        assert result["status"] == "satisfiable"
        assert primary._call_count == 1
        assert alt._call_count == 0

    def test_cross_validates_on_failure(self, mk_solvers):
        primary, alt = mk_solvers("unsatisfiable", "satisfiable")
        resolver = ForkingResolver(primary, alternate_solver_factory=lambda: alt)
        result = resolver.resolve_dependencies([])
        assert result["status"] == "satisfiable"
        assert primary._call_count == 1
        assert alt._call_count == 1
        assert "cross-validated" in result.get("solver", "")

    def test_both_unsat_returns_primary(self, mk_solvers):
        primary, alt = mk_solvers("unsatisfiable", "unsatisfiable")
        resolver = ForkingResolver(primary, alternate_solver_factory=lambda: alt)
        result = resolver.resolve_dependencies([])
        assert result["status"] == "unsatisfiable"
        # Primary called once for original solve + once for relaxation fallback
        assert primary._call_count == 2
        assert alt._call_count == 1
        assert result.get("cross_validation", {}).get("alternate_status") == "unsatisfiable"

    def test_primary_timeout_alt_solves(self, mk_solvers):
        primary, alt = mk_solvers("timeout", "satisfiable")
        resolver = ForkingResolver(primary, alternate_solver_factory=lambda: alt)
        result = resolver.resolve_dependencies([])
        assert result["status"] == "satisfiable"
        assert "cross-validated" in result.get("solver", "")

    def test_no_alt_factory_returns_primary(self):
        class AlwaysFail:
            def resolve_dependencies(self, packages, system_info=None, **kwargs):
                return {"status": "unsatisfiable", "resolved_packages": {}}

        resolver = ForkingResolver(AlwaysFail(), alternate_solver_factory=None)
        result = resolver.resolve_dependencies([])
        assert result["status"] == "unsatisfiable"

    def test_alt_exception_returns_primary_with_cross_validation(self):
        class FailSolver:
            def resolve_dependencies(self, packages, system_info=None, **kwargs):
                return {"status": "unsatisfiable", "resolved_packages": {}}

        class AltError:
            def resolve_dependencies(self, packages, system_info=None, **kwargs):
                raise RuntimeError("alt solver crashed")

        resolver = ForkingResolver(FailSolver(), alternate_solver_factory=lambda: AltError())
        result = resolver.resolve_dependencies([])
        assert result["status"] == "unsatisfiable"
        assert result.get("cross_validation", {}).get("alternate_status") == "error"

    def test_kwargs_passthrough(self):
        class CheckKwargs:
            def __init__(self, label):
                self._label = label
                self._use_optimization = True

            def _get_default_system_info(self):
                return {}

            def resolve_dependencies(self, packages, system_info=None, **kwargs):
                assert kwargs.get("prefer_compatibility") is True
                assert kwargs.get("solver_timeout") == 30000
                return {"status": "satisfiable", "resolved_packages": {}, "solver": self._label}

        resolver = ForkingResolver(
            CheckKwargs("primary"),
            alternate_solver_factory=lambda: CheckKwargs("alt"),
        )
        resolver.resolve_dependencies(
            [
                {
                    "name": "x",
                    "ecosystem": "pypi",
                    "version_constraint": "*",
                    "available_versions": ["1.0"],
                    "dependencies": {},
                }
            ],
            prefer_compatibility=True,
            solver_timeout=30000,
        )

    def test_get_default_system_info_delegates(self):
        class Primary:
            def _get_default_system_info(self):
                return {"os": "linux"}

        resolver = ForkingResolver(Primary())
        assert resolver._get_default_system_info() == {"os": "linux"}


# ── Tests: factory integration ──────────────────────────────────────────────


class TestMaybeWrapForking:
    def test_always_wraps_when_available(self):
        from backend.core.forking_resolver import ForkingResolver

        solver = object()
        wrapped = _maybe_wrap_forking(solver)
        assert isinstance(wrapped, ForkingResolver)
        assert wrapped._primary is solver
