"""Unit tests for backend/core/forking_resolver.py."""

import pytest

from backend.core.forking_resolver import (
    ForkingResolver,
    _fork_constraint_relax,
    _fork_major_version_pin,
    _fork_skip_first_two,
    _fork_skip_latest,
    _most_constrained_packages,
)
from backend.orchestrator.resolve import _maybe_wrap_forking


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def pkgs():
    return [
        {
            "name": "a",
            "ecosystem": "pypi",
            "version_constraint": ">=1.0",
            "available_versions": ["1.0.0", "1.1.0", "2.0.0", "2.1.0", "3.0.0"],
            "dependencies": {"pypi": {"b": ">=1.0", "c": ">=2.0"}},
        },
        {
            "name": "b",
            "ecosystem": "pypi",
            "version_constraint": "*",
            "available_versions": ["1.0.0", "1.5.0", "2.0.0"],
            "dependencies": {},
        },
        {
            "name": "c",
            "ecosystem": "pypi",
            "version_constraint": ">=2.0",
            "available_versions": ["2.0.0", "2.5.0", "3.0.0"],
            "dependencies": {"pypi": {"b": ">=1.0"}},
        },
    ]


@pytest.fixture
def mock_solver():
    """A solver stub that can be configured to succeed or fail."""

    class MockSolver:
        def __init__(self, fail_first=False):
            self._call_count = 0
            self._fail_first = fail_first

        def resolve_dependencies(self, packages, system_info=None, **kwargs):
            self._call_count += 1
            if self._fail_first and self._call_count == 1:
                return {"status": "unsatisfiable", "resolved_packages": {}}
            return {
                "status": "satisfiable",
                "resolved_packages": {"a": {"version": "2.0.0", "ecosystem": "pypi"}},
                "solver": "mock",
            }

    return MockSolver


# ── Tests: _most_constrained_packages ───────────────────────────────────────


class TestMostConstrainedPackages:
    def test_returns_top_n(self, pkgs):
        top = _most_constrained_packages(pkgs, count=2)
        assert len(top) == 2

    def test_a_most_constrained(self, pkgs):
        top = _most_constrained_packages(pkgs, count=1)
        assert len(top) == 1
        name, _score = top[0][1]["name"], top[0][0]
        # a has no in-edges but its name is first — sorting by in-edges * 100 - ver_count
        # a: 0*100 + (100-5) = 95; b: 2*100 + (100-3) = 297; c: 1*100 + (100-3) = 197
        names = [p["name"] for _, p in top]
        assert names == ["b"]  # b has 2 in-edges (from a and c)

    def test_empty_list(self):
        assert _most_constrained_packages([], count=3) == []

    def test_single_package(self):
        pkgs = [{"name": "x", "available_versions": ["1.0"], "dependencies": {}}]
        top = _most_constrained_packages(pkgs, count=5)
        assert len(top) == 1


# ── Tests: fork strategies ──────────────────────────────────────────────────


class TestForkSkipLatest:
    def test_skips_newest(self, pkgs):
        result = _fork_skip_latest(pkgs, "a")
        assert result is not None
        for p in result:
            if p["name"] == "a":
                assert "3.0.0" not in p["available_versions"]
                assert "2.0.0" in p["available_versions"]

    def test_no_change_on_single_version(self, pkgs):
        single = [
            {
                "name": "x",
                "ecosystem": "pypi",
                "available_versions": ["1.0.0"],
                "dependencies": {},
            }
        ]
        result = _fork_skip_latest(single, "x")
        assert result is None  # can't skip the only version

    def test_preserves_other_packages(self, pkgs):
        result = _fork_skip_latest(pkgs, "b")
        assert result is not None
        for p in result:
            if p["name"] == "a":
                assert p["available_versions"] == pkgs[0]["available_versions"]


class TestForkSkipFirstTwo:
    def test_skips_two_newest(self, pkgs):
        result = _fork_skip_first_two(pkgs, "a")
        assert result is not None
        for p in result:
            if p["name"] == "a":
                assert "3.0.0" not in p["available_versions"]
                assert "2.1.0" not in p["available_versions"]
                assert "2.0.0" in p["available_versions"]

    def test_returns_none_when_fewer_than_three(self):
        pkgs = [{"name": "x", "available_versions": ["1.0", "2.0"], "dependencies": {}}]
        assert _fork_skip_first_two(pkgs, "x") is None

    def test_returns_none_when_single(self):
        pkgs = [{"name": "x", "available_versions": ["1.0"], "dependencies": {}}]
        assert _fork_skip_first_two(pkgs, "x") is None


class TestForkMajorVersionPin:
    def test_pins_to_older_major(self, pkgs):
        result = _fork_major_version_pin(pkgs, "a")
        assert result is not None
        for p in result:
            if p["name"] == "a":
                vs = p["available_versions"]
                assert all(not v.startswith("3.") for v in vs)

    def test_returns_none_when_single_major(self):
        pkgs = [{"name": "x", "available_versions": ["1.0", "1.1"], "dependencies": {}}]
        result = _fork_major_version_pin(pkgs, "x")
        assert result is None

    def test_returns_none_when_single_version(self):
        pkgs = [{"name": "x", "available_versions": ["1.0"], "dependencies": {}}]
        result = _fork_major_version_pin(pkgs, "x")
        assert result is None


class TestForkConstraintRelax:
    def test_removes_constraint(self, pkgs):
        result = _fork_constraint_relax(pkgs, "a")
        assert result is not None
        for p in result:
            if p["name"] == "a":
                assert p["version_constraint"] == "*"

    def test_returns_none_when_already_wild(self):
        pkgs = [
            {
                "name": "x",
                "version_constraint": "*",
                "available_versions": ["1.0"],
                "dependencies": {},
            }
        ]
        assert _fork_constraint_relax(pkgs, "x") is None


# ── Tests: ForkingResolver ──────────────────────────────────────────────────


class TestForkingResolver:
    def test_returns_primary_result_on_success(self, mock_solver):
        solver = mock_solver(fail_first=False)
        resolver = ForkingResolver(solver, max_forks=2)
        result = resolver.resolve_dependencies([])
        assert result["status"] == "satisfiable"
        assert solver._call_count == 1

    def test_forks_on_failure(self, mock_solver):
        solver = mock_solver(fail_first=True)
        resolver = ForkingResolver(solver, max_forks=2)
        result = resolver.resolve_dependencies(
            [
                {
                    "name": "x",
                    "ecosystem": "pypi",
                    "version_constraint": "*",
                    "available_versions": ["1.0", "2.0"],
                    "dependencies": {},
                }
            ]
        )
        assert result["status"] == "satisfiable"
        # Primary call + at least one fork call
        assert solver._call_count >= 2

    def test_returns_primary_on_failure_when_no_forks_possible(self):
        """If critical packages have no forkable versions, return original failure."""

        class AlwaysFailSolver:
            def resolve_dependencies(self, packages, system_info=None, **kwargs):
                return {"status": "unsatisfiable", "resolved_packages": {}}

        resolver = ForkingResolver(AlwaysFailSolver(), max_forks=2)
        result = resolver.resolve_dependencies([])
        assert result["status"] == "unsatisfiable"

    def test_forks_on_timeout(self):
        class TimeoutSolver:
            def resolve_dependencies(self, packages, system_info=None, **kwargs):
                return {"status": "timeout", "resolved_packages": {}}

        class SuccessSolver:
            def __init__(self):
                self._called = False

            def resolve_dependencies(self, packages, system_info=None, **kwargs):
                if self._called:
                    return {"status": "satisfiable", "resolved_packages": {"x": {"version": "1.0"}}}
                self._called = True
                return {"status": "timeout", "resolved_packages": {}}

        resolver = ForkingResolver(SuccessSolver(), max_forks=2)
        result = resolver.resolve_dependencies(
            [
                {
                    "name": "x",
                    "ecosystem": "pypi",
                    "version_constraint": "*",
                    "available_versions": ["1.0", "2.0"],
                    "dependencies": {},
                }
            ],
            solver_timeout=60000,
        )
        assert result["status"] == "satisfiable"

    def test_calc_fork_timeout_default(self):
        resolver = ForkingResolver(None, max_forks=4, fork_timeout_ratio=0.5)
        assert resolver._calc_fork_timeout(None) == 30000

    def test_calc_fork_timeout_with_timeout(self):
        resolver = ForkingResolver(None, max_forks=4, fork_timeout_ratio=0.5)
        # 60000 * 0.5 / 4 = 7500 → clamped to 10000 minimum
        assert resolver._calc_fork_timeout(60000) == 10000

    def test_fork_solver_label_annotation(self, mock_solver):
        solver = mock_solver(fail_first=True)
        resolver = ForkingResolver(solver, max_forks=2)
        result = resolver.resolve_dependencies(
            [
                {
                    "name": "x",
                    "ecosystem": "pypi",
                    "version_constraint": "*",
                    "available_versions": ["1.0", "2.0"],
                    "dependencies": {},
                }
            ]
        )
        assert "fork:" in result.get("solver", "")

    def test_kwargs_passthrough(self):
        """kwargs (like prefer_compatibility) should reach the underlying solver."""

        class KwargChecker:
            def resolve_dependencies(self, packages, system_info=None, **kwargs):
                assert kwargs.get("prefer_compatibility") is True
                assert kwargs.get("solver_timeout") is not None
                return {"status": "satisfiable", "resolved_packages": {}}

        resolver = ForkingResolver(KwargChecker(), max_forks=2)
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


# ── Tests: factory integration ──────────────────────────────────────────────


class TestMaybeWrapForking:
    def test_no_wrap_when_disabled(self, monkeypatch):
        monkeypatch.setattr("backend.settings.USE_FORKING_SOLVER", False)
        solver = object()
        assert _maybe_wrap_forking(solver) is solver

    def test_wraps_when_enabled(self, monkeypatch):
        monkeypatch.setattr("backend.settings.USE_FORKING_SOLVER", True)
        monkeypatch.setattr("backend.settings.FORKING_MAX_FORKS", 4)
        monkeypatch.setattr("backend.settings.FORKING_TIMEOUT_RATIO", 0.5)
        from backend.core.forking_resolver import ForkingResolver

        solver = object()
        wrapped = _maybe_wrap_forking(solver)
        assert isinstance(wrapped, ForkingResolver)
        assert wrapped._max_forks == 4
        assert wrapped._fork_timeout_ratio == 0.5
