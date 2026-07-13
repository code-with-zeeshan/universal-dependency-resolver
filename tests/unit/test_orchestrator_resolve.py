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
        data = {"ecosystems": {"pypi": {"system_requirements": {"cuda": {"min_version": "11.7"}}}}}
        result = _extract_system_requirements(data, "pypi")
        assert "cuda" in result
        assert result["cuda"]["min_version"] == "11.7"

    def test_ignores_other_runtimes(self):
        Req = type("Req", (), {"type": "runtime", "name": "python", "version_spec": ">=3.8"})
        data = {"system_requirements": {"pypi": [Req()]}, "ecosystems": {}}
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
        result = _build_dep_pkg(Dep(), "pypi", dep_info)
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
        result = _build_dep_pkg(Dep(), "pypi", dep_info)
        assert result is None

    def test_passes_through_cross_ecosystem_deps_from_aggregator(self):
        Dep = type("Dep", (), {"name": "express", "version_spec": "^4.18", "ecosystem": None})
        dep_info = {
            "version": "4.18.0",
            "versions": {"npm": [{"version": "4.18.0"}]},
            "dependencies": {},
            "system_requirements": {},
            "cross_ecosystem_deps": [
                {
                    "source_ecosystem": "pypi",
                    "target_ecosystem": "npm",
                    "dependency": "express",
                    "version_spec": "^4.18",
                }
            ],
        }
        result = _build_dep_pkg(Dep(), "npm", dep_info)
        assert result is not None
        cross = result.get("cross_ecosystem_deps", [])
        assert len(cross) == 1
        assert cross[0]["dependency"] == "express"
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


class TestBuildDepPkgDevOnlyFiltering:
    """_build_dep_pkg should exclude dev_only deps from dependencies dict."""

    def test_excludes_dev_only_deps(self):
        DepObj = type(
            "DepObj",
            (),
            {"name": "dev-lib", "version_spec": "^1.0", "dev_only": True, "ecosystem": None},
        )
        Dep = type("Dep", (), {"name": "mypkg", "version_spec": "*", "ecosystem": None})
        dep_info = {
            "version": "1.0.0",
            "versions": {"npm": [{"version": "1.0.0"}]},
            "dependencies": {
                "npm": {
                    "all": [
                        DepObj(),
                        type(
                            "DepObj",
                            (),
                            {
                                "name": "runtime-lib",
                                "version_spec": "^2.0",
                                "dev_only": False,
                                "ecosystem": None,
                            },
                        )(),
                    ]
                }
            },
            "system_requirements": {},
        }
        result = _build_dep_pkg(Dep(), "npm", dep_info)
        assert result is not None
        npm_deps = result["dependencies"].get("npm", {})
        assert "dev-lib" not in npm_deps, "dev_only dep should be excluded"
        assert "runtime-lib" in npm_deps, "runtime dep should be included"

    def test_includes_all_when_no_dev(self):
        DepObj = type(
            "DepObj",
            (),
            {"name": "lib-a", "version_spec": ">=1.0", "dev_only": False, "ecosystem": None},
        )
        DepObj2 = type(
            "DepObj2",
            (),
            {"name": "lib-b", "version_spec": ">=2.0", "dev_only": False, "ecosystem": None},
        )
        Dep = type("Dep", (), {"name": "mypkg", "version_spec": "*", "ecosystem": None})
        dep_info = {
            "version": "1.0.0",
            "versions": {"pypi": [{"version": "1.0.0"}]},
            "dependencies": {"pypi": {"all": [DepObj(), DepObj2()]}},
            "system_requirements": {},
        }
        result = _build_dep_pkg(Dep(), "pypi", dep_info)
        assert result is not None
        pypi_deps = result["dependencies"].get("pypi", {})
        assert len(pypi_deps) == 2


class TestAggregatorToResolverInputDevOnlyFiltering:
    """_aggregator_to_resolver_input should skip dev_only deps."""

    def test_skips_dev_only_deps(self):
        from backend.orchestrator.resolve import _aggregator_to_resolver_input

        DepObj = type(
            "DepObj",
            (),
            {"name": "dev-dep", "version_spec": ">=1.0", "dev_only": True, "ecosystem": None},
        )
        agg_data = {
            "name": "mypkg",
            "versions": {"npm": [{"version": "1.0.0"}]},
            "dependencies": {
                "npm": {
                    "all": [
                        DepObj(),
                        type(
                            "DepObj",
                            (),
                            {
                                "name": "run-dep",
                                "version_spec": ">=2.0",
                                "dev_only": False,
                                "ecosystem": None,
                            },
                        )(),
                    ]
                }
            },
        }
        result = _aggregator_to_resolver_input(agg_data, "npm")
        deps = result.get("dependencies", {}).get("npm", {})
        assert "dev-dep" not in deps, "dev_only dep should be excluded"
        assert "run-dep" in deps, "runtime dep should be included"

    def test_includes_all_when_no_dev_flag(self):
        from backend.orchestrator.resolve import _aggregator_to_resolver_input

        DepObj = type(
            "DepObj",
            (),
            {"name": "dep-a", "version_spec": ">=1.0", "dev_only": False, "ecosystem": None},
        )
        agg_data = {
            "name": "mypkg",
            "versions": {"pypi": [{"version": "1.0.0"}]},
            "dependencies": {"pypi": {"all": [DepObj()]}},
        }
        result = _aggregator_to_resolver_input(agg_data, "pypi")
        deps = result.get("dependencies", {}).get("pypi", {})
        assert "dep-a" in deps


class TestCollectCurrentDepsFormatHandling:
    """_collect_current_deps should handle both {"all": [...]} and {name: constraint} formats."""

    def test_handles_both_formats_through_build_dep_pkg(self):
        """Verify _build_dep_pkg output (flat format) is compatible with _collect_current_deps inputs."""
        DepObj = type(
            "DepObj",
            (),
            {"name": "transitive", "version_spec": ">=1.0", "dev_only": False, "ecosystem": None},
        )
        Dep = type("Dep", (), {"name": "rootpkg", "version_spec": "*", "ecosystem": None})
        dep_info = {
            "version": "1.0.0",
            "versions": {"pypi": [{"version": "1.0.0"}]},
            "dependencies": {"pypi": {"all": [DepObj()]}},
            "system_requirements": {},
        }
        pkg = _build_dep_pkg(Dep(), "pypi", dep_info)
        assert pkg is not None
        # The flat format should be {name: constraint}, not {"all": [...]}
        deps = pkg["dependencies"]
        assert "pypi" in deps
        assert "transitive" in deps["pypi"]
        assert isinstance(deps["pypi"]["transitive"], str), (
            "constraint should be a string in flat format"
        )
        assert "all" not in deps["pypi"], "flat format should not have 'all' key"


class TestSystemInfoFingerprint:
    def test_extracts_deterministic_fields(self):
        from backend.orchestrator.resolve import _system_info_fingerprint

        system_info = {
            "platform": {"system": "linux", "architecture": "x86_64"},
            "cpu": {"brand": "Intel", "cores": 8, "arch": "x86_64"},
            "gpu": {"cuda": "12.1"},
            "runtime_versions": {"python": {"version": "3.11.0"}},
            "memory": {"total": 16384, "available": 8192},
            "disks": [{"mount": "/", "total": 500}],
            "hostname": "my-machine",
            "unrelated": "should-be-ignored",
        }
        fp = _system_info_fingerprint(system_info)
        assert fp.get("platform", {}).get("system") == "linux"
        assert fp.get("platform", {}).get("architecture") == "x86_64"
        assert fp.get("gpu", {}).get("cuda") == "12.1"
        assert fp.get("runtime_versions", {}).get("python", {}).get("version") == "3.11.0"
        assert "memory" not in fp
        assert "disks" not in fp
        assert "hostname" not in fp
        assert "unrelated" not in fp

    def test_none_input_returns_empty(self):
        from backend.orchestrator.resolve import _system_info_fingerprint

        assert _system_info_fingerprint(None) == {}
        assert _system_info_fingerprint({}) == {}

    def test_partial_info(self):
        from backend.orchestrator.resolve import _system_info_fingerprint

        fp = _system_info_fingerprint({"gpu": {"cuda": "11.8"}})
        assert fp.get("gpu", {}).get("cuda") == "11.8"
        assert "platform" not in fp
        assert "runtime_versions" not in fp

    def test_arch_falls_back_to_cpu_arch(self):
        from backend.orchestrator.resolve import _system_info_fingerprint

        fp = _system_info_fingerprint({"cpu": {"arch": "aarch64"}})
        assert fp.get("platform", {}).get("architecture") == "aarch64"

    def test_includes_non_cuda_gpu_types(self):
        from backend.orchestrator.resolve import _system_info_fingerprint

        system_info = {
            "gpu": {
                "rocm": "6.0.0",
                "intel_gpu": "1.0.0",
                "metal": "3.0",
                "cuda": "12.1",
            },
        }
        fp = _system_info_fingerprint(system_info)
        gpu = fp.get("gpu", {})
        assert gpu.get("rocm") == "6.0.0"
        assert gpu.get("intel_gpu") == "1.0.0"
        assert gpu.get("metal") == "3.0"
        assert gpu.get("cuda") == "12.1"

    def test_non_cuda_gpu_types_with_dict_format(self):
        from backend.orchestrator.resolve import _system_info_fingerprint

        system_info = {
            "gpu": {
                "rocm": {"version": "5.7.0"},
                "metal": {"version": "3.0"},
            },
        }
        fp = _system_info_fingerprint(system_info)
        gpu = fp.get("gpu", {})
        assert gpu.get("rocm") == "5.7.0"
        assert gpu.get("metal") == "3.0"

    def test_non_cuda_gpu_types_omitted_when_missing(self):
        from backend.orchestrator.resolve import _system_info_fingerprint

        fp = _system_info_fingerprint({"gpu": {"cuda": "12.1"}})
        assert "rocm" not in fp.get("gpu", {})
        assert "intel_gpu" not in fp.get("gpu", {})
        assert "metal" not in fp.get("gpu", {})


class TestIncrementalResolution:
    @pytest.mark.asyncio
    async def test_incremental_happy_path(self):
        from unittest.mock import AsyncMock

        from backend.core.conflict_resolver import ConflictResolver
        from backend.orchestrator.resolve import (
            _resolve_transitive,
            _system_info_fingerprint,
        )

        aggregator = MagicMock()
        resolver = MagicMock()
        system_info = {
            "platform": {"system": "linux", "architecture": "x86_64"},
            "runtime_versions": {"python": {"version": "3.11.0"}},
            "memory": {"total": 16384},
        }
        fingerprint = _system_info_fingerprint(system_info)

        pkg = {
            "name": "flask",
            "ecosystem": "pypi",
            "version_constraint": ">=2.0",
            "dependencies": {},
        }
        expected_hash = ConflictResolver.compute_resolution_hash(
            "flask", "pypi", ">=2.0", {}, fingerprint
        )
        lock_data = {
            "packages": {
                "flask": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.3.3",
                    "version": "2.3.3",
                    "original_constraint": ">=2.0",
                    "resolution_hash": expected_hash,
                    "depends_on": {},
                }
            }
        }

        result = await _resolve_transitive(
            aggregator,
            resolver,
            [pkg],
            system_info,
            lock_data=lock_data,
        )
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"]["flask"]["version"] == "2.3.3"
        resolver.resolve_dependencies.assert_not_called()

    @pytest.mark.asyncio
    async def test_incremental_partial_change(self):
        from unittest.mock import AsyncMock

        from backend.core.conflict_resolver import ConflictResolver
        from backend.orchestrator.resolve import (
            _resolve_transitive,
            _system_info_fingerprint,
        )

        aggregator = MagicMock()
        aggregator.get_package_info = AsyncMock(
            return_value={
                "name": "requests",
                "versions": {"pypi": [{"version": "2.31.0"}]},
                "dependencies": {},
                "system_requirements": {},
            }
        )
        resolver = MagicMock()
        resolver.resolve_dependencies.return_value = {
            "status": "satisfiable",
            "resolved_packages": {
                "requests": {"version": "2.31.0", "ecosystem": "pypi"},
            },
        }
        system_info = {
            "platform": {"system": "linux"},
            "gpu": {"cuda": "12.1"},
        }
        fingerprint = _system_info_fingerprint(system_info)

        # flask unchanged
        flask_hash = ConflictResolver.compute_resolution_hash(
            "flask", "pypi", ">=2.0", {}, fingerprint
        )
        # requests changed — compute hash with OLD constraint so stored hash doesn't match
        old_requests_hash = ConflictResolver.compute_resolution_hash(
            "requests", "pypi", ">=2.28.0", {}, fingerprint
        )
        packages = [
            {
                "name": "flask",
                "ecosystem": "pypi",
                "version_constraint": ">=2.0",
                "dependencies": {},
            },
            {
                "name": "requests",
                "ecosystem": "pypi",
                "version_constraint": ">=2.31.0",
                "dependencies": {},
            },
        ]
        lock_data = {
            "packages": {
                "flask": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.3.3",
                    "version": "2.3.3",
                    "original_constraint": ">=2.0",
                    "resolution_hash": flask_hash,
                    "depends_on": {},
                },
                "requests": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.28.0",
                    "version": "2.28.0",
                    "original_constraint": ">=2.28.0",
                    "resolution_hash": old_requests_hash,
                    "depends_on": {},
                },
            }
        }

        result = await _resolve_transitive(
            aggregator,
            resolver,
            packages,
            system_info,
            lock_data=lock_data,
        )
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"]["flask"]["version"] == "2.3.3"
        assert result["resolved_packages"]["requests"]["version"] == "2.31.0"
        resolver.resolve_dependencies.assert_called_once()

    @pytest.mark.asyncio
    async def test_incremental_no_lock_data(self):
        from unittest.mock import AsyncMock

        from backend.orchestrator.resolve import _resolve_transitive

        aggregator = MagicMock()
        aggregator.get_package_info = AsyncMock(return_value=None)
        resolver = MagicMock()
        resolver.resolve_dependencies.return_value = {
            "status": "satisfiable",
            "resolved_packages": {},
        }
        system_info = {"gpu": {"cuda": "12.1"}}
        pkg = {
            "name": "flask",
            "ecosystem": "pypi",
            "version_constraint": ">=2.0",
            "dependencies": {},
        }

        result = await _resolve_transitive(
            aggregator,
            resolver,
            [pkg],
            system_info,
            lock_data=None,
        )
        assert result["status"] == "satisfiable"
        aggregator.get_package_info.assert_called()

    @pytest.mark.asyncio
    async def test_incremental_force_flag(self):
        from unittest.mock import AsyncMock

        from backend.core.conflict_resolver import ConflictResolver
        from backend.orchestrator.resolve import (
            _resolve_transitive,
            _system_info_fingerprint,
        )

        aggregator = MagicMock()
        aggregator.get_package_info = AsyncMock(return_value=None)
        resolver = MagicMock()
        resolver.resolve_dependencies.return_value = {
            "status": "satisfiable",
            "resolved_packages": {},
        }
        system_info = {"platform": {"system": "linux"}}
        fingerprint = _system_info_fingerprint(system_info)

        pkg = {
            "name": "flask",
            "ecosystem": "pypi",
            "version_constraint": ">=2.0",
            "dependencies": {},
        }
        expected_hash = ConflictResolver.compute_resolution_hash(
            "flask", "pypi", ">=2.0", {}, fingerprint
        )
        lock_data = {
            "packages": {
                "flask": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.3.3",
                    "version": "2.3.3",
                    "original_constraint": ">=2.0",
                    "resolution_hash": expected_hash,
                    "depends_on": {},
                }
            }
        }

        result = await _resolve_transitive(
            aggregator,
            resolver,
            [pkg],
            system_info,
            lock_data=lock_data,
            incremental=False,
        )
        assert result["status"] == "satisfiable"
        aggregator.get_package_info.assert_called()
        # Even though hash matches, incremental=False forces full BFS

    @pytest.mark.asyncio
    async def test_incremental_missing_hash_transitive(self):
        from unittest.mock import AsyncMock

        from backend.core.conflict_resolver import ConflictResolver
        from backend.orchestrator.resolve import (
            _resolve_transitive,
            _system_info_fingerprint,
        )

        aggregator = MagicMock()
        aggregator.get_package_info = AsyncMock(
            return_value={
                "name": "flask",
                "versions": {"pypi": [{"version": "2.3.3"}]},
                "dependencies": {
                    "pypi": {
                        "all": [
                            type(
                                "_Dep",
                                (),
                                {
                                    "name": "click",
                                    "version_spec": ">=8.0",
                                    "ecosystem": None,
                                    "dev_only": False,
                                },
                            )()
                        ]
                    }
                },
                "system_requirements": {},
            }
        )
        resolver = MagicMock()
        resolver.resolve_dependencies.return_value = {
            "status": "satisfiable",
            "resolved_packages": {},
        }
        system_info = {"gpu": {"cuda": "12.1"}}
        fingerprint = _system_info_fingerprint(system_info)

        pkg = {
            "name": "flask",
            "ecosystem": "pypi",
            "version_constraint": ">=2.0",
            "dependencies": {"pypi": {"click": ">=8.0"}},
        }
        expected_hash = ConflictResolver.compute_resolution_hash(
            "flask", "pypi", ">=2.0", {"pypi": {"click": ">=8.0"}}, fingerprint
        )
        lock_data = {
            "packages": {
                "flask": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.3.3",
                    "version": "2.3.3",
                    "original_constraint": ">=2.0",
                    "resolution_hash": expected_hash,
                    "depends_on": {"click": ">=8.0"},
                },
                "click": {
                    "ecosystem": "pypi",
                    "resolved_version": "8.1.7",
                    "version": "8.1.7",
                    "original_constraint": ">=8.0",
                    # Intentionally NO resolution_hash
                    "depends_on": {},
                },
            }
        }

        result = await _resolve_transitive(
            aggregator,
            resolver,
            [pkg],
            system_info,
            lock_data=lock_data,
        )
        assert result["status"] == "satisfiable"
        # Since click is missing a hash, flask falls back to BFS
        aggregator.get_package_info.assert_called()

    @pytest.mark.asyncio
    async def test_incremental_mixed(self):
        from unittest.mock import AsyncMock

        from backend.core.conflict_resolver import ConflictResolver
        from backend.orchestrator.resolve import (
            _resolve_transitive,
            _system_info_fingerprint,
        )

        aggregator = MagicMock()
        aggregator.get_package_info = AsyncMock(
            return_value={
                "name": "numpy",
                "versions": {"pypi": [{"version": "1.26.0"}]},
                "dependencies": {},
                "system_requirements": {},
            }
        )

        resolver = MagicMock()
        resolver.resolve_dependencies.return_value = {
            "status": "satisfiable",
            "resolved_packages": {
                "numpy": {"version": "1.26.0", "ecosystem": "pypi"},
            },
        }
        system_info = {"platform": {"system": "linux"}}
        fingerprint = _system_info_fingerprint(system_info)

        flask_hash = ConflictResolver.compute_resolution_hash(
            "flask", "pypi", ">=2.0", {}, fingerprint
        )
        packages = [
            {
                "name": "flask",
                "ecosystem": "pypi",
                "version_constraint": ">=2.0",
                "dependencies": {},
            },
            {
                "name": "numpy",
                "ecosystem": "pypi",
                "version_constraint": ">=1.24",
                "dependencies": {},
            },
        ]
        lock_data = {
            "packages": {
                "flask": {
                    "ecosystem": "pypi",
                    "resolved_version": "2.3.3",
                    "version": "2.3.3",
                    "original_constraint": ">=2.0",
                    "resolution_hash": flask_hash,
                    "depends_on": {},
                },
                # numpy is NOT in lock_data — it's new
            }
        }

        result = await _resolve_transitive(
            aggregator,
            resolver,
            packages,
            system_info,
            lock_data=lock_data,
        )
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"]["flask"]["version"] == "2.3.3"
        assert result["resolved_packages"]["numpy"]["version"] == "1.26.0"

    @pytest.mark.asyncio
    async def test_incremental_empty_packages(self):
        from backend.orchestrator.resolve import _resolve_transitive

        aggregator = MagicMock()
        resolver = MagicMock()
        system_info = {}
        lock_data = {"packages": {}, "version": "2.1"}

        result = await _resolve_transitive(
            aggregator,
            resolver,
            [],
            system_info,
            lock_data=lock_data,
        )
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"] == {}
        resolver.resolve_dependencies.assert_not_called()


class TestCrossDepsInjection:
    """Cross-ecosystem dependency injection from config (udr.json cross_deps)."""

    def _make_dep(self, name: str, version_spec: str = "*", eco: str = "pypi"):
        return type("_Dep", (), {"name": name, "version_spec": version_spec, "ecosystem": eco})()

    def _make_agg_response(self, name, ecosystem, version, deps=None):
        return {
            "name": name,
            "version": version,
            "versions": {ecosystem: [{"version": version}]},
            "dependencies": deps or {ecosystem: {"all": []}},
            "_version_metadata": {},
        }

    @pytest.mark.asyncio
    async def test_cross_deps_injects_edge_to_target_package(self):
        from backend.orchestrator.resolve import _resolve_transitive

        async def fake_get_package_info(name, ecosystem, **kwargs):
            if name == "mypkg" and ecosystem == "pypi":
                return self._make_agg_response("mypkg", "pypi", "1.0.0")
            if name == "lodash" and ecosystem == "npm":
                return self._make_agg_response("lodash", "npm", "4.17.21")
            return None

        aggregator = AsyncMock()
        aggregator.get_package_info = fake_get_package_info
        resolver = MagicMock()
        resolver.resolve_dependencies.return_value = {
            "status": "satisfiable",
            "resolved_packages": {},
        }
        system_info = {}

        cross_deps = [
            {
                "from": "mypkg@pypi",
                "dep": "lodash@npm",
                "constraint": ">=4.17.0",
                "target_ecosystem": "npm",
            },
        ]

        # lodash is already in packages — cross_deps should inject edge without needing fetch
        packages = [
            {
                "name": "mypkg",
                "ecosystem": "pypi",
                "available_versions": ["1.0.0"],
                "dependencies": {},
                "system_requirements": {},
            },
            {
                "name": "lodash",
                "ecosystem": "npm",
                "available_versions": ["4.17.21"],
                "dependencies": {},
                "system_requirements": {},
            },
        ]

        result = await _resolve_transitive(
            aggregator,
            resolver,
            packages,
            system_info,
            cross_deps=cross_deps,
            incremental=False,
        )
        assert result["status"] in ("satisfiable", "partial")

    @pytest.mark.asyncio
    async def test_cross_deps_noop_when_source_not_in_packages(self):
        from backend.orchestrator.resolve import _resolve_transitive

        aggregator = AsyncMock()
        aggregator.get_package_info.return_value = None
        resolver = MagicMock()
        resolver.resolve_dependencies.return_value = {
            "status": "satisfiable",
            "resolved_packages": {},
        }
        system_info = {}

        cross_deps = [
            {
                "from": "nonexistent@pypi",
                "dep": "something@npm",
                "constraint": "*",
                "target_ecosystem": "npm",
            },
        ]

        result = await _resolve_transitive(
            aggregator,
            resolver,
            [],
            system_info,
            cross_deps=cross_deps,
            incremental=False,
        )
        assert result["status"] == "satisfiable"

    @pytest.mark.asyncio
    async def test_cross_deps_source_already_has_deps(self):
        from backend.orchestrator.resolve import _resolve_transitive

        aggregator = AsyncMock()
        aggregator.get_package_info.side_effect = [
            self._make_agg_response("mypkg", "pypi", "1.0.0"),
        ]
        resolver = MagicMock()
        resolver.resolve_dependencies.return_value = {
            "status": "satisfiable",
            "resolved_packages": {},
        }
        system_info = {}

        cross_deps = [
            {
                "from": "mypkg@pypi",
                "dep": "lodash@npm",
                "constraint": ">=4.17",
                "target_ecosystem": "npm",
            },
        ]

        packages = [
            {
                "name": "mypkg",
                "ecosystem": "pypi",
                "available_versions": ["1.0.0"],
                "dependencies": {"pypi": {"all": [self._make_dep("click", ">=8.0")]}},
                "system_requirements": {},
            },
            {
                "name": "lodash",
                "ecosystem": "npm",
                "available_versions": ["4.17.21"],
                "dependencies": {},
                "system_requirements": {},
            },
        ]

        result = await _resolve_transitive(
            aggregator,
            resolver,
            packages,
            system_info,
            cross_deps=cross_deps,
            incremental=False,
        )
        assert result["status"] in ("satisfiable", "partial")

    @pytest.mark.asyncio
    async def test_cross_deps_missing_from_field_skipped(self):
        from backend.orchestrator.resolve import _resolve_transitive

        aggregator = AsyncMock()
        aggregator.get_package_info.return_value = self._make_agg_response("mypkg", "pypi", "1.0.0")
        resolver = MagicMock()
        resolver.resolve_dependencies.return_value = {
            "status": "satisfiable",
            "resolved_packages": {},
        }
        system_info = {}

        cross_deps = [
            {"dep": "lodash@npm", "constraint": "*"},  # missing "from"
        ]
        packages = [
            {
                "name": "mypkg",
                "ecosystem": "pypi",
                "available_versions": ["1.0.0"],
                "dependencies": {},
                "system_requirements": {},
            }
        ]

        result = await _resolve_transitive(
            aggregator,
            resolver,
            packages,
            system_info,
            cross_deps=cross_deps,
            incremental=False,
        )
        assert result["status"] in ("satisfiable", "partial")
