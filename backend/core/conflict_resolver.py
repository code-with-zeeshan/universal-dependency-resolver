"""Module docstring."""

# conflict_resolver.py
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
import platform
import re
import uuid
from typing import TYPE_CHECKING, Any

import networkx as nx
from packaging import version

if TYPE_CHECKING:
    import z3

from backend.utils.errors import (
    ResolverError,
    ResolverErrorCode,
    ensure_details_context,
    make_internal_error,
)

from .cache import cached
from .utils import (
    compare_versions,
    is_compatible_version,
    normalize_package_name,
    parse_version,
)

logger = logging.getLogger(__name__)

SOLVER_MAX_VARS = int(os.environ.get("SOLVER_MAX_VARS", "5000"))
SOLVER_MAX_CLUSTERS = int(os.environ.get("SOLVER_MAX_CLUSTERS", "5"))
SOLVER_PRERELEASE_PENALTY = int(os.environ.get("SOLVER_PRERELEASE_PENALTY", "100000"))
USE_OPTIMIZATION = os.environ.get("USE_Z3_OPTIMIZE", "true").lower() == "true"

# Data-driven conflict rules: each rule specifies incompatible version ranges
# across packages or ecosystems.  Used by _add_conflict_constraints().
CONFLICT_RULES: list[dict[str, Any]] = [
    {
        "id": "cuda:min_version >=11.0,<12.0 vs cuda:min_version >=12.0,<13.0",
        "type": "cuda",
        "constraint_a": {"field": "cuda.min_version", "op": ">=", "value": "11.0"},
        "constraint_b": {"field": "cuda.min_version", "op": "<", "value": "12.0"},
        "mutually_exclusive_with": {
            "field": "cuda.min_version",
            "op": ">=",
            "value": "12.0",
        },
    },
    {
        "id": "cuda:min_version >=12.0,<13.0 vs cuda:min_version >=11.0,<12.0",
        "type": "cuda",
        "constraint_a": {"field": "cuda.min_version", "op": ">=", "value": "12.0"},
        "constraint_b": {"field": "cuda.min_version", "op": "<", "value": "13.0"},
        "mutually_exclusive_with": {
            "field": "cuda.min_version",
            "op": ">=",
            "value": "11.0",
        },
    },
    {
        "id": "tensorflow vs numpy upper bound",
        "type": "dependency",
        "description": "tensorflow 2.15+ requires numpy <1.28",
        "packages": ["tensorflow"],
        "constraint": {"numpy": "<1.28"},
    },
]


class ConflictResolver:
    """Resolves dependency conflicts using constraint satisfaction and graph algorithms."""

    def __init__(self, use_optimization: bool | None = None):
        """Initialize the conflict resolver with Z3 solver and dependency graph.

        Args:
            use_optimization: If True, use z3.Optimize() with minimize() objectives
                to prefer newer versions. If None, falls back to USE_Z3_OPTIMIZE env var.

        """
        import z3

        self.dependency_graph = nx.DiGraph()
        if use_optimization is None:
            use_optimization = USE_OPTIMIZATION
        self._use_optimization = use_optimization
        self._solver = z3.Optimize() if use_optimization else z3.Solver()
        self.version_vars = {}  # Maps package_version strings to Z3 variables
        self.version_to_int = {}  # Maps version strings to integers for Z3
        self.int_to_version = {}  # Reverse mapping
        self._version_weights = []  # Weights for minimize() objective
        self._minimization_added = False
        self.offline_mode = False

    @property
    def solver(self):
        """Get the Z3 solver instance (backward-compatible access)."""
        return self._solver

    # Additional error handling enhancements
    def resolve_dependencies(
        self,
        packages: list[dict[str, Any]],
        system_info: dict[str, Any] | None = None,
        prefer_compatibility: bool = True,
        solver_timeout: int | None = None,
    ) -> dict[str, Any]:
        """Resolve package dependencies and conflicts."""
        # Clear previous solver state
        self.version_vars.clear()
        self.version_to_int.clear()
        self.int_to_version.clear()

        resolution_context = {
            "package_count": len(packages),
            "solver_timeout_ms": solver_timeout,
        }

        try:
            normalized_packages = self._normalize_packages(packages, resolution_context)
            resolution_context["normalized_package_count"] = len(normalized_packages)

            self._validate_package_inputs(normalized_packages, resolution_context)
            system_info = self._prepare_system_info(system_info, resolution_context)
            self._reset_solver_state(solver_timeout)

            logger.info(
                "Starting dependency resolution",
                extra={"event": "dependency_resolution_start", **resolution_context},
            )

            self._build_dependency_graph(normalized_packages)
            logger.debug(
                "Dependency graph built",
                extra={
                    "event": "dependency_graph_built",
                    "node_count": self.dependency_graph.number_of_nodes(),
                    **resolution_context,
                },
            )

            constraints = self._create_constraints(normalized_packages, system_info)
            logger.debug(
                "Constraints prepared",
                extra={
                    "event": "constraints_prepared",
                    "constraint_count": len(self.solver.assertions()),
                    **resolution_context,
                },
            )

            solution = self._solve_constraints(constraints, prefer_compatibility)

            if solution["status"] == "satisfiable":
                logger.info(
                    "Dependency resolution successful",
                    extra={
                        "event": "dependency_resolution_success",
                        **resolution_context,
                    },
                )
                return self._format_solution(solution)

            if solution["status"] == "timeout":
                logger.warning(
                    "Solver timeout, attempting alternatives",
                    extra={
                        "event": "dependency_resolution_timeout",
                        **resolution_context,
                    },
                )
            else:
                logger.warning(
                    "Dependency resolution unsatisfiable, attempting alternatives",
                    extra={
                        "event": "dependency_resolution_unsat",
                        **resolution_context,
                    },
                )
            return self._resolve_with_alternatives(normalized_packages, system_info)

        except ResolverError as exc:
            logger.warning(
                "Resolver error encountered",
                extra={
                    "event": "dependency_resolution_error",
                    "code": exc.category.value if exc.category else "unknown",
                    "log_msg": exc.message,
                    "details": exc.details,
                    **resolution_context,
                },
            )
            return exc.to_payload()
        except Exception as exc:
            correlation_id = str(uuid.uuid4())
            error = make_internal_error(
                exc,
                context=ensure_details_context(
                    None,
                    **resolution_context,
                    scope="resolve_dependencies",
                ),
                correlation_id=correlation_id,
            )
            logger.exception(
                "Unexpected error during dependency resolution",
                extra={
                    "event": "dependency_resolution_unexpected_error",
                    "correlation_id": correlation_id,
                    **resolution_context,
                },
            )
            return error.to_payload()

    async def resolve_batch(
        self, package_batches: list[list[dict]], system_info: dict
    ) -> list[dict]:
        """Resolve multiple independent package batches in parallel using asyncio.

        Args:
            package_batches: List of package batch lists, each containing packages to resolve
            system_info: Dictionary containing system requirements

        Returns:
            List of resolution results for each batch

        """
        batch_context = {"batch_count": len(package_batches)}

        try:
            if not package_batches:
                logger.warning(
                    "No package batches provided for batch resolution",
                    extra={"event": "batch_resolution_empty_input"},
                )
                return []

            if not system_info:
                logger.warning(
                    "No system info provided for batch resolution; using defaults",
                    extra={"event": "batch_resolution_system_info_default"},
                )
                system_info = self._get_default_system_info()

            tasks = [
                self.resolve_dependencies_async(batch, system_info) for batch in package_batches
            ]

            logger.info(
                "Starting parallel batch resolution",
                extra={"event": "batch_resolution_start", **batch_context},
            )
            results = await asyncio.gather(*tasks, return_exceptions=True)

            processed_results: list[Any] = []
            for index, result in enumerate(results):
                if isinstance(result, Exception):
                    correlation_id = str(uuid.uuid4())
                    error = make_internal_error(
                        result,
                        context=ensure_details_context(
                            None,
                            **batch_context,
                            scope="batch_resolution_task",
                            batch_index=index,
                        ),
                        correlation_id=correlation_id,
                    )
                    logger.error(
                        "Batch resolution failed",
                        extra={
                            "event": "batch_resolution_failure",
                            "batch_index": index,
                            "correlation_id": correlation_id,
                            "error": str(result),
                            **batch_context,
                        },
                    )
                    processed_results.append(error.to_payload())
                else:
                    processed_results.append(result)

            logger.info(
                "Completed parallel batch resolution",
                extra={"event": "batch_resolution_complete", **batch_context},
            )
            return processed_results

        except Exception as exc:
            correlation_id = str(uuid.uuid4())
            error = make_internal_error(
                exc,
                context=ensure_details_context(
                    None,
                    **batch_context,
                    scope="batch_resolution",
                ),
                correlation_id=correlation_id,
            )
            logger.exception(
                "Unexpected error during batch resolution",
                extra={
                    "event": "batch_resolution_unexpected_error",
                    "correlation_id": correlation_id,
                    **batch_context,
                },
            )
            return [error.to_payload() for _ in package_batches]

    def _generate_resolution_cache_key(self, packages: list[dict], system_info: dict) -> str:
        """Generate a cache key for resolution results based on packages and system info."""
        # Create a deterministic representation of packages
        package_data = []
        for pkg in packages:
            pkg_copy = pkg.copy()
            # Sort keys for consistency
            sorted_pkg = {k: pkg_copy[k] for k in sorted(pkg_copy.keys())}
            package_data.append(sorted_pkg)

        # Create system info hash
        system_hash = hashlib.md5(json.dumps(system_info, sort_keys=True).encode()).hexdigest()

        # Create packages hash
        packages_hash = hashlib.md5(json.dumps(package_data, sort_keys=True).encode()).hexdigest()

        return f"resolution:{packages_hash}:{system_hash}"

    @cached(ttl=3600, key_prefix="dependency_resolution")  # 1 hour cache
    async def resolve_dependencies_async(
        self,
        packages: list[dict[str, Any]],
        system_info: dict[str, Any],
        prefer_compatibility: bool = True,
        solver_timeout: int | None = None,
    ) -> dict[str, Any]:
        """Async wrapper for resolve_dependencies with caching.

        This method provides the same functionality as resolve_dependencies but with
        Redis-based caching for improved performance on repeated requests.
        """
        # Run the synchronous resolution in a thread pool to avoid blocking
        import concurrent.futures
        import functools

        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            func = functools.partial(
                self._resolve_dependencies_sync,
                packages,
                system_info,
                prefer_compatibility,
                solver_timeout,
            )
            result = await loop.run_in_executor(executor, func)
            return result

    def _resolve_dependencies_sync(
        self,
        packages: list[dict[str, Any]],
        system_info: dict[str, Any],
        prefer_compatibility: bool = True,
        solver_timeout: int | None = None,
    ) -> dict[str, Any]:
        """Synchronous implementation of dependency resolution (extracted for caching)."""
        try:
            return self.resolve_dependencies(
                packages,
                system_info,
                prefer_compatibility,
                solver_timeout=solver_timeout,
            )
        except ResolverError:
            raise
        except Exception as exc:
            correlation_id = str(uuid.uuid4())
            error = make_internal_error(
                exc,
                context=ensure_details_context(
                    None,
                    scope="resolve_dependencies_sync",
                    package_count=len(packages),
                    solver_timeout_ms=solver_timeout,
                ),
                correlation_id=correlation_id,
            )
            logger.exception(
                "Unexpected error during synchronous dependency resolution",
                extra={
                    "event": "resolve_dependencies_sync_unexpected_error",
                    "correlation_id": correlation_id,
                    "package_count": len(packages),
                    "solver_timeout_ms": solver_timeout,
                },
            )
            return error.to_payload()

    def _normalize_packages(
        self, packages: list[dict[str, Any]], resolution_context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Normalize package structures and names before processing."""
        context = {**resolution_context, "scope": "package_normalization"}

        if not isinstance(packages, list):
            raise ResolverError(
                message="Packages payload must be a list of package definitions.",
                code=ResolverErrorCode.VALIDATION_ERROR,
                details={"provided_type": type(packages).__name__, **context},
            )

        normalized_packages: list[dict[str, Any]] = []
        normalization_failures: list[dict[str, Any]] = []

        for index, package in enumerate(packages):
            if not isinstance(package, dict):
                normalization_failures.append(
                    {
                        "index": index,
                        "reason": "package must be a dictionary",
                        "provided_type": type(package).__name__,
                    }
                )
                continue

            if not isinstance(package, dict) or not package.get("name"):
                normalization_failures.append(
                    {"index": index, "reason": "package missing required fields"}
                )
                continue

            normalized_name = normalize_package_name(package["name"])
            normalized_package = copy.deepcopy(package)
            normalized_package["name"] = normalized_name

            dependencies = normalized_package.get("dependencies", {})
            if not isinstance(dependencies, dict):
                normalization_failures.append(
                    {"index": index, "reason": "dependencies must be a dictionary"}
                )
                continue

            normalized_dependencies: dict[str, dict[str, str]] = {}
            for ecosystem, deps in dependencies.items():
                if not isinstance(deps, dict):
                    normalization_failures.append(
                        {
                            "index": index,
                            "reason": "dependency entries must be dictionaries",
                            "ecosystem": ecosystem,
                        }
                    )
                    break

                normalized_dependencies[ecosystem] = {}
                for dep_name, constraint in deps.items():
                    normalized_dependencies[ecosystem][normalize_package_name(dep_name)] = (
                        constraint
                    )
            else:
                normalized_package["dependencies"] = normalized_dependencies

            normalized_packages.append(normalized_package)

        if normalization_failures:
            raise ResolverError(
                message="One or more packages failed normalization.",
                code=ResolverErrorCode.VALIDATION_ERROR,
                details={"failures": normalization_failures, **context},
            )

        return normalized_packages

    def _prepare_system_info(
        self, system_info: dict[str, Any] | None, resolution_context: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalize, validate, and augment system information.

        Args:
            system_info: Optional user-provided system metadata.
            resolution_context: Shared context used for logging and error reporting.

        Returns:
            A validated system info dictionary.

        Raises:
            ResolverError: If the provided system info fails validation.

        """
        context = {**resolution_context, "scope": "system_info_preparation"}

        try:
            if system_info is None:
                resolved_system_info = self._get_default_system_info()
                context["system_info_source"] = "default"
            else:
                if not isinstance(system_info, dict):
                    raise ResolverError(
                        message="System information must be a dictionary.",
                        code=ResolverErrorCode.SYSTEM_INFO_ERROR,
                        details={
                            "provided_type": type(system_info).__name__,
                            **context,
                        },
                    )

                resolved_system_info = copy.deepcopy(system_info)
                context["system_info_source"] = "provided"

            # Ensure required sections exist
            resolved_system_info.setdefault("os", "unknown")
            resolved_system_info.setdefault("architecture", "unknown")
            resolved_system_info.setdefault("runtime_versions", {})
            resolved_system_info.setdefault("gpu", {"available": False, "cuda": None})

            runtime_versions = resolved_system_info["runtime_versions"]
            if not isinstance(runtime_versions, dict):
                raise ResolverError(
                    message="runtime_versions must be a dictionary.",
                    code=ResolverErrorCode.SYSTEM_INFO_ERROR,
                    details={"runtime_versions": runtime_versions, **context},
                )

            python_info = runtime_versions.setdefault("python", {})
            if not isinstance(python_info, dict):
                raise ResolverError(
                    message="runtime_versions.python must be a dictionary.",
                    code=ResolverErrorCode.SYSTEM_INFO_ERROR,
                    details={"python": python_info, **context},
                )

            python_info.setdefault("version", self._get_default_python_version())

            gpu_info = resolved_system_info["gpu"]
            if not isinstance(gpu_info, dict):
                raise ResolverError(
                    message="gpu information must be a dictionary.",
                    code=ResolverErrorCode.SYSTEM_INFO_ERROR,
                    details={"gpu": gpu_info, **context},
                )

            gpu_info.setdefault("available", bool(gpu_info.get("cuda")))
            gpu_info.setdefault("cuda", None)

            context["resolved_system_info"] = {
                "os": resolved_system_info.get("os"),
                "architecture": resolved_system_info.get("architecture"),
                "python_version": python_info.get("version"),
                "cuda": gpu_info.get("cuda"),
            }
            return resolved_system_info

        except ResolverError:
            raise
        except Exception as exc:
            raise self._handle_unexpected_resolution_error(  # type: ignore[misc]
                exc, context, elevate=True
            ) from exc

    def _get_default_system_info(self) -> dict:
        """Provide default system info when none is provided."""
        return {
            "os": platform.system().lower(),
            "architecture": platform.machine(),
            "runtime_versions": {"python": {"version": f"{self._get_default_python_version()}"}},
            "gpu": {"available": False, "cuda": None},
        }

    def _reset_solver_state(self, solver_timeout: int | None = None) -> None:
        """Reset the solver state and apply timeout if specified."""
        import z3

        if self._use_optimization:
            self._solver = z3.Optimize()
            self._minimization_added = False
            self._version_weights = []
        else:
            self._solver = z3.Solver()
        if solver_timeout is not None:
            self.solver.set(timeout=solver_timeout)
        else:
            self.solver.set(timeout=0)

    @staticmethod
    def _get_default_python_version() -> str:
        """Get default python version."""
        import sys

        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    def _handle_unexpected_resolution_error(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
        *,
        elevate: bool = False,
    ) -> dict[str, Any]:
        """Convert unexpected errors into structured ResolverError payloads."""
        context = context or {}
        resolution_context = {
            **context,
            "event": "dependency_resolution_unexpected_error",
            "error_type": type(error).__name__,
        }

        correlation_id = str(uuid.uuid4())
        resolution_context["correlation_id"] = correlation_id

        logger.exception("Unexpected error during dependency resolution", extra=resolution_context)

        resolver_error = ResolverError(
            message="An unexpected error occurred during dependency resolution.",
            code=ResolverErrorCode.INTERNAL_ERROR,
            details={
                "correlation_id": correlation_id,
                "original_error": str(error),
                **context,
            },
        )

        if elevate:
            raise resolver_error from error

        payload = resolver_error.to_payload()
        return payload

    def _validate_package_inputs(
        self, packages: list[dict[str, Any]], resolution_context: dict[str, Any]
    ) -> None:
        """Validate normalized package inputs for resolver consistency."""
        validation_scope = {**resolution_context, "scope": "package_validation"}

        if not packages:
            raise ResolverError(
                message="At least one package must be provided for resolution.",
                code=ResolverErrorCode.VALIDATION_ERROR,
                details={**validation_scope, "reason": "empty_package_list"},
            )

        validation_errors: list[dict[str, Any]] = []

        for index, package in enumerate(packages):
            if not isinstance(package, dict):
                validation_errors.append(
                    {
                        **validation_scope,
                        "package_index": index,
                        "field": "package",
                        "reason": "package entries must be dictionaries",
                    }
                )
                continue

            package_context = {
                **validation_scope,
                "package_index": index,
                "package_name": package.get("name"),
            }

            if not package.get("name"):
                validation_errors.append(
                    {
                        **package_context,
                        "field": "name",
                        "reason": "missing_package_name",
                    }
                )

            ecosystem = package.get("ecosystem")
            if ecosystem is not None and not isinstance(ecosystem, str):
                validation_errors.append(
                    {
                        **package_context,
                        "field": "ecosystem",
                        "reason": "ecosystem must be a string",
                    }
                )

            versions_field = package.get("versions")
            if versions_field is not None and not isinstance(versions_field, list):
                validation_errors.append(
                    {
                        **package_context,
                        "field": "versions",
                        "reason": "versions must be a list when provided",
                    }
                )

            available_versions = package.get("available_versions", [])
            if not isinstance(available_versions, list) or not available_versions:
                validation_errors.append(
                    {
                        **package_context,
                        "field": "available_versions",
                        "reason": "available_versions must be a non-empty list of version strings",
                    }
                )
            elif not all(isinstance(version_str, str) for version_str in available_versions):
                validation_errors.append(
                    {
                        **package_context,
                        "field": "available_versions",
                        "reason": "available_versions entries must be strings",
                    }
                )
            elif len(set(available_versions)) != len(available_versions):
                validation_errors.append(
                    {
                        **package_context,
                        "field": "available_versions",
                        "reason": "available_versions contains duplicates",
                    }
                )

            dependencies = package.get("dependencies", {})
            if dependencies and not isinstance(dependencies, dict):
                validation_errors.append(
                    {
                        **package_context,
                        "field": "dependencies",
                        "reason": "dependencies must be a dictionary keyed by ecosystem",
                    }
                )
            elif isinstance(dependencies, dict):
                for dependency_ecosystem, dependency_map in dependencies.items():
                    ecosystem_context = {
                        **package_context,
                        "dependency_ecosystem": dependency_ecosystem,
                    }
                    if not isinstance(dependency_map, dict):
                        validation_errors.append(
                            {
                                **ecosystem_context,
                                "field": "dependencies",
                                "reason": "dependency entries must be dictionaries keyed by dependency name",
                            }
                        )
                        continue

                    for dependency_name, constraint in dependency_map.items():
                        dependency_context = {
                            **ecosystem_context,
                            "dependency_name": dependency_name,
                        }
                        if not isinstance(dependency_name, str) or not dependency_name:
                            validation_errors.append(
                                {
                                    **dependency_context,
                                    "field": "dependency_name",
                                    "reason": "dependency names must be non-empty strings",
                                }
                            )

                        if constraint is None:
                            validation_errors.append(
                                {
                                    **dependency_context,
                                    "field": "dependency_constraint",
                                    "reason": "dependency constraint cannot be null",
                                }
                            )
                        elif not isinstance(constraint, str):
                            validation_errors.append(
                                {
                                    **dependency_context,
                                    "field": "dependency_constraint",
                                    "reason": "dependency constraint must be a string expression",
                                }
                            )

        if validation_errors:
            raise ResolverError(
                message="Package validation failed.",
                code=ResolverErrorCode.VALIDATION_ERROR,
                details={**validation_scope, "errors": validation_errors},
            )

    def _build_dependency_graph(self, packages: list[dict]):
        """Build a graph of package dependencies, including cross-ecosystem deps."""
        self.dependency_graph.clear()

        for package in packages:
            # Package name is already normalized in resolve_dependencies
            pkg_id = f"{package['name']}@{package.get('ecosystem', 'unknown')}"
            self.dependency_graph.add_node(pkg_id, **package)

            # Add dependencies as edges
            for dep_ecosystem, deps in package.get("dependencies", {}).items():
                for dep_name, dep_constraint in deps.items():
                    dep_id = f"{dep_name}@{dep_ecosystem}"
                    self.dependency_graph.add_edge(pkg_id, dep_id, constraint=dep_constraint)

            # Add cross-ecosystem dependency edges
            for xdep in package.get("cross_ecosystem_deps", []):
                target_eco = xdep.get("target_ecosystem", package.get("ecosystem", "unknown"))
                dep_name = xdep.get("dependency", "")
                if dep_name:
                    dep_id = f"{dep_name}@{target_eco}"
                    self.dependency_graph.add_edge(
                        pkg_id,
                        dep_id,
                        constraint=xdep.get("version_spec", "*"),
                        cross_ecosystem=True,
                    )

    def _is_prerelease(self, ver: str) -> bool:
        """Check if a version is a pre-release (alpha, beta, dev, rc)."""
        try:
            parsed = version.parse(ver)
            return parsed.is_prerelease
        except Exception:
            return bool(re.search(r'(a|alpha|b|beta|rc|dev|pre|preview)[._-]?\d*$', ver, re.IGNORECASE))

    def _cluster_versions(self, versions: list[str]) -> list[str]:
        """Group versions by major.minor, keep latest stable per cluster.

        Keeps at most SOLVER_MAX_CLUSTERS clusters, each with the latest
        stable version.  If a cluster has no stable version, the latest
        pre-release is kept as fallback.  If the list is short (<=10)
        and most versions are same major, return as-is.
        """
        if len(versions) <= SOLVER_MAX_CLUSTERS:
            return versions
        parsed_pairs: list[tuple[str, Any]] = []
        for ver in versions:
            p = parse_version(ver)
            if p:
                parsed_pairs.append((ver, p))
        if not parsed_pairs:
            return versions[:SOLVER_MAX_CLUSTERS]
        parsed_pairs.sort(key=lambda x: x[1], reverse=True)
        clusters: dict[str, list[tuple[str, Any]]] = {}
        for ver, p in parsed_pairs:
            key = f"{p.major}.{p.minor}"
            clusters.setdefault(key, []).append((ver, p))
        sorted_keys = sorted(
            clusters.keys(),
            key=lambda k: [int(x) for x in k.split('.')],
            reverse=True,
        )
        result = []
        for key in sorted_keys[:SOLVER_MAX_CLUSTERS]:
            entries = clusters[key]
            stable = [(v, p) for v, p in entries if not self._is_prerelease(v)]
            if stable:
                result.append(stable[0][0])
            else:
                result.append(entries[0][0])
        if not result:
            return versions[:SOLVER_MAX_CLUSTERS]
        return result

    def _create_version_mapping(self, package_name: str, versions: list[str]):
        """Create integer mapping for versions to use in Z3."""
        # Use parse_version for safer version parsing
        parsed_versions = []
        for ver in versions:
            parsed = parse_version(ver)
            if parsed:
                parsed_versions.append((ver, parsed))

        # Sort by parsed version objects
        sorted_versions = sorted(parsed_versions, key=lambda x: x[1])

        for idx, (ver, _) in enumerate(sorted_versions):
            key = f"{package_name}_{ver}"
            self.version_to_int[key] = idx
            self.int_to_version[key] = ver

    def _create_constraints(self, packages: list[dict], system_info: dict) -> dict:
        """Create constraint system for SAT solver."""
        import z3

        constraints: dict[str, Any] = {
            "package_versions": {},
            "system_requirements": {},
            "conflicts": [],
            "dependencies": [],
        }

        self._version_weights = []
        self._minimization_added = False

        # Variable for each package version
        total_vars = 0
        for package in packages:
            pkg_name = package["name"]  # Already normalized
            versions = package.get("available_versions", [])

            # Cluster versions to reduce solver variables and avoid old versions
            versions = self._cluster_versions(versions)
            package["available_versions"] = versions

            # Create version mapping
            self._create_version_mapping(pkg_name, versions)

            # Create boolean variable for each version
            constraint = package.get("version_constraint", "*")
            if constraint != "*":
                try:
                    from packaging.specifiers import SpecifierSet

                    SpecifierSet(constraint)
                except Exception:
                    constraint = "*"
            version_vars = []
            for v in versions:
                if constraint != "*" and not is_compatible_version(v, constraint):
                    continue

                var_name = f"{pkg_name}_{v}"
                var = z3.Bool(var_name)
                version_vars.append(var)
                self.version_vars[var_name] = var

                # Weight for minimization: higher version index = lower weight (preferred)
                sorted_idx = self.version_to_int.get(var_name, 0)
                total_versions = len(versions)
                # Newest version gets weight 0, oldest gets weight total_versions
                weight = total_versions - sorted_idx
                # Pre-release penalty: strongly prefer stable versions
                if self._is_prerelease(v):
                    weight += SOLVER_PRERELEASE_PENALTY
                self._version_weights.append(weight * var)

                # Add system requirement constraints
                if "system_requirements" in package:
                    self._add_system_constraints(
                        var, package["system_requirements"], system_info, constraints
                    )

            constraints["package_versions"][pkg_name] = version_vars
            total_vars += len(version_vars)

            if not version_vars:
                continue

            # Max-vars guard to prevent memory blowup on huge graphs
            if total_vars > SOLVER_MAX_VARS:
                logger.warning(
                    f"Solver variable limit ({SOLVER_MAX_VARS}) reached at {total_vars} vars, "
                    f"limiting further package versions",
                    extra={
                        "event": "solver_max_vars_reached",
                        "total_vars": total_vars,
                    },
                )
                break

            # Exactly one version must be selected
            self.solver.add(z3.Or(version_vars))
            self.solver.add(z3.AtMost(*version_vars, 1))

        # Add dependency constraints
        self._add_dependency_constraints(constraints)

        # Add known conflict constraints
        self._add_conflict_constraints(packages, constraints)

        return constraints

    def _add_system_constraints(
        self,
        version_var: z3.BoolRef,
        requirements: dict,
        system_info: dict,
        constraints: dict,
    ):
        """Add constraints based on system requirements."""
        import z3

        for req_type, req_value in requirements.items():
            if req_type == "cuda" and "gpu" in system_info:
                if system_info["gpu"]["cuda"]:
                    system_cuda = parse_version(system_info["gpu"]["cuda"])
                    required_cuda = parse_version(req_value.get("min_version", "0.0"))

                    if (
                        system_cuda
                        and required_cuda
                        and (
                            compare_versions(
                                system_info["gpu"]["cuda"],
                                req_value.get("min_version", "0.0"),
                            )
                            < 0
                        )
                    ):
                        # This version cannot be selected
                        self.solver.add(z3.Not(version_var))

            elif req_type == "python" and "runtime_versions" in system_info:
                system_python_str = system_info["runtime_versions"]["python"]["version"]
                if "min_version" in req_value and (
                    compare_versions(system_python_str, req_value["min_version"]) < 0
                ):
                    self.solver.add(z3.Not(version_var))

    def _add_dependency_constraints(self, constraints: dict):
        """Add constraints for package dependencies."""
        import z3

        for node in self.dependency_graph.nodes():
            node_data = self.dependency_graph.nodes[node]
            pkg_name = node_data.get("name")
            if pkg_name is None:
                continue
            node_data.get("ecosystem", "unknown")

            for successor in self.dependency_graph.successors(node):
                edge_data = self.dependency_graph.get_edge_data(node, successor)
                constraint_str = edge_data.get("constraint", "")

                if not constraint_str:
                    continue

                # Skip deps with unparseable constraints (e.g. path-based, git urls)
                try:
                    from packaging.specifiers import SpecifierSet

                    SpecifierSet(constraint_str)
                except Exception:
                    continue

                # Get successor package info
                successor_data = self.dependency_graph.nodes.get(successor, {})
                dep_name = successor_data.get("name", successor.split("@")[0])

                # For each version of the dependent package
                if pkg_name in constraints["package_versions"]:
                    for pkg_var in constraints["package_versions"][pkg_name]:
                        str(pkg_var).split("_")[-1]
                        pkg_var_ref = self.version_vars.get(str(pkg_var))

                        if pkg_var_ref is not None and dep_name in constraints["package_versions"]:
                            # Create constraint: if this package version is selected,
                            # then dependency must satisfy version constraint
                            valid_dep_vars = []

                            for dep_var in constraints["package_versions"][dep_name]:
                                dep_version = str(dep_var).split("_")[-1]
                                dep_var_ref = self.version_vars.get(str(dep_var))

                                # Use is_compatible_version for checking
                                if dep_var_ref is not None and is_compatible_version(
                                    dep_version, constraint_str
                                ):
                                    valid_dep_vars.append(dep_var_ref)

                            if valid_dep_vars:
                                # If package is selected, one of the valid dependency versions must be selected
                                self.solver.add(z3.Implies(pkg_var_ref, z3.Or(valid_dep_vars)))
                            else:
                                # No valid dependency version satisfies the constraint
                                # → this package version cannot be selected
                                self.solver.add(z3.Not(pkg_var_ref))

    def _add_conflict_constraints(self, packages: list[dict], constraints: dict):
        """Add known conflict constraints."""
        import z3

        # Example: CUDA 11.x packages conflict with CUDA 12.x packages
        cuda_11_packages = []
        cuda_12_packages = []

        for package in packages:
            if "system_requirements" in package:
                cuda_req = package.get("system_requirements", {}).get("cuda", {})
                if "min_version" in cuda_req:
                    cuda_ver = cuda_req["min_version"]
                    if cuda_ver.startswith("11."):
                        cuda_11_packages.append(package["name"])
                    elif cuda_ver.startswith("12."):
                        cuda_12_packages.append(package["name"])

        # Add conflict constraints
        for pkg11 in cuda_11_packages:
            for pkg12 in cuda_12_packages:
                constraints["conflicts"].append((pkg11, pkg12))

                # Add to solver: both packages cannot be selected simultaneously
                if (
                    pkg11 in constraints["package_versions"]
                    and pkg12 in constraints["package_versions"]
                ):
                    for var11 in constraints["package_versions"][pkg11]:
                        for var12 in constraints["package_versions"][pkg12]:
                            var11_ref = self.version_vars.get(str(var11))
                            var12_ref = self.version_vars.get(str(var12))
                            if var11_ref is not None and var12_ref is not None:
                                self.solver.add(z3.Not(z3.And(var11_ref, var12_ref)))

    def _solve_constraints(self, constraints: dict, prefer_compatibility: bool) -> dict:
        """Solve the constraint system."""
        import z3

        if self._use_optimization and self._version_weights and not self._minimization_added:
            self.solver.minimize(z3.Sum(self._version_weights))
            self._minimization_added = True

        result = self.solver.check()

        if result == z3.sat:
            model = self.solver.model()
            solution: dict[str, Any] = {
                "status": "satisfiable",
                "packages": {},
                "warnings": [],
            }

            # Extract selected versions
            for pkg_name, version_vars in constraints["package_versions"].items():
                for var in version_vars:
                    var_ref = self.version_vars.get(str(var))
                    if var_ref is not None and z3.is_true(model.eval(var_ref)):
                        version_str = str(var).split("_", 1)[-1]
                        solution["packages"][pkg_name] = {
                            "version": version_str,
                            "ecosystem": self._get_ecosystem(pkg_name),
                        }
                        break

            return solution
        if result == z3.unknown:
            logger.warning("Z3 solver returned unknown (likely timeout or incomplete)")
            return {
                "status": "timeout",
                "conflicts": [],
                "message": "Solver timed out or could not determine satisfiability",
            }
        return {"status": "unsatisfiable", "conflicts": self._analyze_conflicts()}

    def _resolve_with_alternatives(self, packages: list[dict], system_info: dict) -> dict:
        """Try to resolve conflicts by finding alternative packages or versions."""
        alternatives: dict[str, Any] = {
            "status": "partial",
            "packages": {},
            "alternatives": [],
            "warnings": [],
        }

        # Try to find compatible versions for each package independently
        for package in packages:
            compatible_versions = self._find_compatible_versions(package, system_info)
            if compatible_versions:
                alternatives["packages"][package["name"]] = {
                    "version": compatible_versions[0],
                    "alternatives": compatible_versions[1:],
                    "ecosystem": package.get("ecosystem", "unknown"),
                }
            else:
                alternatives["warnings"].append(
                    f"No compatible version found for {package['name']}"
                )

        return alternatives

    def _find_compatible_versions(self, package: dict, system_info: dict) -> list[str]:
        """Find versions compatible with system requirements."""
        compatible = []

        # Apply version_constraint from manifest (e.g. >=3.11,<3.13)
        version_constraint = package.get("version_constraint", "*")

        # Check package-level system requirements
        sys_reqs = package.get("system_requirements", {})
        python_req = sys_reqs.get("python", {})
        min_python = python_req.get("min_version", "")

        cuda_req = sys_reqs.get("cuda", {})
        min_cuda = cuda_req.get("min_version", "")

        # Support both "versions" (list of dicts) and "available_versions" (list of strings)
        raw_versions = package.get("versions") or package.get("available_versions", [])
        for version_info in raw_versions:
            if isinstance(version_info, dict):
                version_str = version_info.get("version", "")
                version_info.get("system_requirements", {})
                if not self._check_version_compatibility(version_info, system_info):
                    continue
            else:
                version_str = str(version_info)

            # Apply version_constraint from manifest (e.g. python >=3.11,<3.13)
            if version_constraint != "*" and not is_compatible_version(
                version_str, version_constraint
            ):
                continue

                # Apply package-level system requirements
                sys_python = (
                    system_info.get("runtime_versions", {}).get("python", {}).get("version", "")
                )
                if sys_python and compare_versions(sys_python, min_python) < 0:
                    continue
            if min_cuda:
                sys_cuda = system_info.get("gpu", {}).get("cuda", "")
                if sys_cuda and compare_versions(sys_cuda, min_cuda) < 0:
                    continue

            # Skip pre-release versions in fallback path
            if self._is_prerelease(version_str):
                continue

            compatible.append(version_str)

        # Sort using compare_versions
        return sorted(
            compatible,
            key=lambda v: parse_version(v) or version.parse("0.0"),
            reverse=True,
        )

    def _check_version_compatibility(self, version_info: dict, system_info: dict) -> bool:
        """Check if a specific version is compatible with system."""
        requirements = version_info.get("system_requirements", {})

        # Check CUDA compatibility
        if "cuda" in requirements and "gpu" in system_info:
            if not system_info["gpu"]["cuda"]:
                return False

            min_cuda = requirements["cuda"].get("min_version", "0.0")
            if compare_versions(system_info["gpu"]["cuda"], min_cuda) < 0:
                return False

        # Check Python compatibility
        if "python" in requirements and "runtime_versions" in system_info:
            system_python = system_info["runtime_versions"]["python"]["version"]
            min_python = requirements["python"].get("min_version", "0.0")

            if compare_versions(system_python, min_python) < 0:
                return False

        return True

    def _format_solution(self, solution: dict) -> dict:
        """Format the solution for output."""
        formatted = {
            "resolved_packages": solution["packages"],
            "dependency_tree": self._build_dependency_tree(solution["packages"]),
            "warnings": solution.get("warnings", []),
            "installation_order": self._calculate_installation_order(solution["packages"]),
            "status": solution.get("status", "satisfiable"),
        }

        return formatted

    def _build_dependency_tree(self, packages: dict) -> dict:
        """Build a tree structure of dependencies."""
        tree = {}

        for pkg_name, pkg_info in packages.items():
            deps = self._get_package_dependencies(pkg_name, pkg_info["version"])
            tree[pkg_name] = {"version": pkg_info["version"], "dependencies": deps}

        return tree

    def _calculate_installation_order(self, packages: dict) -> list[str]:
        """Calculate the order in which packages should be installed."""
        # Topological sort of dependency graph
        subgraph = self.dependency_graph.subgraph(
            [f"{name}@{info['ecosystem']}" for name, info in packages.items()]
        )

        try:
            return list(nx.topological_sort(subgraph))
        except nx.NetworkXUnfeasible:
            # Graph has cycles, return arbitrary order
            try:
                cycles = list(nx.simple_cycles(subgraph))
                cycle_strs = [" -> ".join(c) for c in cycles[:5]]
                logger.warning(
                    "Circular dependencies detected in installation order",
                    extra={
                        "event": "circular_dependency_detected",
                        "cycles": cycle_strs,
                        "package_count": len(packages),
                    },
                )
            except Exception:
                pass
            return list(packages.keys())

    def _get_ecosystem(self, package_name: str) -> str:
        """Get ecosystem for a package from the graph."""
        for node in self.dependency_graph.nodes():
            if node.startswith(f"{package_name}@"):
                return node.split("@")[1]
        return "unknown"

    def _get_package_dependencies(self, package_name: str, version_str: str) -> dict:
        """Get dependencies for a specific package version."""
        dependencies: dict[str, Any] = {}

        # Find the node in the graph
        pkg_node = None
        for node in self.dependency_graph.nodes():
            node_data = self.dependency_graph.nodes[node]
            if node_data.get("name") == package_name:
                pkg_node = node
                break

        if not pkg_node:
            return dependencies

        # Get version-specific dependencies
        node_data = self.dependency_graph.nodes[pkg_node]

        # Check if we have version-specific dependency information
        if "versions" in node_data:
            for version_info in node_data["versions"]:
                if version_info.get("version") == version_str:
                    version_deps = version_info.get("dependencies", {})
                    for ecosystem, deps in version_deps.items():
                        dependencies[ecosystem] = deps
                    return dependencies

        # Fall back to general dependencies from the graph edges
        for successor in self.dependency_graph.successors(pkg_node):
            edge_data = self.dependency_graph.get_edge_data(pkg_node, successor)
            successor_data = self.dependency_graph.nodes.get(successor, {})

            dep_name = successor_data.get("name", successor.split("@")[0])
            dep_ecosystem = successor_data.get("ecosystem", "unknown")
            constraint = edge_data.get("constraint", "*")

            if dep_ecosystem not in dependencies:
                dependencies[dep_ecosystem] = {}

            dependencies[dep_ecosystem][dep_name] = constraint

        return dependencies

    def _analyze_conflicts(self) -> list[dict]:
        """Analyze why constraints are unsatisfiable using unsat core."""
        import z3

        conflicts = []

        # Create tracked assertions
        tracked_assertions = []
        assertion_info = {}

        # Re-add all assertions with tracking
        temp_solver = z3.Solver()
        temp_solver.set(unsat_core=True)
        if not self._use_optimization:
            self.solver.set(unsat_core=True)

        idx = 0
        for assertion in self.solver.assertions():
            track_var = z3.Bool(f"track_{idx}")
            temp_solver.add(z3.Implies(track_var, assertion))
            tracked_assertions.append(track_var)

            # Store information about what this assertion represents
            assertion_str = str(assertion)
            if "Implies" in assertion_str:
                # This is likely a dependency constraint
                assertion_info[track_var] = {
                    "type": "dependency",
                    "constraint": assertion_str,
                }
            elif "Not(And(" in assertion_str:
                # This is likely a conflict constraint
                assertion_info[track_var] = {
                    "type": "conflict",
                    "constraint": assertion_str,
                }
            else:
                assertion_info[track_var] = {
                    "type": "other",
                    "constraint": assertion_str,
                }

            idx += 1

        # Check with all tracking variables enabled
        result = temp_solver.check(tracked_assertions)

        if result == z3.unsat:
            core = temp_solver.unsat_core()

            # Analyze the unsat core
            for track_var in core:
                if track_var in assertion_info:
                    info = assertion_info[track_var]

                    # Parse the constraint to extract package names
                    constraint_str = info["constraint"]
                    packages_involved = []

                    # Extract package names from the constraint string
                    package_pattern = r"(\w+)_(\d+\.\d+(?:\.\d+)?)"
                    matches = re.findall(package_pattern, constraint_str)

                    for match in matches:
                        packages_involved.append({"name": match[0], "version": match[1]})

                    conflicts.append(
                        {
                            "type": info["type"],
                            "packages": packages_involved,
                            "description": self._format_conflict_description(
                                info, packages_involved
                            ),
                        }
                    )

        return conflicts

    def _format_conflict_description(self, info: dict, packages: list[dict]) -> str:
        """Format a human-readable description of the conflict."""
        if info["type"] == "dependency":
            if len(packages) >= 2:
                return f"{packages[0]['name']} {packages[0]['version']} requires incompatible version of {packages[1]['name']}"
        elif info["type"] == "conflict":
            if len(packages) >= 2:
                return f"{packages[0]['name']} {packages[0]['version']} conflicts with {packages[1]['name']} {packages[1]['version']}"

        return f"Constraint conflict: {info['constraint']}"
