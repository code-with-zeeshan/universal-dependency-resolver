from __future__ import annotations

import pytest

from backend.core.resolution_result import ResolutionResult


class TestResolutionResult:
    def test_success_defaults(self):
        r = ResolutionResult(
            status="satisfiable",
            resolved_packages={"foo": {"version": "1.0", "ecosystem": "pypi"}},
            dependency_tree={},
            warnings=[],
            installation_order=["foo"],
        )
        assert r.is_success
        assert not r.is_timeout
        assert not r.is_unsatisfiable
        assert not r.is_partial
        assert r.error is None

    def test_unsatisfiable(self):
        r = ResolutionResult(
            status="unsatisfiable",
            resolved_packages={},
            dependency_tree={},
            warnings=["Conflict between A and B"],
            installation_order=[],
            error="No solution found",
            conflicts=[{"packages": ["A", "B"], "constraint": "A>1.0, B<2.0"}],
        )
        assert r.is_unsatisfiable
        assert not r.is_success
        assert r.error == "No solution found"
        assert len(r.conflicts) == 1

    def test_timeout(self):
        r = ResolutionResult(
            status="timeout",
            resolved_packages={},
            dependency_tree={},
            warnings=["Solver timed out"],
            installation_order=[],
        )
        assert r.is_timeout

    def test_partial(self):
        r = ResolutionResult(
            status="partial",
            resolved_packages={"bar": {"version": "2.0", "ecosystem": "npm"}},
            dependency_tree={},
            warnings=["1/3 SCCs failed"],
            installation_order=["bar"],
        )
        assert r.is_partial

    def test_from_dict_success(self):
        data = {
            "status": "satisfiable",
            "resolved_packages": {"a": {"version": "1", "ecosystem": "pypi"}},
            "dependency_tree": {"a": {}},
            "warnings": [],
            "installation_order": ["a"],
        }
        r = ResolutionResult.from_dict(data)
        assert r.is_success
        assert r.resolved_packages["a"]["version"] == "1"

    def test_from_dict_falls_back_to_packages(self):
        data = {
            "status": "satisfiable",
            "packages": {"b": {"version": "2", "ecosystem": "npm"}},
            "dependency_tree": {},
            "warnings": [],
            "installation_order": ["b"],
        }
        r = ResolutionResult.from_dict(data)
        assert r.resolved_packages["b"]["version"] == "2"

    def test_from_dict_with_conflicts(self):
        data = {
            "status": "unsatisfiable",
            "resolved_packages": {},
            "dependency_tree": {},
            "warnings": [],
            "installation_order": [],
            "error": "Conflict detected",
            "conflicts": [{"packages": ["x", "y"]}],
        }
        r = ResolutionResult.from_dict(data)
        assert r.error == "Conflict detected"
        assert r.conflicts == [{"packages": ["x", "y"]}]

    def test_to_dict_omits_empty_error_conflicts(self):
        r = ResolutionResult(
            status="satisfiable",
            resolved_packages={},
            dependency_tree={},
            warnings=[],
            installation_order=[],
        )
        d = r.to_dict()
        assert "error" not in d
        assert "conflicts" not in d
        assert d["status"] == "satisfiable"

    def test_to_dict_includes_error(self):
        r = ResolutionResult(
            status="unsatisfiable",
            resolved_packages={},
            dependency_tree={},
            warnings=["x"],
            installation_order=[],
            error="bad",
            conflicts=[{"c": "d"}],
        )
        d = r.to_dict()
        assert d["error"] == "bad"
        assert d["conflicts"] == [{"c": "d"}]

    def test_roundtrip(self):
        original = {
            "status": "satisfiable",
            "resolved_packages": {"pkg": {"version": "1.0.0", "ecosystem": "pypi"}},
            "dependency_tree": {"pkg": {"deps": []}},
            "warnings": [],
            "installation_order": ["pkg"],
        }
        r = ResolutionResult.from_dict(original)
        assert r.to_dict() == original

    @pytest.mark.parametrize(
        "status,expected",
        [
            ("satisfiable", "is_success"),
            ("unsatisfiable", "is_unsatisfiable"),
            ("timeout", "is_timeout"),
            ("partial", "is_partial"),
        ],
    )
    def test_status_properties(self, status: str, expected: str):
        r = ResolutionResult(
            status=status,
            resolved_packages={},
            dependency_tree={},
            warnings=[],
            installation_order=[],
        )
        assert getattr(r, expected)
