# tests/unit/test_core/test_conflict_resolver.py
import asyncio

import pytest
from unittest.mock import MagicMock, patch, call
import z3

from backend.core.cache import cache_manager
from backend.core.conflict_resolver import ConflictResolver


@pytest.fixture(autouse=True)
def reset_cache_stats():
    """Reset cache stats between tests"""
    original_stats = cache_manager._cache_stats.copy()
    cache_manager._cache_stats = {"hits": 0, "misses": 0, "errors": 0}
    yield
    cache_manager._cache_stats = original_stats


class TestConflictResolver:
    @pytest.fixture
    def resolver(self):
        """Create ConflictResolver instance for testing"""
        return ConflictResolver()

    def test_initialization(self, resolver):
        """Test ConflictResolver initialization"""
        assert resolver.dependency_graph is not None
        assert resolver.solver is not None
        assert resolver.version_vars == {}
        assert resolver.version_to_int == {}
        assert resolver.int_to_version == {}

    def test_resolve_empty_packages(self, resolver):
        """Test error handling for empty packages"""
        result = resolver.resolve_dependencies([], {})
        assert result["status"] == "error"
        assert "At least one package must be provided" in result["message"]
        assert result["resolved_packages"] == {}

    def test_resolve_no_system_info(self, resolver):
        """Test handling when no system info is provided"""
        packages = [{"name": "requests", "version_spec": ">=2.0.0"}]

        with patch.object(
            resolver, "_get_default_system_info", return_value={"os": "linux"}
        ):
            result = resolver.resolve_dependencies(packages, {})

        assert result["status"] in ["success", "error"]

    def test_solver_timeout_applied_and_reset(self, resolver):
        """Ensure solver timeout propagates and resets between runs"""
        packages = [{"name": "requests", "available_versions": ["1.0.0"]}]
        system_info = {"os": "linux"}

        with patch.object(resolver.solver, "set") as mock_set, patch.object(
            resolver.solver, "reset"
        ):
            resolver.resolve_dependencies(packages, system_info, solver_timeout=1500)
            resolver.resolve_dependencies(packages, system_info, solver_timeout=None)

        assert mock_set.call_count == 2
        assert mock_set.call_args_list[0] == call(timeout=1500)
        assert mock_set.call_args_list[1] == call(timeout=0)

    def test_version_mapping_creation(self, resolver):
        """Test version mapping creation for Z3 solver"""
        versions = ["1.0.0", "2.0.0", "1.5.0"]

        resolver._create_version_mapping("test-package", versions)

        assert "test-package_1.0.0" in resolver.version_to_int
        assert "test-package_2.0.0" in resolver.version_to_int
        assert "test-package_1.5.0" in resolver.version_to_int

        # Should be sorted by version
        assert resolver.version_to_int["test-package_1.0.0"] == 0
        assert resolver.version_to_int["test-package_1.5.0"] == 1
        assert resolver.version_to_int["test-package_2.0.0"] == 2

    def test_dependency_graph_building(self, resolver):
        """Test building dependency graph from packages"""
        packages = [
            {
                "name": "package-a",
                "ecosystem": "pypi",
                "dependencies": {
                    "pypi": {"package-b": ">=1.0.0", "package-c": "==2.0.0"}
                },
            },
            {"name": "package-b", "ecosystem": "pypi"},
        ]

        resolver._build_dependency_graph(packages)

        assert "package-a@pypi" in resolver.dependency_graph
        assert "package-b@pypi" in resolver.dependency_graph
        assert "package-c@pypi" in resolver.dependency_graph

        # Check edges
        edges = list(resolver.dependency_graph.edges())
        assert len(edges) == 2  # Two dependencies from package-a

    @patch("z3.Solver.check")
    @patch("z3.Solver.model")
    def test_solve_constraints_satisfiable(self, mock_model, mock_check, resolver):
        """Test constraint solving when satisfiable"""
        mock_check.return_value = z3.sat
        mock_model_instance = MagicMock()
        mock_model.return_value = mock_model_instance

        # Setup some version variables
        resolver.version_vars = {"pkg_1.0.0": z3.Bool("pkg_1.0.0")}

        packages = [{"name": "test-pkg", "available_versions": ["1.0.0"]}]
        system_info = {}

        result = resolver._solve_constraints(
            {"package_versions": {}, "system_requirements": {}, "conflicts": [], "dependencies": []},
            False,
        )

        assert result["status"] == "satisfiable"

    @patch("z3.Solver.check")
    def test_solve_constraints_unsatisfiable(self, mock_check, resolver):
        """Test constraint solving when unsatisfiable"""
        mock_check.return_value = z3.unsat

        result = resolver._solve_constraints({}, False)

        assert result["status"] == "unsatisfiable"

    @pytest.mark.asyncio
    async def test_batch_resolution(self, resolver):
        """Test parallel batch resolution"""
        package_batches = [
            [{"name": "numpy", "version_spec": ">=1.0.0"}],
            [{"name": "pandas", "version_spec": ">=1.0.0"}],
        ]
        system_info = {"python_version": "3.9"}

        with patch.object(resolver, "resolve_dependencies_async") as mock_resolve:
            mock_resolve.return_value = {"status": "success", "resolved_packages": {}}

            results = await resolver.resolve_batch(package_batches, system_info)

            assert len(results) == 2
            assert all(r["status"] == "success" for r in results)
            assert mock_resolve.call_count == 2

            # Ensure resolver calls do not persist solver timeout defaults
            for call_args in mock_resolve.call_args_list:
                assert call_args.kwargs.get("solver_timeout", 0) == 0

    @pytest.mark.asyncio
    async def test_batch_resolution_with_errors(self, resolver):
        """Test batch resolution error handling"""
        package_batches = [[{"name": "numpy"}], [{"name": "pandas"}]]
        system_info = {}

        with patch.object(resolver, "resolve_dependencies_async") as mock_resolve:
            mock_resolve.side_effect = [
                Exception("Network error"),
                {"status": "success"},
            ]

            results = await resolver.resolve_batch(package_batches, system_info)

            assert len(results) == 2
            assert results[0]["status"] == "error"
            assert "An unexpected internal error occurred" in results[0]["message"]
            assert results[1]["status"] == "success"

            # Ensure solver timeout reset is applied even when errors occur
            for call_args in mock_resolve.call_args_list:
                assert call_args.kwargs.get("solver_timeout", 0) == 0

    @pytest.mark.asyncio
    async def test_batch_resolution_runs_batches_concurrently(self, resolver):
        """Ensure resolve_batch launches batch resolutions concurrently"""
        package_batches = [[{"name": "batch-a"}], [{"name": "batch-b"}]]
        system_info = {}

        started = 0
        start_event = asyncio.Event()

        async def fake_resolve(packages, *_args, **_kwargs):
            nonlocal started
            started += 1
            if started == len(package_batches):
                start_event.set()
            await start_event.wait()
            await asyncio.sleep(0)  # Yield control to simulate work
            return {"status": "success", "batch": packages[0]["name"]}

        with patch.object(
            resolver, "resolve_dependencies_async", side_effect=fake_resolve
        ) as mock_resolve:
            results = await asyncio.wait_for(
                resolver.resolve_batch(package_batches, system_info), timeout=1.0
            )

        assert start_event.is_set()
        assert mock_resolve.call_count == len(package_batches)
        assert {r["batch"] for r in results if r["status"] == "success"} == {
            "batch-a",
            "batch-b",
        }

    @pytest.mark.asyncio
    async def test_batch_resolution_concurrent_failure_isolated(self, resolver):
        """Failures in one batch should not block other concurrent results"""
        package_batches = [[{"name": "good"}], [{"name": "bad"}]]
        system_info = {}

        started = 0
        start_event = asyncio.Event()

        async def fake_resolve(packages, *_args, **_kwargs):
            nonlocal started
            started += 1
            if started == len(package_batches):
                start_event.set()
            await start_event.wait()
            if packages[0]["name"] == "bad":
                raise RuntimeError("boom")
            return {"status": "success"}

        with patch.object(
            resolver, "resolve_dependencies_async", side_effect=fake_resolve
        ) as mock_resolve:
            results = await asyncio.wait_for(
                resolver.resolve_batch(package_batches, system_info), timeout=1.0
            )

        assert start_event.is_set()
        assert mock_resolve.call_count == len(package_batches)
        statuses = [result["status"] for result in results]
        assert statuses.count("success") == 1
        assert statuses.count("error") == 1
        error_messages = [
            result["message"] for result in results if result["status"] == "error"
        ]
        assert any("occurred" in message for message in error_messages)

    def test_format_solution(self, resolver):
        """Test solution formatting"""
        solution = {
            "status": "satisfiable",
            "packages": {},
            "warnings": [],
        }

        result = resolver._format_solution(solution)

        assert "resolved_packages" in result
        assert "dependency_tree" in result
        assert "warnings" in result

    def test_default_system_info(self, resolver):
        """Test default system info generation"""
        default_info = resolver._get_default_system_info()

        assert "os" in default_info
        assert "architecture" in default_info
        assert "runtime_versions" in default_info
        assert "python" in default_info["runtime_versions"]

    def test_cache_key_generation(self, resolver):
        """Test cache key generation for resolution results"""
        packages = [{"name": "numpy", "version": "1.24.0"}]
        system_info = {"python": "3.9"}

        key = resolver._generate_resolution_cache_key(packages, system_info)

        assert isinstance(key, str)
        assert len(key) > 0

        # Same inputs should generate same key
        key2 = resolver._generate_resolution_cache_key(packages, system_info)
        assert key == key2

        # Different inputs should generate different key
        key3 = resolver._generate_resolution_cache_key(
            [{"name": "pandas"}], system_info
        )
        assert key != key3

    def test_solver_reset(self, resolver):
        """Test that solver state is properly reset"""
        # Add some state
        resolver.version_vars["test"] = "value"
        resolver.version_to_int["test"] = 1
        resolver.int_to_version["test"] = "1.0.0"

        # Call resolve which should reset
        resolver.resolve_dependencies([], {})

        # Check reset occurred
        assert resolver.version_vars == {}
        assert resolver.version_to_int == {}
        assert resolver.int_to_version == {}

    def test_error_handling_in_resolution(self, resolver):
        """Test error handling during resolution process"""
        # Force an exception during graph building
        with patch.object(
            resolver, "_build_dependency_graph", side_effect=Exception("Graph error")
        ):
            result = resolver.resolve_dependencies(
                [{"name": "test", "available_versions": ["1.0.0"]}], {}
            )

            assert result["status"] == "error"
            assert "unexpected internal error" in result["message"]
            assert "Graph error" in str(result.get("details", {}))

    @pytest.mark.asyncio
    async def test_async_resolution_with_caching(self, resolver):
        """Test async resolution with caching enabled"""
        packages = [{"name": "requests", "version_spec": ">=2.0.0"}]
        system_info = {"python_version": "3.9"}

        with patch.object(resolver, "_resolve_dependencies_sync") as mock_sync:
            mock_sync.return_value = {"status": "success"}

            result = await resolver.resolve_dependencies_async(packages, system_info)

            assert result["status"] == "success"
            mock_sync.assert_called_once_with(packages, system_info, True, None)

    @pytest.mark.asyncio
    async def test_async_resolution_propagates_timeout_and_caches(
        self, resolver, monkeypatch
    ):
        """Ensure async wrapper forwards solver timeout and caches results"""
        packages = [{"name": "requests", "version_spec": ">=2.0.0"}]
        system_info = {"python_version": "3.9"}

        async def fake_get(key):
            fake_get.calls.append(key)
            return fake_get.results.pop(0)

        async def fake_set(key, value, ttl):
            fake_set.calls.append((key, value, ttl))
            return True

        fake_get.calls = []
        fake_get.results = [None, {"status": "success"}]
        fake_set.calls = []

        monkeypatch.setattr(cache_manager, "get", fake_get)
        monkeypatch.setattr(cache_manager, "set", fake_set)

        # First call should miss cache and invoke sync resolver with timeout propagation
        with patch.object(resolver, "_resolve_dependencies_sync") as mock_sync:
            mock_sync.return_value = {"status": "success"}
            result = await resolver.resolve_dependencies_async(
                packages, system_info, solver_timeout=2500
            )
            assert result["status"] == "success"
            mock_sync.assert_called_once_with(packages, system_info, True, 2500)

        # Second call should hit cache and avoid re-invoking sync resolver
        with patch.object(resolver, "_resolve_dependencies_sync") as mock_sync:
            result = await resolver.resolve_dependencies_async(
                packages, system_info, solver_timeout=2500
            )
            assert result["status"] == "success"
            mock_sync.assert_not_called()

        assert len(fake_get.calls) == 2
        assert len(fake_set.calls) == 1
        assert fake_set.calls[0][1] == {"status": "success"}

    def test_complex_dependency_scenario(self, resolver):
        """Test resolution with complex dependencies (mocked)"""
        packages = [
            {
                "name": "tensorflow",
                "available_versions": ["2.13.0", "2.14.0", "2.15.0"],
                "dependencies": {"pypi": {"numpy": ">=1.24.0", "protobuf": ">=3.20.0"}},
            },
            {
                "name": "torch",
                "available_versions": ["2.0.0", "2.1.0"],
                "dependencies": {"pypi": {"numpy": ">=1.21.0"}},
            },
        ]

        # Mock successful resolution
        with patch.object(resolver, "_solve_constraints") as mock_solve:
            mock_solve.return_value = {
                "status": "satisfiable",
                "packages": {},
                "warnings": [],
            }

            result = resolver.resolve_dependencies(packages, {})

            assert "resolved_packages" in result
            mock_solve.assert_called_once()
