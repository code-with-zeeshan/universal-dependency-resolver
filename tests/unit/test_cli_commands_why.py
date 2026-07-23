from unittest.mock import MagicMock, patch

import pytest

from backend.cli.commands.why import (
    _build_reverse_deps,
    _find_dep_chain,
    _render_dep_table,
)


class TestBuildReverseDeps:
    def test_empty_packages(self):
        assert _build_reverse_deps({}) == {}

    def test_single_dep(self):
        packages = {
            "a": {
                "resolved_version": "1.0.0",
                "depends_on": {"b": {"constraint": ">=1.0"}},
            }
        }
        result = _build_reverse_deps(packages)
        assert result == {"b": [("a", "1.0.0", ">=1.0")]}

    def test_dep_with_string_constraint(self):
        packages = {
            "a": {
                "resolved_version": "1.0.0",
                "depends_on": {"b": ">=2.0"},
            }
        }
        result = _build_reverse_deps(packages)
        assert result == {"b": [("a", "1.0.0", ">=2.0")]}

    def test_multiple_reverse_deps(self):
        packages = {
            "a": {"resolved_version": "1.0", "depends_on": {"c": ">=1.0"}},
            "b": {"resolved_version": "2.0", "depends_on": {"c": ">=2.0"}},
        }
        result = _build_reverse_deps(packages)
        assert len(result["c"]) == 2
        assert ("a", "1.0", ">=1.0") in result["c"]
        assert ("b", "2.0", ">=2.0") in result["c"]

    def test_no_resolved_version_key(self):
        packages = {"a": {"depends_on": {"b": "*"}}}
        result = _build_reverse_deps(packages)
        assert result["b"][0][1] == "?"


class TestFindDepChain:
    def test_target_not_in_rev_deps(self):
        assert _find_dep_chain({}, {}, "missing") is None

    def test_direct_dep(self):
        packages = {
            "root": {"resolved_version": "1.0", "direct": True, "depends_on": {"dep": ">=1.0"}},
            "dep": {"resolved_version": "2.0", "direct": False, "depends_on": {}},
        }
        rev = _build_reverse_deps(packages)
        chain = _find_dep_chain(packages, rev, "dep")
        assert chain is not None
        assert len(chain) == 1
        assert chain[0][0] == "root"
        assert chain[0][3] is True

    def test_transitive_chain(self):
        packages = {
            "root": {"resolved_version": "1.0", "direct": True, "depends_on": {"mid": ">=1.0"}},
            "mid": {"resolved_version": "1.5", "direct": False, "depends_on": {"leaf": ">=2.0"}},
            "leaf": {"resolved_version": "2.0", "direct": False, "depends_on": {}},
        }
        rev = _build_reverse_deps(packages)
        chain = _find_dep_chain(packages, rev, "leaf")
        assert chain is not None
        assert chain[0][0] == "root"
        assert chain[1][0] == "mid"

    def test_circular_dep_avoided(self):
        packages = {
            "a": {"resolved_version": "1.0", "direct": True, "depends_on": {"b": ">=1.0"}},
            "b": {"resolved_version": "1.0", "direct": False, "depends_on": {"a": ">=1.0"}},
        }
        rev = _build_reverse_deps(packages)
        chain = _find_dep_chain(packages, rev, "b")
        assert chain is not None
        assert chain[0][0] == "a"

    def test_max_depth_exceeded(self):
        packages = {
            f"lvl{i}": {
                "resolved_version": "1.0",
                "direct": i == 0,
                "depends_on": {f"lvl{i + 1}": ">=1.0"},
            }
            for i in range(15)
        }
        packages["lvl14"]["depends_on"] = {}
        rev = _build_reverse_deps(packages)
        chain = _find_dep_chain(packages, rev, "lvl14", max_depth=3)
        assert chain is None


class TestRenderDepTable:
    @patch("backend.cli.commands.why.console")
    def test_direct_dep(self, mock_console):
        _render_dep_table(
            packages={"dep": {"resolved_version": "1.0", "source": "manifest", "direct": True}},
            rev_deps={},
            target="dep",
            ver="1.0",
            eco="pypi",
            direct=True,
            constraint=">=1.0",
        )
        assert mock_console.print.called

    @patch("backend.cli.commands.why.console")
    def test_transitive_dep(self, mock_console):
        _render_dep_table(
            packages={"dep": {"resolved_version": "1.0", "direct": False}},
            rev_deps={},
            target="dep",
            ver="1.0",
            eco="pypi",
            direct=False,
            constraint="",
        )
        assert mock_console.print.called

    @patch("backend.cli.commands.why.console")
    def test_with_reverse_deps(self, mock_console):
        rev_deps = {"dep": [("parent", "2.0", ">=1.0")]}
        _render_dep_table(
            packages={"dep": {"resolved_version": "1.0", "direct": False}},
            rev_deps=rev_deps,
            target="dep",
            ver="1.0",
            eco="pypi",
            direct=False,
            constraint="",
        )
        assert mock_console.print.called
