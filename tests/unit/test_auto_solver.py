"""Unit tests for core/auto_solver.py — crash-fallback hardening."""

from backend.core.auto_solver import AutoSolver


class _CrashingSolver:
    """Solver stub that always raises — simulates e.g. pubgrub-py ValueError."""

    def resolve_dependencies(self, packages, system_info=None, **kwargs):
        raise ValueError("Invalid version '8.3.*': unexpected character '*'")

    def _get_default_system_info(self):
        return {}


class _GoodSolver:
    """Solver stub that always resolves satisfiably."""

    def resolve_dependencies(self, packages, system_info=None, **kwargs):
        return {"status": "satisfiable", "resolved_packages": {}}

    def _get_default_system_info(self):
        return {}


class _BadSolver:
    """Solver stub that returns unsatisfiable."""

    def resolve_dependencies(self, packages, system_info=None, **kwargs):
        return {"status": "unsatisfiable", "resolution_error": "no", "resolved_packages": {}}

    def _get_default_system_info(self):
        return {}


def _pkg(name="app"):
    return {
        "name": name,
        "ecosystem": "pypi",
        "version_constraint": ">=0.0.0",
        "available_versions": ["1.0.0"],
        "dependencies": {"pypi": {"all": []}},
    }


def test_primary_crash_falls_through_to_fallback(monkeypatch):
    """A crashing primary must NOT propagate — the fallback solver runs."""
    asolver = AutoSolver()
    monkeypatch.setattr(asolver, "_select_solver", lambda profile: (_CrashingSolver(), "crash"))
    monkeypatch.setattr(asolver, "_fallback_chain", lambda profile: [("good", _GoodSolver())])
    result = asolver.resolve_dependencies([_pkg()])
    assert result["status"] == "satisfiable"
    assert result["solver"] == "good"


def test_primary_crash_and_bad_fallback_returns_error(monkeypatch):
    autosolv = AutoSolver()
    monkeypatch.setattr(autosolv, "_select_solver", lambda profile: (_CrashingSolver(), "crash"))
    monkeypatch.setattr(autosolv, "_fallback_chain", lambda profile: [("bad", _BadSolver())])
    result = autosolv.resolve_dependencies([_pkg()])
    assert result["status"] == "unsatisfiable"
    assert "crashed" in result.get("resolution_error", "")


def test_primary_crash_crash_fallback_crash_returns_primary_error(monkeypatch):
    autosolv = AutoSolver()
    monkeypatch.setattr(autosolv, "_select_solver", lambda profile: (_CrashingSolver(), "crash"))
    monkeypatch.setattr(
        autosolv, "_fallback_chain", lambda profile: [("crash2", _CrashingSolver())]
    )
    result = autosolv.resolve_dependencies([_pkg()])
    assert result["status"] == "unsatisfiable"
    assert "crash" in result.get("resolution_error", "")
    assert result["solver"] == "crash"


def test_primary_unsat_crash_fallback_sat(monkeypatch):
    autosolv = AutoSolver()
    monkeypatch.setattr(autosolv, "_select_solver", lambda profile: (_BadSolver(), "bad"))
    monkeypatch.setattr(autosolv, "_fallback_chain", lambda profile: [("good", _GoodSolver())])
    result = autosolv.resolve_dependencies([_pkg()])
    assert result["status"] == "satisfiable"
    assert result["solver"] == "good"


def test_satisfiable_primary_skips_fallbacks(monkeypatch):
    autosolv = AutoSolver()
    called = []

    def _fallback_chain(profile):
        called.append(True)
        return []

    monkeypatch.setattr(autosolv, "_select_solver", lambda profile: (_GoodSolver(), "good"))
    monkeypatch.setattr(autosolv, "_fallback_chain", _fallback_chain)
    result = autosolv.resolve_dependencies([_pkg()])
    assert result["status"] == "satisfiable"
    assert called == []


def test_real_wildcard_pubgrub_crash_falls_back_to_z3():
    """Integration: the torchvision wildcard repro crashes pubgrub -> AutoSolver
    falls back, never raises."""
    try:
        from backend.core.conflict_resolver import ConflictResolver  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("z3 not installed")
    autosolv = AutoSolver()
    # Use the real default + the real fallback chain (z3) with the wildcard
    # sanitizer disabled, so the primary crashes exactly like the original bug.
    import backend.core.pubgrub_solver as ps

    original = ps._expand_wildcard_exclusions
    ps._expand_wildcard_exclusions = lambda c, v: c  # disable the sanitizer for this test
    try:
        packages = [
            {
                "name": "app",
                "ecosystem": "pypi",
                "version_constraint": ">=0.0.0",
                "available_versions": ["1.0.0"],
                "dependencies": {"pypi": {"torchvision": ">=0.0.0"}},
            },
            {
                "name": "torchvision",
                "ecosystem": "pypi",
                "version_constraint": ">=0.0.0",
                "available_versions": ["0.28.0"],
                "dependencies": {"pypi": {"pillow": "!=8.3.*,>=5.3.0"}},
            },
            {
                "name": "pillow",
                "ecosystem": "pypi",
                "version_constraint": ">=0.0.0",
                "available_versions": ["8.2.0", "8.3.0", "8.3.1", "9.0.0"],
                "dependencies": {"pypi": {}},
            },
        ]
        result = autosolv.resolve_dependencies(packages)
    finally:
        ps._expand_wildcard_exclusions = original
    assert result["status"] == "satisfiable"
    assert result["resolved_packages"]["pillow"]["version"] == "9.0.0"
