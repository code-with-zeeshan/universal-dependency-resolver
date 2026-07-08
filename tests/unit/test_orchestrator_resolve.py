"""Unit tests for orchestrator/resolve.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.orchestrator.resolve import (
    _add_cross_eco_edge,
    _build_dep_pkg,
    _collect_locked_transitive_deps,
    _determine_dep_ecosystem,
    _extract_system_requirements,
    _lock_data_to_result,
    _normalize_cuda,
    _safe_version_key,
)


class TestSafeVersionKey:
    def test_normal_version(self):
        from packaging.version import Version

        assert isinstance(_safe_version_key("1.2.3", "pypi"), Version)
        assert _safe_version_key("1.2.3", "pypi") == _safe_version_key("1.2.3", "pypi")

    def test_invalid_version_fallback(self):
        vk = _safe_version_key("not-a-version", "pypi")
        assert str(vk) == "0.0.0"

    def test_v_prefix_stripped(self):
        vk = _safe_version_key("v2.0.0", "pypi")
        assert str(vk) == "2.0.0"

    def test_go_version_with_v(self):
        vk = _safe_version_key("v1.2.3", "gomodules")
        assert str(vk) == "1.2.3"


class TestParsePackageSpec:
    def test_basic_pypi_default(self):
        from backend.orchestrator import _parse_package_spec

        name, eco, constraint = _parse_package_spec("numpy")
        assert name == "numpy"
        assert eco == "pypi"
        assert constraint is None

    def test_with_ecosystem(self):
        from backend.orchestrator import _parse_package_spec

        name, eco, constraint = _parse_package_spec("express@npm")
        assert name == "express"
        assert eco == "npm"
        assert constraint is None

    def test_scoped_npm(self):
        from backend.orchestrator import _parse_package_spec

        name, eco, constraint = _parse_package_spec("@angular/core@npm")
        assert name == "@angular/core"
        assert eco == "npm"
        assert constraint is None

    def test_with_constraint(self):
        from backend.orchestrator import _parse_package_spec

        name, eco, constraint = _parse_package_spec("numpy>=1.20")
        assert name == "numpy"
        assert eco == "pypi"
        assert constraint == ">=1.20"

    def test_with_constraint_and_ecosystem(self):
        from backend.orchestrator import _parse_package_spec

        name, eco, constraint = _parse_package_spec("fastapi>=0.115@pypi")
        assert name == "fastapi"
        assert eco == "pypi"
        assert constraint == ">=0.115"

    def test_unknown_ecosystem(self):
        from backend.orchestrator import _parse_package_spec

        name, eco, constraint = _parse_package_spec("pkg@nonexistent")
        assert eco == "pypi"  # falls back to default
        assert name == "pkg@nonexistent"  # returns raw spec


class TestExtractSystemRequirements:
    def test_extracts_python_runtime(self):
        Req = type("Req", (), {"type": "runtime", "name": "python", "version_spec": ">=3.9"})
        data = {"system_requirements": {"pypi": [Req()]}}
        result = _extract_system_requirements(data, "pypi")
        assert "python" in result
        assert result["python"]["min_version"] == "3.9"

    def test_extracts_cuda_req(self):
        data = {"ecosystem": {"pypi": {"system_requirements": {"cuda": {"min_version": "11.7"}}}}}
        result = _extract_system_requirements(data, "pypi")
        assert "cuda" in result
        assert result["cuda"]["min_version"] == "11.7"

    def test_ignores_other_runtimes(self):
        Req = type("Req", (), {"type": "runtime", "name": "python", "version_spec": ">=3.8"})
        data = {"system_requirements": {"pypi": [Req()]}, "ecosystem": {}}
        result = _extract_system_requirements(data, "npm")
        assert "python" not in result

    def test_handles_missing_system_requirements(self):
        data = {}
        result = _extract_system_requirements(data, "pypi")
        assert result == {}


class TestDetermineDepEcosystem:
    def test_dep_has_explicit_ecosystem(self):
        dep = MagicMock()
        dep.ecosystem = "npm"
        result = _determine_dep_ecosystem(dep, "npm", "pypi")
        assert result == "npm"

    def test_dep_ecosystem_differs_from_pkg(self):
        dep = MagicMock()
        dep.ecosystem = None
        result = _determine_dep_ecosystem(dep, "npm", "pypi")
        assert result == "npm"

    def test_same_ecosystem(self):
        dep = MagicMock()
        dep.ecosystem = None
        result = _determine_dep_ecosystem(dep, "pypi", "pypi")
        assert result == "pypi"


class TestBuildDepPkg:
    def test_basic_build(self):
        Dep = type("Dep", (), {"name": "urllib3", "version_spec": ">=1.21.1,<3", "ecosystem": None})
        dep_info = {
            "version": "1.26.0",
            "versions": {"pypi": [{"version": "1.26.0"}]},
            "dependencies": {},
            "system_requirements": {},
        }
        result = _build_dep_pkg(Dep(), "pypi", dep_info, "pypi", "requests")
        assert result is not None
        assert result["name"] == "urllib3"
        assert result["ecosystem"] == "pypi"
        assert "1.26.0" in result["available_versions"]

    def test_no_available_versions_returns_none(self):
        Dep = type("Dep", (), {"name": "missing", "version_spec": "*", "ecosystem": None})
        dep_info = {
            "version": "",
            "versions": {"pypi": []},
            "dependencies": {},
            "system_requirements": {},
        }
        result = _build_dep_pkg(Dep(), "pypi", dep_info, "pypi", "pkg")
        assert result is None

    def test_cross_ecosystem_edge(self):
        Dep = type("Dep", (), {"name": "express", "version_spec": "^4.18", "ecosystem": None})
        dep_info = {
            "version": "4.18.0",
            "versions": {"npm": [{"version": "4.18.0"}]},
            "dependencies": {},
            "system_requirements": {},
        }
        result = _build_dep_pkg(Dep(), "npm", dep_info, "pypi", "some-pkg")
        assert result is not None
        cross = result.get("cross_ecosystem_deps", [])
        assert len(cross) == 1
        assert cross[0]["source"] == "some-pkg@pypi"
        assert cross[0]["name"] == "express"
        assert cross[0]["target_ecosystem"] == "npm"


class TestAddCrossEcoEdge:
    def test_adds_edge(self):
        all_pkgs = {("express", "npm"): {"name": "express", "ecosystem": "npm"}}
        Dep = type("Dep", (), {"name": "express", "version_spec": "^4.18", "ecosystem": None})
        _add_cross_eco_edge(all_pkgs, ("express", "npm"), Dep(), "fastapi", "pypi", "npm")
        cross = all_pkgs[("express", "npm")]["cross_ecosystem_deps"]
        assert len(cross) == 1
        assert cross[0]["source"] == "fastapi@pypi"

    def test_no_duplicate_edges(self):
        all_pkgs = {
            ("express", "npm"): {"name": "express", "ecosystem": "npm", "cross_ecosystem_deps": []}
        }
        Dep = type("Dep", (), {"name": "express", "version_spec": "^4.18", "ecosystem": None})
        _add_cross_eco_edge(all_pkgs, ("express", "npm"), Dep(), "fastapi", "pypi", "npm")
        _add_cross_eco_edge(all_pkgs, ("express", "npm"), Dep(), "fastapi", "pypi", "npm")
        assert len(all_pkgs[("express", "npm")]["cross_ecosystem_deps"]) == 1

    def test_no_existing_skipped(self):
        all_pkgs = {}
        Dep = type("Dep", (), {"name": "express", "version_spec": "^4.18", "ecosystem": None})
        _add_cross_eco_edge(all_pkgs, ("express", "npm"), Dep(), "fastapi", "pypi", "npm")
        assert ("express", "npm") not in all_pkgs


class TestNormalizeCuda:
    def test_strips_dot_and_cu(self):
        assert _normalize_cuda("12.1") == 121
        assert _normalize_cuda("cu121") == 121
        assert _normalize_cuda("11.8") == 118

    def test_already_normalized(self):
        assert _normalize_cuda("118") == 118

    def test_invalid_returns_zero(self):
        assert _normalize_cuda("abc") == 0


class TestCollectLockedTransitiveDeps:
    def test_walks_dep_graph(self):
        locked = {
            "root": {"ecosystem": "pypi", "resolved_version": "1.0", "depends_on": {"dep_a": {}}},
            "dep_a": {"ecosystem": "pypi", "resolved_version": "2.0", "depends_on": {"dep_b": {}}},
            "dep_b": {"ecosystem": "pypi", "resolved_version": "3.0", "depends_on": {}},
        }
        result = _collect_locked_transitive_deps(locked, "root", "pypi")
        assert ("root", "pypi") in result
        assert ("dep_a", "pypi") in result
        assert ("dep_b", "pypi") in result

    def test_empty_deps(self):
        locked = {"root": {"ecosystem": "pypi", "resolved_version": "1.0", "depends_on": {}}}
        result = _collect_locked_transitive_deps(locked, "root", "pypi")
        assert len(result) == 1
        assert result[("root", "pypi")] == "1.0"

    def test_cycles_handled(self):
        locked = {
            "a": {"ecosystem": "pypi", "resolved_version": "1.0", "depends_on": {"b": {}}},
            "b": {"ecosystem": "pypi", "resolved_version": "2.0", "depends_on": {"a": {}}},
        }
        result = _collect_locked_transitive_deps(locked, "a", "pypi")
        assert ("a", "pypi") in result
        assert ("b", "pypi") in result


class TestLockDataToResult:
    def test_converts_lock_data(self):
        lock_data = {
            "packages": {
                "flask": {
                    "resolved_version": "2.3.3",
                    "ecosystem": "pypi",
                    "depends_on": {},
                },
                "click": {
                    "resolved_version": "8.1.7",
                    "ecosystem": "pypi",
                    "depends_on": {},
                },
            },
            "version": "2.0",
        }
        result = _lock_data_to_result(lock_data)
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"]["flask"]["version"] == "2.3.3"
        assert result["resolved_packages"]["click"]["version"] == "8.1.7"

    def test_empty_packages(self):
        result = _lock_data_to_result({"packages": {}})
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"] == {}

    def test_falls_back_to_version_field(self):
        lock_data = {
            "packages": {
                "pkg": {"version": "1.0", "ecosystem": "pypi", "depends_on": {}},
            }
        }
        result = _lock_data_to_result(lock_data)
        assert result["resolved_packages"]["pkg"]["version"] == "1.0"


class TestFetchDepInfo:
    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        aggregator = MagicMock()
        aggregator.get_package_info = AsyncMock(return_value={"name": "test-pkg"})
        from backend.orchestrator.resolve import _fetch_dep_info

        result = await _fetch_dep_info(aggregator, "test-pkg", "pypi")
        assert result == {"name": "test-pkg"}

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        aggregator = MagicMock()
        aggregator.get_package_info = AsyncMock(side_effect=Exception("API error"))
        from backend.orchestrator.resolve import _fetch_dep_info

        result = await _fetch_dep_info(aggregator, "bad-pkg", "pypi")
        assert result is None
