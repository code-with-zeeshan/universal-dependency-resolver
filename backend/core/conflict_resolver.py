"""Module docstring."""

# conflict_resolver.py
from __future__ import annotations

import asyncio
import concurrent.futures
import copy
import hashlib
import logging
import platform
import re
import threading
import uuid
from typing import TYPE_CHECKING, Any

import networkx as nx
from packaging import version

from backend.tracing_config import get_tracer

from ._json import dumps

if TYPE_CHECKING:
    import z3

from backend.settings import (
    CACHE_TTL,
    SOLVER_MAX_CLUSTERS,
    SOLVER_MAX_CLUSTERS_MAX,
    SOLVER_MAX_CLUSTERS_MIN,
    SOLVER_MAX_VARIABLES,
    SOLVER_OPTIMIZATION_THRESHOLD,
    SOLVER_PRERELEASE_PENALTY,
    SOLVER_REJECT_DEPRECATED,
)
from backend.settings import (
    USE_Z3_OPTIMIZE as USE_OPTIMIZATION,
)
from backend.utils.errors import (
    ResolverError,
    ResolverErrorCode,
    ensure_details_context,
    make_internal_error,
)

from .cache import cached
from .constraint_normalizer import is_prerelease_version, normalize_version
from .utils import (
    compare_versions,
    is_compatible_version,
    normalize_package_name,
    parse_version,
)

logger = logging.getLogger(__name__)


def _get_gpu_version(system_info: dict, gpu_type: str) -> str:
    """Extract GPU version string from system_info for a given GPU type.

    Handles both plain-string (CLI override) and dict (auto-detection) formats.
    """
    gpu = system_info.get("gpu", {})
    if not isinstance(gpu, dict):
        return ""
    val = gpu.get(gpu_type)
    if val is None:
        return ""
    if isinstance(val, dict):
        return val.get("version", "")
    if isinstance(val, str):
        return val
    return ""


# Data-driven conflict rules: each rule specifies incompatible version ranges
# across packages or ecosystems.  Used by _add_conflict_constraints().
CONFLICT_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "cuda 11.x vs cuda 12.x",
        "type": "cuda",
        "constraint_a": {
            "field": "system_requirements.cuda.min_version",
            "op": ">=",
            "value": "11.0",
        },
        "constraint_b": {
            "field": "system_requirements.cuda.min_version",
            "op": ">=",
            "value": "12.0",
        },
        "mutually_exclusive_with": {
            "field": "system_requirements.cuda.min_version",
            "op": ">=",
            "value": "12.0",
        },
    },
    {
        "id": "rocm 5.x vs rocm 6.x",
        "type": "rocm",
        "constraint_a": {
            "field": "system_requirements.rocm.min_version",
            "op": ">=",
            "value": "5.0.0",
        },
        "constraint_b": {
            "field": "system_requirements.rocm.min_version",
            "op": ">=",
            "value": "6.0.0",
        },
        "mutually_exclusive_with": {
            "field": "system_requirements.rocm.min_version",
            "op": ">=",
            "value": "6.0.0",
        },
    },
    {
        "id": "tensorflow vs numpy upper bound",
        "type": "dependency",
        "description": "tensorflow 2.15+ requires numpy <1.28",
        "packages": ["tensorflow"],
        "constraint": {"numpy": "<1.28"},
    },
)


_APK_RE = re.compile(r"^(\d[\w.]*)-r\d+$")


def _is_apk_version(v: str) -> bool:
    return bool(_APK_RE.match(v))


def _normalize_npm_constraint(constraint_str: str, dep_eco: str) -> str | None:
    """Normalize an npm-style constraint to PEP 440 for Z3's SpecifierSet.

    Handles ``^``, ``~``, ``~>``, x-ranges, and compound constraints.
    Falls back to ``None`` if no valid normalisation is possible.
    """
    from packaging.specifiers import InvalidSpecifier, SpecifierSet

    def _try_spec(norm: str) -> bool:
        if norm == "*":
            return True
        try:
            SpecifierSet(norm)
            return True
        except InvalidSpecifier:
            try:
                SpecifierSet(f"=={norm}")
                return True
            except InvalidSpecifier:
                return False

    def _normalize_part(part: str) -> str | None:
        part = part.strip()
        if not part:
            return None

        # Try direct VersSpec first
        from .vers import VersSpec

        parsed = str(VersSpec.parse(part, dep_eco))
        if _try_spec(parsed):
            return parsed
        # Handle ^X.Y.Z-pre — strip pre-release suffix
        c_match = re.match(r"^\^(\d+(?:\.\d+)*)", part)
        if c_match:
            base = c_match.group(1)
            parts = base.split(".")
            major = int(parts[0])
            p_low = _cluster_versions_static.__globals__.get("_to_semver", lambda v: v)(base)
            if not p_low:
                p_low = base
            built = f">={p_low},<{major + 1}.0.0"
            if _try_spec(built):
                return built
        # Handle ~X.Y.Z-pre — strip pre-release suffix
        t_match = re.match(r"^~(\d+(?:\.\d+)*)", part)
        if t_match:
            base = t_match.group(1)
            parts = base.split(".")
            if len(parts) >= 2:
                low = f"{parts[0]}.{parts[1]}.0" if parts[1][0].isdigit() else f"{parts[0]}.0.0"
                minor = int(parts[1])
                built = f">={low},<{parts[0]}.{minor + 1}.0"
            else:
                major = int(parts[0])
                built = f">={parts[0]}.0.0,<{major + 1}.0.0"
            if _try_spec(built):
                return built
        # Handle ~> (RubyGems pessimistic)
        rg_match = re.match(r"^~>\s*(\d+(?:\.\d+)*)", part)
        if rg_match:
            base = rg_match.group(1)
            parts = base.split(".")
            if len(parts) >= 2:
                low = f"{parts[0]}.{parts[1]}.0"
                major = int(parts[0])
                built = f">={low},<{major + 1}.0.0"
            else:
                major = int(parts[0])
                built = f">={parts[0]}.0.0,<{major + 1}.0.0"
            if _try_spec(built):
                return built
        return None

    parts = [p.strip() for p in constraint_str.split(",")]
    normalized_parts = []
    for part in parts:
        result = _normalize_part(part)
        if result is not None:
            normalized_parts.append(result)
    if normalized_parts:
        rejoined = ",".join(normalized_parts)
        if _try_spec(rejoined):
            return rejoined
        # If compound fails, try each individually
        valid_specs = [p for p in normalized_parts if _try_spec(p)]
        if valid_specs:
            return ",".join(valid_specs)
    return None


def _cluster_versions_static(versions: list[str], max_clusters: int = 100) -> list[str]:
    """Group versions by major.minor, keep latest stable per cluster.

    Standalone version of ConflictResolver._cluster_versions for use
    by PubGrub solver and other non-Z3 consumers.
    """
    if len(versions) <= max_clusters:
        return versions
    parsed_pairs: list[tuple[str, Any]] = []
    for ver in versions:
        p = parse_version(ver)
        if p:
            parsed_pairs.append((ver, p))
    if not parsed_pairs:
        return versions[:max_clusters]
    parsed_pairs.sort(key=lambda x: x[1], reverse=True)
    clusters: dict[str, list[tuple[str, Any]]] = {}
    for ver, p in parsed_pairs:
        key = f"{p.major}.{p.minor}"
        clusters.setdefault(key, []).append((ver, p))
    sorted_keys = sorted(
        clusters.keys(),
        key=lambda k: [int(x) for x in k.split(".")],
        reverse=True,
    )
    result = []
    for key in sorted_keys[:max_clusters]:
        entries = clusters[key]
        stable = [(v, p) for v, p in entries if not p.is_prerelease]
        if stable:
            result.append(stable[0][0])
        else:
            result.append(entries[0][0])
    if not result:
        return versions[:max_clusters]
    return result


class ConflictResolver:
    """Resolves dependency conflicts using constraint satisfaction and graph algorithms."""

    def __init__(self, use_optimization: bool | None = None):
        """Initialize the conflict resolver with Z3 solver and dependency graph.

        Args:
            use_optimization: If True, use z3.Optimize() with minimize() objectives
                to prefer newer versions. If None, falls back to USE_Z3_OPTIMIZE env var.

        """
        try:
            import z3
        except ImportError as _exc:
            raise ImportError(
                "z3-solver is required for ConflictResolver. "
                "Install it with: pip install 'ud-resolver[z3]'"
            ) from _exc

        self.dependency_graph = nx.DiGraph()
        if use_optimization is None:
            use_optimization = USE_OPTIMIZATION
        self._use_optimization = use_optimization
        self._solver = z3.Optimize() if use_optimization else z3.Solver()
        self.version_vars: dict[str, Any] = {}
        self.version_to_int: dict[str, int] = {}
        self.int_to_version: dict[int, str] = {}
        self._version_weights: list[Any] = []
        self._minimization_added = False
        self.offline_mode = False
        self._batch_active = False
        self._name_map: dict[str, str] = {}
        self._node_by_name: dict[str, str] = {}
        self._var_to_version: dict[str, str] = {}
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._resolve_lock = threading.Lock()

    def close(self) -> None:
        """Shut down the thread pool executor, releasing its worker threads."""
        with self._resolve_lock:
            if self._executor is not None:
                self._executor.shutdown(wait=True)
                self._executor = None

    @property
    def solver(self):
        """Get the Z3 solver instance (backward-compatible access)."""
        return self._solver

    @staticmethod
    def compute_resolution_hash(
        package_name: str,
        ecosystem: str,
        version_constraint: str,
        dependencies: dict,
        system_info: dict | None = None,
    ) -> str:
        """Compute a hash of the package's resolution context for incremental resolution.

        The hash captures everything that determines a package's resolution:
        its name, ecosystem, version constraint, dependency names+constraints,
        and relevant system info (CUDA, Python version).
        When the hash matches a stored value in the lock file, re-resolution
        can be skipped and the locked version reused.
        """
        ctx: dict[str, Any] = {
            "name": package_name,
            "ecosystem": ecosystem,
            "constraint": version_constraint,
            "deps": {k: dict(v) for k, v in sorted(dependencies.items())}
            if isinstance(dependencies, dict)
            else {},
        }
        if system_info:
            gpu = system_info.get("gpu", {})
            if isinstance(gpu, dict):
                for gpu_type in ("cuda", "rocm", "intel_gpu", "metal"):
                    val = gpu.get(gpu_type)
                    if val is None:
                        continue
                    if isinstance(val, dict):
                        ver = val.get("version", "")
                    elif isinstance(val, str):
                        ver = val
                    else:
                        continue
                    if ver:
                        ctx[gpu_type] = ver
            rt = system_info.get("runtime_versions", {})
            py = rt.get("python", {})
            if py:
                ctx["python"] = py.get("version")
        raw = dumps(ctx, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # Additional error handling enhancements
    def resolve_dependencies(
        self,
        packages: list[dict[str, Any]],
        system_info: dict[str, Any] | None = None,
        prefer_compatibility: bool = True,
        solver_timeout: int | None = None,
    ) -> dict[str, Any]:
        """Resolve package dependencies and conflicts."""
        _tracer = get_tracer(__name__)
        with _tracer.start_as_current_span("ConflictResolver.resolve_dependencies") as _span:
            _span.set_attribute("package_count", len(packages))
            _span.set_attribute("solver_timeout_ms", solver_timeout or 0)
            self._resolve_lock.acquire()
            try:
                result = self._resolve_dependencies_impl(
                    packages, system_info, prefer_compatibility, solver_timeout
                )
                _span.set_attribute("result.status", result.get("status", "unknown"))
                _span.set_attribute("resolved_count", len(result.get("resolved_packages", {})))
                return result
            finally:
                self._resolve_lock.release()

    def _resolve_dependencies_impl(
        self,
        packages: list[dict[str, Any]],
        system_info: dict[str, Any] | None = None,
        prefer_compatibility: bool = True,
        solver_timeout: int | None = None,
    ) -> dict[str, Any]:
        """Hold _resolve_lock during dependency resolution."""
        # Reassign (not clear) to give each call fresh state

        self.version_vars = {}
        self.version_to_int = {}
        self.int_to_version = {}
        self._version_weights = []
        self._minimization_added = False
        self._var_to_version = {}

        # Guard: reject if total available versions exceed SOLVER_MAX_VARIABLES
        total_versions = sum(len(pkg.get("available_versions", []) or []) for pkg in packages)
        if total_versions > SOLVER_MAX_VARIABLES:
            logger.warning(
                "Too many versions (%d) — exceeds SOLVER_MAX_VARIABLES (%d)",
                total_versions,
                SOLVER_MAX_VARIABLES,
                extra={
                    "event": "solver_max_variables_exceeded",
                    "total_versions": total_versions,
                    "max_vars": SOLVER_MAX_VARIABLES,
                },
            )
            return {
                "status": "unsatisfiable",
                "error": (
                    f"Too many versions ({total_versions}) — "
                    f"exceeds SOLVER_MAX_VARIABLES ({SOLVER_MAX_VARIABLES})"
                ),
                "resolved_packages": {},
            }

        resolution_context = {
            "package_count": len(packages),
            "solver_timeout_ms": solver_timeout,
        }

        try:
            normalized_packages = self._normalize_packages(packages, resolution_context)
            resolution_context["normalized_package_count"] = len(normalized_packages)

            self._validate_package_inputs(normalized_packages, resolution_context)
            system_info = self._prepare_system_info(system_info, resolution_context)
            self._reset_solver_state(solver_timeout, len(normalized_packages))

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

            # Try SCC-based batch resolution for large graphs with actual cycles
            # (more than 1 SCC, at least one cycle among them, and enough packages
            # to justify the overhead).  Skip for pure DAGs where each package
            # is its own SCC — the monolithic solver handles cross-package
            # constraints correctly there.
            sccs_found = list(nx.strongly_connected_components(self.dependency_graph))
            has_cycles = any(len(scc) > 1 for scc in sccs_found)
            if has_cycles and len(sccs_found) > 1 and len(normalized_packages) > 20:
                scc_result = self._batch_resolve_sccs(
                    normalized_packages, system_info, prefer_compatibility, solver_timeout
                )
                if scc_result is not None:
                    return scc_result

            # Try per-ecosystem isolation (independent ecosystems resolved separately)
            eco_result = self._isolate_by_ecosystem(
                normalized_packages, system_info, prefer_compatibility, solver_timeout
            )
            if eco_result is not None:
                return eco_result

            try:
                constraints = self._create_constraints(normalized_packages, system_info)
            except RuntimeError as e:
                logger.error("Constraint creation failed: %s", e)
                return {
                    "status": "unsatisfiable",
                    "error": str(e),
                    "packages": {},
                    "warnings": [str(e)],
                }
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
            conflicts = solution.get("conflicts", [])
            diag = self._resolve_with_alternatives(normalized_packages, system_info)
            diag_list = list(diag.get("diagnosis", []))
            for c in conflicts:
                desc = c.get("description", "")
                if desc and desc not in diag_list:
                    diag_list.append(desc)
            result: dict[str, Any] = {"status": "unsatisfiable", "resolved_packages": {}}
            if diag_list:
                result["resolution_error"] = "; ".join(diag_list)
            elif conflicts:
                pkg_names: set[str] = set()
                for c in conflicts:
                    for p in c.get("packages", []):
                        pkg_names.add(p.get("name", ""))
                result["resolution_error"] = (
                    f"Unsatisfiable constraints involving: {', '.join(sorted(pkg_names))}"
                )
            else:
                result["resolution_error"] = (
                    "Constraint conflict detected — run with --json for details"
                )
            result["conflicts"] = conflicts
            return result

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

    def _batch_resolve_sccs(
        self,
        normalized_packages: list[dict],
        system_info: dict,
        prefer_compatibility: bool,
        solver_timeout: int | None,
    ) -> dict | None:
        """Resolve packages by partitioning the dependency graph into SCCs.

        Each SCC is resolved independently with its own Z3 solver instance.
        Already-resolved dependency versions are pinned in downstream SCCs.
        Returns None if the graph has only one SCC (fall back to monolithic).
        """
        try:
            sccs = list(nx.strongly_connected_components(self.dependency_graph))
            if len(sccs) <= 1:
                return None

            # Build condensation DAG for topological ordering
            cond = nx.condensation(self.dependency_graph)
            topo_order = list(nx.topological_sort(cond))

            # Collect packages per SCC from condensation node members
            scc_packages: dict[int, list[dict]] = {}
            for scc_node in cond.nodes():
                scc_id = scc_node
                members = cond.nodes[scc_node].get("members", set())
                pkgs = []
                for node in members:
                    pkg_data = dict(self.dependency_graph.nodes[node])
                    if pkg_data:
                        pkgs.append(pkg_data)
                scc_packages[scc_id] = pkgs

            resolved_versions: dict[str, str] = {}
            all_results: dict[str, dict] = {}
            scc_failures: int = 0
            total_sccs: int = len(topo_order)

            # Build map from package name to SCC id for cross-SCC constraint propagation
            package_to_scc: dict[str, int] = {}
            for sid, spkgs in scc_packages.items():
                for sp in spkgs:
                    sp_name = sp.get("name", "")
                    if sp_name:
                        package_to_scc[sp_name] = sid

            # Collect downstream constraints: for each package, gather all dependency
            # constraints from predecessor SCCs (nodes that depend on this package).
            # These are constraints that will be enforced later but must be satisfied
            # by the version chosen now in this leaf SCC.
            downstream_constraints: dict[str, list[str]] = {}
            for sid, spkgs in scc_packages.items():
                for sp in spkgs:
                    pkg_name = sp.get("name", "")
                    pkg_eco = sp.get("ecosystem", "unknown")
                    pkg_node = f"{pkg_name}@{pkg_eco}"
                    for pred_node in self.dependency_graph.predecessors(pkg_node):
                        pred_name = pred_node.rsplit("@", 1)[0]
                        pred_scc = package_to_scc.get(pred_name, sid)
                        if pred_scc != sid:
                            edge_data = self.dependency_graph.get_edge_data(pred_node, pkg_node)
                            if edge_data:
                                constraint = edge_data.get("constraint", "")
                                if constraint:
                                    downstream_constraints.setdefault(pkg_name, []).append(
                                        constraint
                                    )

            logger.info(
                "Batch resolving %d SCCs from dependency graph",
                len(topo_order),
                extra={"event": "batch_scc_resolution_start", "scc_count": len(topo_order)},
            )

            for scc_id in topo_order:
                pkgs = scc_packages.get(scc_id, [])
                if not pkgs:
                    continue

                # Pin already-resolved deps in this SCC
                scc_pkg_names = {p["name"] for p in pkgs}

                # Merge downstream constraints from dependents in other SCCs
                for pkg in pkgs:
                    pkg_name = pkg.get("name", "")
                    if pkg_name in downstream_constraints:
                        for dep_constraint in downstream_constraints[pkg_name]:
                            existing = pkg.get("version_constraint", "*")
                            if existing and existing != "*":
                                pkg["version_constraint"] = f"{existing},{dep_constraint}"
                            else:
                                pkg["version_constraint"] = dep_constraint

                for pkg in pkgs:
                    pinned_deps = {}
                    for eco, deps in pkg.get("dependencies", {}).items():
                        pinned_deps[eco] = {}
                        for dep_name, constraint in deps.items():
                            if dep_name in resolved_versions and dep_name not in scc_pkg_names:
                                pinned_deps[eco][dep_name] = f"=={resolved_versions[dep_name]}"
                            else:
                                pinned_deps[eco][dep_name] = constraint
                    if pinned_deps:
                        pkg["dependencies"] = pinned_deps

                # Resolve this SCC with a fresh solver instance
                self._batch_active = True
                self.version_vars.clear()
                self.version_to_int.clear()
                self.int_to_version.clear()
                self._reset_solver_state(solver_timeout, len(pkgs))

                try:
                    constraints = self._create_constraints(pkgs, system_info)
                    solution = self._solve_constraints(constraints, prefer_compatibility)

                    if solution["status"] == "satisfiable":
                        formatted = self._format_solution(solution)
                        pkgs_dict = formatted.get("resolved_packages", {})
                        for pname, pinfo in pkgs_dict.items():
                            ver = pinfo.get("version", "")
                            if ver:
                                resolved_versions[pname] = ver
                            all_results[pname] = pinfo
                    else:
                        logger.warning(
                            "SCC %d unsatisfiable, trying alternatives",
                            scc_id,
                            extra={"event": "scc_unsat", "scc_id": scc_id},
                        )
                        scc_failures += 1
                except Exception as exc:
                    scc_failures += 1
                    logger.warning(
                        "SCC %d resolution failed: %s",
                        scc_id,
                        exc,
                        extra={"event": "scc_failed", "scc_id": scc_id},
                    )

            self._batch_active = False

            if not all_results:
                return None

            status = "partial" if scc_failures > 0 else "satisfiable"
            warnings_list = (
                [f"{scc_failures}/{total_sccs} SCCs failed — partial resolution"]
                if scc_failures > 0
                else []
            )

            return {
                "status": status,
                "resolved_packages": all_results,
                "dependency_tree": self._build_dependency_tree(all_results),
                "warnings": warnings_list,
                "installation_order": list(all_results.keys()),
                "batch_resolved": True,
                "scc_count": total_sccs,
            }

        except Exception as exc:
            logger.warning("Batch SCC resolution failed: %s", exc)
            self._batch_active = False
            return None

    def _isolate_by_ecosystem(
        self,
        normalized_packages: list[dict],
        system_info: dict,
        prefer_compatibility: bool,
        solver_timeout: int | None,
    ) -> dict | None:
        """Resolve packages by isolating per-ecosystem groups.

        Groups packages by ecosystem, builds an ecosystem-level dependency
        graph, and resolves each ecosystem with its own solver instance.
        Cross-ecosystem dependencies are pinned from upstream ecosystems.

        Returns None if only one ecosystem is present or if cross-ecosystem
        cycles prevent isolation (falls back to combined resolution).
        """
        eco_groups: dict[str, list[dict]] = {}
        for pkg in normalized_packages:
            eco = pkg.get("ecosystem", "unknown")
            eco_groups.setdefault(eco, []).append(pkg)

        if len(eco_groups) <= 1:
            return None

        eco_graph = nx.DiGraph()
        for eco in eco_groups:
            eco_graph.add_node(eco)
        for pkg in normalized_packages:
            pkg_eco = pkg.get("ecosystem", "unknown")
            for dep_eco, deps in pkg.get("dependencies", {}).items():
                if dep_eco != pkg_eco and dep_eco in eco_groups and deps:
                    eco_graph.add_edge(dep_eco, pkg_eco)

        try:
            topo_eco_order = list(nx.topological_sort(eco_graph))
        except nx.NetworkXUnfeasible:
            logger.info(
                "Cross-ecosystem cycles detected — cannot isolate per ecosystem",
                extra={"event": "eco_isolation_cycle_detected"},
            )
            return None

        # Collect downstream constraints: packages in future ecosystems
        # that constrain packages in earlier (upstream) ecosystems.
        # E.g., mypkg@pypi depends on dep-npm@npm with >=2.0.0 —
        # this constraint must be applied when resolving npm first.
        downstream_constraints: dict[str, list[tuple[str, str]]] = {}
        for pkg in normalized_packages:
            pkg_eco = pkg.get("ecosystem", "unknown")
            for dep_eco, deps in pkg.get("dependencies", {}).items():
                if dep_eco != pkg_eco and dep_eco in eco_groups:
                    for dep_name, constraint in deps.items():
                        downstream_constraints.setdefault(dep_name, [])
                        downstream_constraints[dep_name].append((pkg_eco, constraint))

        resolved_versions: dict[str, str] = {}
        all_results: dict[str, dict] = {}
        all_trees: dict[str, dict] = {}

        for idx, eco in enumerate(topo_eco_order):
            pkgs = copy.deepcopy(eco_groups[eco])
            eco_pkg_names = {p["name"] for p in pkgs}

            # Propagate downstream constraints from future ecosystems
            for pkg in pkgs:
                pkg_name = pkg.get("name", "")
                if pkg_name in downstream_constraints:
                    for source_eco, constraint in downstream_constraints[pkg_name]:
                        source_idx = (
                            topo_eco_order.index(source_eco) if source_eco in topo_eco_order else -1
                        )
                        if source_idx > idx:
                            existing = pkg.get("version_constraint", "*")
                            if existing and existing != "*":
                                pkg["version_constraint"] = f"{existing},{constraint}"
                            else:
                                pkg["version_constraint"] = constraint

            for pkg in pkgs:
                for dep_eco, deps in list(pkg.get("dependencies", {}).items()):
                    if dep_eco == eco:
                        continue
                    for dep_name in list(deps.keys()):
                        if dep_name in resolved_versions and dep_name not in eco_pkg_names:
                            deps[dep_name] = f"=={resolved_versions[dep_name]}"

            self._batch_active = True
            self.version_vars.clear()
            self.version_to_int.clear()
            self.int_to_version.clear()
            self._reset_solver_state(solver_timeout, len(pkgs))

            try:
                constraints = self._create_constraints(pkgs, system_info)
                solution = self._solve_constraints(constraints, prefer_compatibility)

                if solution["status"] == "satisfiable":
                    formatted = self._format_solution(solution)
                    for pname, pinfo in formatted.get("resolved_packages", {}).items():
                        ver = pinfo.get("version", "")
                        if ver:
                            resolved_versions[pname] = ver
                        all_results[pname] = pinfo
                    # Collect per-ecosystem dependency tree (each eco resolved with its own graph)
                    eco_tree = formatted.get("dependency_tree", {})
                    for pname, pdep in eco_tree.items():
                        all_trees[pname] = pdep
                else:
                    logger.info(
                        "Ecosystem %s unsatisfiable — falling back to combined resolution",
                        eco,
                        extra={"event": "eco_isolation_unsat", "ecosystem": eco},
                    )
                    self._batch_active = False
                    return None
            except Exception as exc:
                logger.warning(
                    "Ecosystem %s resolution failed: %s",
                    eco,
                    exc,
                    extra={"event": "eco_isolation_failed", "ecosystem": eco},
                )
                self._batch_active = False
                return None

        self._batch_active = False

        return {
            "status": "satisfiable",
            "resolved_packages": all_results,
            "dependency_tree": all_trees,
            "warnings": [],
            "installation_order": list(all_results.keys()),
            "eco_isolation": True,
            "eco_count": len(topo_eco_order),
        }

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
        system_hash = hashlib.sha256(dumps(system_info, sort_keys=True).encode()).hexdigest()

        # Create packages hash
        packages_hash = hashlib.sha256(dumps(package_data, sort_keys=True).encode()).hexdigest()

        return f"resolution:{packages_hash}:{system_hash}"

    @cached(ttl=CACHE_TTL, key_prefix="dependency_resolution")
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
        import functools

        if self._executor is None:
            with self._resolve_lock:
                if self._executor is None:
                    self._executor = concurrent.futures.ThreadPoolExecutor()
        loop = asyncio.get_running_loop()
        func = functools.partial(
            self._resolve_dependencies_sync,
            packages,
            system_info,
            prefer_compatibility,
            solver_timeout,
        )
        result = await loop.run_in_executor(self._executor, func)
        return result

    def _resolve_dependencies_sync(
        self,
        packages: list[dict[str, Any]],
        system_info: dict[str, Any],
        prefer_compatibility: bool = True,
        solver_timeout: int | None = None,
    ) -> dict[str, Any]:
        """Run dependency resolution synchronously."""
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
        dropped_names: set[str] = set()

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

            # Skip packages with no available versions (e.g. Go pseudo-versions
            # that don't exist on the proxy)
            available_versions = package.get("available_versions", [])
            if not isinstance(available_versions, list) or not available_versions:
                logger.info(
                    "Skipping package with zero available versions",
                    extra={
                        "event": "skip_zero_version_package",
                        "pkg_name": package.get("name"),
                        **context,
                    },
                )
                dropped_names.add(normalize_package_name(package.get("name", "")))
                continue

            normalized_name = normalize_package_name(package["name"])
            normalized_package = copy.deepcopy(package)
            normalized_package["name"] = normalized_name
            # Preserve original name so output uses the non-normalized form
            if normalized_name != package["name"]:
                if normalized_name in self._name_map:
                    logger.warning(
                        "Package name collision: %s -> %s (was %s) — display name may be incorrect",
                        package["name"],
                        normalized_name,
                        self._name_map[normalized_name],
                    )
                self._name_map[normalized_name] = package["name"]

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

        # Check for orphaned dependencies: remaining packages that depend on
        # a dropped package (one with zero available versions). Remove them
        # iteratively so cascading orphans are caught — a package whose
        # transitive dependency was dropped must also be removed, otherwise
        # the solver silently drops the dangling edge.
        if dropped_names:
            all_dropped: set[str] = set(dropped_names)
            while True:
                new_orphans: list[str] = []
                for pkg in normalized_packages:
                    if pkg["name"] in all_dropped:
                        continue
                    for eco_deps in pkg.get("dependencies", {}).values():
                        for dep_name in eco_deps:
                            if dep_name in all_dropped:
                                new_orphans.append(pkg["name"])
                                break
                        if pkg["name"] in new_orphans:
                            break
                if not new_orphans:
                    break
                for name in new_orphans:
                    all_dropped.add(name)
                    logger.warning(
                        "Package %s depends on dropped package (no versions available) — "
                        "marked unsatisfiable",
                        name,
                    )
                normalized_packages = [
                    p for p in normalized_packages if p["name"] not in all_dropped
                ]

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
                gpu_info = {}
                resolved_system_info["gpu"] = gpu_info

            gpu_info.setdefault("available", bool(gpu_info.get("cuda")))
            gpu_info.setdefault("cuda", None)
            gpu_info.setdefault("rocm", None)
            gpu_info.setdefault("intel_gpu", None)
            gpu_info.setdefault("metal", None)

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

    def _reset_solver_state(
        self, solver_timeout: int | None = None, package_count: int = 0
    ) -> None:
        """Reset the solver state and apply timeout if specified.

        Uses z3.Optimize (prefers newer versions) for graphs up to
        *SOLVER_OPTIMIZATION_THRESHOLD* packages.  Falls back to plain
        z3.Solver for larger graphs to avoid solver hangs.
        """
        import z3

        threshold = SOLVER_OPTIMIZATION_THRESHOLD
        self._optimization_active = self._use_optimization and package_count <= threshold
        if self._optimization_active:
            self._solver = z3.Optimize()
            self._minimization_added = False
            self._version_weights = []
        else:
            if self._use_optimization and package_count > threshold:
                logger.warning(
                    "Optimization disabled: %d packages exceeds threshold %d "
                    "(set SOLVER_OPTIMIZATION_THRESHOLD env var to adjust)",
                    package_count,
                    threshold,
                )
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

        logger.error("Unexpected error during dependency resolution", extra=resolution_context)

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
        self._node_by_name.clear()

        # Collect Go replace rules across all root packages
        go_replace: dict[str, str] = {}
        for package in packages:
            pkg_replace = package.get("_go_replace", None)
            if pkg_replace and isinstance(pkg_replace, dict):
                go_replace.update(pkg_replace)

        for package in packages:
            # Package name is already normalized in resolve_dependencies
            pkg_id = f"{package['name']}@{package.get('ecosystem', 'unknown')}"
            # Detect cross-ecosystem name collisions — two packages from different
            # ecosystems with names that normalize to the same string.
            existing = self._node_by_name.get(package["name"])
            if existing and existing != pkg_id:
                logger.warning(
                    "Name collision detected: %s (existing=%s, new=%s) — "
                    "two packages across ecosystems share the same normalized name",
                    package["name"],
                    existing,
                    pkg_id,
                )
            self._node_by_name[package["name"]] = pkg_id
            self.dependency_graph.add_node(pkg_id, **package)

            # Add dependencies as edges, applying Go replace remapping
            for dep_ecosystem, deps in package.get("dependencies", {}).items():
                for dep_name, dep_constraint in deps.items():
                    effective_name = dep_name
                    if dep_ecosystem == "gomodules" and dep_name in go_replace:
                        effective_name = go_replace[dep_name]
                    dep_id = f"{effective_name}@{dep_ecosystem}"
                    self.dependency_graph.add_edge(pkg_id, dep_id, constraint=dep_constraint)

            # Add cross-ecosystem dependency edges
            for xdep in package.get("cross_ecosystem_deps", []):
                target_eco = xdep.get("target_ecosystem", package.get("ecosystem", "unknown"))
                dep_name = xdep.get("name") or xdep.get("dependency", "")
                if dep_name:
                    if target_eco == "gomodules" and dep_name in go_replace:
                        dep_name = go_replace[dep_name]
                    dep_id = f"{dep_name}@{target_eco}"
                    constraint = xdep.get("constraint") or xdep.get("version_spec", "*")
                    self.dependency_graph.add_edge(
                        pkg_id,
                        dep_id,
                        constraint=constraint,
                        cross_ecosystem=True,
                    )

    def _is_prerelease(self, ver: str) -> bool:
        """Check if a version is a pre-release (alpha, beta, dev, rc, canary, next)."""
        return is_prerelease_version(ver)

    def _get_max_clusters(self, n_versions: int) -> int:
        """Compute dynamic cluster count based on version count.

        When SOLVER_MAX_CLUSTERS is explicitly set via env var, that value
        is used as-is.  Otherwise scales with sqrt(n_versions) to give
        packages with many versions more representative coverage.
        """
        import os as _os

        if "SOLVER_MAX_CLUSTERS" in _os.environ:
            return SOLVER_MAX_CLUSTERS
        import math

        return min(
            max(SOLVER_MAX_CLUSTERS_MIN, int(math.sqrt(n_versions)) * 2),
            SOLVER_MAX_CLUSTERS_MAX,
        )

    def _cluster_versions(self, versions: list[str]) -> list[str]:
        """Group versions by major.minor, keep latest stable per cluster.

        Delegates to standalone :func:`_cluster_versions_static`.
        """
        max_clusters = self._get_max_clusters(len(versions))
        return _cluster_versions_static(versions, max_clusters=max_clusters)

    def _create_version_mapping(self, package_name: str, versions: list[str]):
        """Create integer mapping for versions to use in Z3."""
        # Use parse_version for safer version parsing
        parsed_versions = []
        for ver in versions:
            parsed = parse_version(ver)
            if parsed:
                parsed_versions.append((ver, parsed))

        # Sort by parsed version objects descending (latest = idx 0 for optimization)
        sorted_versions = sorted(parsed_versions, key=lambda x: x[1], reverse=True)

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
        self._candidate_lists: dict[str, list[str]] = {}
        self._sys_python_version = (
            system_info.get("runtime_versions", {}).get("python", {}).get("version", "")
        )
        self._sys_cuda_version = _get_gpu_version(system_info, "cuda")
        self._sys_rocm_version = _get_gpu_version(system_info, "rocm")
        self._sys_intel_gpu_version = _get_gpu_version(system_info, "intel_gpu")
        self._sys_metal_version = _get_gpu_version(system_info, "metal")

        # Variable for each package version
        total_vars = 0
        for package in packages:
            pkg_name = package["name"]  # Already normalized
            versions = package.get("available_versions", [])

            # Cluster versions to reduce solver variables and avoid old versions.
            # Skip clustering when per-version deps are present — the solver needs
            # all version variables to match version-specific edge constraints.
            # Also skip for packages that are depended on by packages with per-version
            # deps — clustering may drop versions needed by specific package versions.
            has_version_deps = bool(package.get("version_dependencies", {}))
            inherited_version_deps = has_version_deps
            if not inherited_version_deps:
                pkg_id = f"{pkg_name}@{package.get('ecosystem', 'unknown')}"
                if pkg_id in self.dependency_graph:
                    for pred in self.dependency_graph.predecessors(pkg_id):
                        pred_data = self.dependency_graph.nodes[pred]
                        if pred_data and bool(pred_data.get("version_dependencies", {})):
                            inherited_version_deps = True
                            break
            clustered = versions if inherited_version_deps else self._cluster_versions(versions)

            # Create boolean variable for each version
            constraint = package.get("version_constraint", "*")
            if constraint != "*":
                ecosystem = package.get("ecosystem", "pypi")
                from packaging.specifiers import InvalidSpecifier, SpecifierSet

                from .vers import VersSpec

                spec_str = str(VersSpec.parse(constraint, ecosystem))
                if spec_str != "*":
                    try:
                        SpecifierSet(spec_str)
                    except InvalidSpecifier:
                        try:
                            SpecifierSet(f"=={spec_str}")
                            spec_str = f"=={spec_str}"
                        except InvalidSpecifier:
                            spec_str = "*"
                constraint = spec_str

            sys_py = system_info.get("runtime_versions", {}).get("python", {}).get("version", "")
            ver_python_reqs = package.get("version_requires_python", {})
            sys_reqs = package.get("system_requirements", {})
            python_req = sys_reqs.get("python", {})
            min_python = python_req.get("min_version", "")

            def _build_vars(
                ver_list,
                pkg_name=pkg_name,
                constraint=constraint,
                package=package,
                sys_py=sys_py,
                min_python=min_python,
                ver_python_reqs=ver_python_reqs,
            ):
                vars_list = []
                self._create_version_mapping(pkg_name, ver_list)
                pkg_eco = package.get("ecosystem", "pypi")
                ver_meta = package.get("_version_metadata", {}) or {}
                for v in ver_list:
                    norm_v = normalize_version(v, pkg_eco)
                    if constraint != "*" and not is_compatible_version(norm_v, constraint):
                        continue
                    # Skip deprecated/yanked versions when SOLVER_REJECT_DEPRECATED is true
                    meta = ver_meta.get(v, {})
                    if meta:
                        is_yanked = meta.get("yanked", False)
                        is_deprecated = bool(meta.get("deprecated", False))
                        if (is_yanked or is_deprecated) and SOLVER_REJECT_DEPRECATED:
                            continue
                    # Skip version if Python requirement is incompatible
                    py_req = ver_python_reqs.get(v)
                    if py_req and sys_py:
                        try:
                            from packaging.specifiers import SpecifierSet

                            if sys_py not in SpecifierSet(py_req):
                                continue
                        except Exception:
                            logger.debug("SpecifierSet check failed", exc_info=True)
                    elif sys_py and min_python and compare_versions(sys_py, min_python) < 0:
                        continue
                    var_name = f"{pkg_name}_{v}"
                    var = z3.Bool(var_name)
                    vars_list.append(var)
                    self.version_vars[var_name] = var
                    self._var_to_version[str(var)] = v
                    sorted_idx = self.version_to_int.get(var_name, 0)
                    len(ver_list)
                    weight = sorted_idx + 1
                    if self._is_prerelease(v):
                        weight += SOLVER_PRERELEASE_PENALTY
                    self._version_weights.append(weight * var)
                    if "system_requirements" in package:
                        self._add_system_constraints(
                            var, package["system_requirements"], system_info, constraints
                        )
                return vars_list

            # Build full candidate list (all constraint-compatible versions, unclustered)
            # for _upgrade_to_latest post-processing — avoids clustering blindness
            full_candidates: list[str] = []
            for v in versions:
                if constraint != "*" and not is_compatible_version(v, constraint):
                    continue
                full_candidates.append(v)
            candidate_list = full_candidates if full_candidates else versions
            from packaging.version import InvalidVersion
            from packaging.version import Version as PkgVersion

            try:
                candidate_list = sorted(
                    candidate_list,
                    key=lambda v: PkgVersion(v) if v.count(".") >= 2 else PkgVersion(v + ".0"),
                    reverse=True,
                )
            except (InvalidVersion, Exception):
                pass
            self._candidate_lists[pkg_name] = candidate_list

            version_vars = _build_vars(clustered)
            versions_used = clustered

            # If clustering eliminated all versions matching the constraint,
            # fall back to unclustered list (but still filtered by constraint)
            if not version_vars:
                version_vars = _build_vars(versions)
                versions_used = versions

            # No compatible versions at all — create a sentinel variable that is always False.
            # This ensures packages depending on this one become unsatisfiable
            # instead of silently dropping the dependency from the lock file.
            if not version_vars:
                sentinel_var = z3.Bool(f"{pkg_name}_no_compatible_version")
                self.solver.add(z3.Not(sentinel_var))
                version_vars = [sentinel_var]
                versions_used = []
                logger.warning(f"No compatible version for {pkg_name} — marking unsatisfiable")
            package["available_versions"] = versions_used

            if pkg_name in constraints["package_versions"]:
                logger.warning(
                    "Solver variable collision: %s appears twice with different ecosystems — "
                    "share a single set of version variables",
                    pkg_name,
                )
            constraints["package_versions"][pkg_name] = version_vars
            total_vars += len(version_vars)

            # Max-vars guard to prevent memory blowup on huge graphs
            if total_vars > SOLVER_MAX_VARIABLES:
                logger.warning(
                    f"Solver variable limit ({SOLVER_MAX_VARIABLES}) exceeded at {total_vars} vars — "
                    f"resolution aborted. Increase with SOLVER_MAX_VARIABLES=N env var",
                    extra={
                        "event": "solver_max_vars_reached",
                        "total_vars": total_vars,
                    },
                )
                raise RuntimeError(
                    f"Solver variable limit ({SOLVER_MAX_VARIABLES}) exceeded — "
                    f"cannot guarantee correct resolution. Increase SOLVER_MAX_VARIABLES."
                )

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
            if req_type in ("cuda", "gpu"):
                min_ver = req_value.get("min_version", "") if isinstance(req_value, dict) else ""
                if not min_ver:
                    continue
                sys_cuda = _get_gpu_version(system_info, "cuda")
                if not sys_cuda or compare_versions(sys_cuda, min_ver) < 0:
                    self.solver.add(z3.Not(version_var))
            elif req_type in ("rocm", "intel_gpu", "metal"):
                min_ver = req_value.get("min_version", "") if isinstance(req_value, dict) else ""
                if not min_ver:
                    continue
                sys_ver = _get_gpu_version(system_info, req_type)
                if not sys_ver or compare_versions(sys_ver, min_ver) < 0:
                    self.solver.add(z3.Not(version_var))
            elif req_type == "os":
                allowed = req_value if isinstance(req_value, list) else [req_value]
                sys_os = system_info.get("os", "unknown")
                if sys_os not in allowed and "any" not in allowed:
                    self.solver.add(z3.Not(version_var))
            elif req_type == "arch":
                allowed = req_value if isinstance(req_value, list) else [req_value]
                sys_arch = system_info.get("architecture", "unknown")
                if sys_arch not in allowed and "any" not in allowed:
                    self.solver.add(z3.Not(version_var))

    def _add_dependency_constraints(self, constraints: dict):
        """Add constraints for package dependencies."""
        import z3

        # Pre-compute compatible dep version cache across all edges.
        # Maps (dep_name, parsed_constraint) -> list of valid dep_var_refs.
        compat_cache: dict[tuple[str, str], list] = {}

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

                # Normalize ecosystem-specific constraint via VersSpec
                from packaging.specifiers import InvalidSpecifier, SpecifierSet

                from .vers import VersSpec

                successor_data = self.dependency_graph.nodes.get(successor, {})
                dep_eco = successor_data.get("ecosystem", "unknown")
                parsed_constraint = str(VersSpec.parse(constraint_str, dep_eco))
                if parsed_constraint != "*":
                    spec_valid = False
                    try:
                        SpecifierSet(parsed_constraint)
                        spec_valid = True
                    except InvalidSpecifier:
                        try:
                            SpecifierSet(f"=={parsed_constraint}")
                            parsed_constraint = f"=={parsed_constraint}"
                            spec_valid = True
                        except InvalidSpecifier:
                            pass
                    if not spec_valid:
                        fallback = _normalize_npm_constraint(constraint_str, dep_eco)
                        if fallback is not None:
                            parsed_constraint = fallback
                            spec_valid = True
                        else:
                            logger.warning(
                                "Failed to normalize dependency constraint '%s' for %s — "
                                "treating as 'any version'",
                                constraint_str,
                                dep_eco,
                            )
                            parsed_constraint = "*"

                # Get successor package info
                dep_name = successor_data.get("name", successor.rsplit("@", 1)[0])

                # Build compat cache entry lazily (once per unique dep_name+constraint)
                cache_key = (dep_name, parsed_constraint)
                if cache_key not in compat_cache:
                    valid = []
                    if dep_name in constraints["package_versions"]:
                        for dep_var in constraints["package_versions"][dep_name]:
                            dep_version = self._var_to_version.get(
                                str(dep_var), str(dep_var).split("_")[-1]
                            )
                            norm_dep_version = normalize_version(dep_version, dep_eco)
                            dep_var_ref = self.version_vars.get(str(dep_var))
                            if dep_var_ref is not None and is_compatible_version(
                                norm_dep_version, parsed_constraint
                            ):
                                valid.append(dep_var_ref)
                    compat_cache[cache_key] = valid

                # For each version of the dependent package
                if pkg_name in constraints["package_versions"]:
                    for pkg_var in constraints["package_versions"][pkg_name]:
                        pkg_var_ref = self.version_vars.get(str(pkg_var))

                        if pkg_var_ref is not None:
                            # Start with the flat-edge constraint's compatible dep versions.
                            valid_dep_vars = compat_cache[cache_key]

                            # Check for version-specific dependency constraints.
                            # Some packages (notably npm) have different deps per version —
                            # the edge's flat constraint is from the latest version only.
                            pkg_version = self._var_to_version.get(str(pkg_var), "")
                            version_deps = node_data.get("version_dependencies", {})
                            ver_specific = (
                                version_deps.get(pkg_version, {})
                                if isinstance(version_deps, dict)
                                else {}
                            )
                            if ver_specific:
                                ver_dep_constraint = None
                                dep_ecosystem_val = successor_data.get("ecosystem", "unknown")
                                for v_eco, v_deps in ver_specific.items():
                                    if dep_name in v_deps:
                                        ver_dep_constraint = v_deps[dep_name]
                                        break
                                if (
                                    ver_dep_constraint is not None
                                    and ver_dep_constraint != constraint_str
                                ):
                                    ver_parsed = str(
                                        VersSpec.parse(ver_dep_constraint, dep_ecosystem_val)
                                    )
                                    cache_key_ver = (dep_name, ver_parsed)
                                    if cache_key_ver not in compat_cache:
                                        valid_ver = []
                                        if dep_name in constraints["package_versions"]:
                                            for dep_var in constraints["package_versions"][
                                                dep_name
                                            ]:
                                                dep_version = self._var_to_version.get(
                                                    str(dep_var), str(dep_var).split("_")[-1]
                                                )
                                                norm_dep_version = normalize_version(
                                                    dep_version, dep_ecosystem_val
                                                )
                                                dep_var_ref = self.version_vars.get(str(dep_var))
                                                if (
                                                    dep_var_ref is not None
                                                    and is_compatible_version(
                                                        norm_dep_version, ver_parsed
                                                    )
                                                ):
                                                    valid_ver.append(dep_var_ref)
                                        compat_cache[cache_key_ver] = valid_ver
                                    valid_dep_vars = compat_cache[cache_key_ver]

                            if valid_dep_vars:
                                self.solver.add(z3.Implies(pkg_var_ref, z3.Or(valid_dep_vars)))
                            elif (
                                dep_name in constraints["package_versions"]
                                and constraints["package_versions"][dep_name]
                            ):
                                self.solver.add(z3.Not(pkg_var_ref))

    def _get_pkg_field(self, package: dict, field_path: str) -> Any:
        """Get a nested field value from a package dict by dot-separated path."""
        value = package
        for part in field_path.split("."):
            if isinstance(value, dict):
                value = value.get(part, {})
            else:
                return None
        return value if value != {} else None

    def _add_conflict_constraints(self, packages: list[dict], constraints: dict):
        """Add known conflict constraints from data-driven CONFLICT_RULES.

        For version-range-type rules (cuda, rocm, etc.): finds packages whose
        system_requirements.<type>.min_version falls into each of two ranges and
        adds cross-product conflict constraints between them.
        For dependency-type rules: adds version constraints on specific deps.
        """
        import z3

        pkg_by_name = {p["name"]: p for p in packages}

        def _pkg_field_val(pkg: dict, field_path: str) -> Any:
            value = pkg
            for part in field_path.split("."):
                if isinstance(value, dict):
                    value = value.get(part, {})
                else:
                    return None
            return value if value != {} else None

        def _field_match(val: Any, op: str, target: str) -> bool:
            from backend.core.utils import compare_versions

            try:
                cmp = compare_versions(str(val), target)
                if op == ">=":
                    return cmp >= 0
                if op == "<=":
                    return cmp <= 0
                if op == ">":
                    return cmp > 0
                if op == "<":
                    return cmp < 0
                if op == "==":
                    return cmp == 0
                if op == "!=":
                    return cmp != 0
            except Exception:
                logger.debug(
                    "Failed to compare version constraint %s %s %s", val, op, target, exc_info=True
                )
            return False

        def _in_range(pkg: dict, lo_constraint: dict, hi_constraint: dict) -> bool:
            """Check if pkg's field falls in [lo, hi) range defined by two constraints."""
            field = lo_constraint.get("field", "cuda.min_version")
            val = _pkg_field_val(pkg, field)
            if val is None:
                return False
            if not _field_match(val, lo_constraint.get("op", ">="), lo_constraint.get("value", "")):
                return False
            return _field_match(val, hi_constraint.get("op", "<"), hi_constraint.get("value", ""))

        for rule in CONFLICT_RULES:
            rule_type = rule.get("type")
            if rule_type in ("cuda", "rocm"):
                constraint_a = rule.get("constraint_a", {})
                constraint_b = rule.get("constraint_b", {})
                exclusive = rule.get("mutually_exclusive_with", {})

                # Group A: matches constraint_a AND NOT exclusive
                # Group B: matches constraint_b (which is the other range entirely)
                field = constraint_a.get("field", "cuda.min_version")
                group_a = []
                group_b = []
                for pkg in packages:
                    val = _pkg_field_val(pkg, field)
                    if val is None:
                        continue
                    in_a = _field_match(
                        val, constraint_a.get("op", ">="), constraint_a.get("value", "")
                    ) and not _field_match(
                        val, exclusive.get("op", ">="), exclusive.get("value", "")
                    )
                    if in_a:
                        group_a.append(pkg["name"])
                        continue
                    if _field_match(
                        val, constraint_b.get("op", "<"), constraint_b.get("value", "")
                    ):
                        group_b.append(pkg["name"])

                # Guard CUDA cross-product: skip if too many combinations
                if len(group_a) * len(group_b) > 500:
                    continue
                for pkg_a in group_a:
                    for pkg_b in group_b:
                        if pkg_a == pkg_b:
                            continue
                        constraints["conflicts"].append((pkg_a, pkg_b))
                        if (
                            pkg_a in constraints["package_versions"]
                            and pkg_b in constraints["package_versions"]
                        ):
                            for var_a in constraints["package_versions"][pkg_a]:
                                for var_b in constraints["package_versions"][pkg_b]:
                                    ref_a = self.version_vars.get(str(var_a))
                                    ref_b = self.version_vars.get(str(var_b))
                                    if ref_a is not None and ref_b is not None:
                                        self.solver.add(z3.Not(z3.And(ref_a, ref_b)))

            elif rule_type == "dependency":
                pkg_names = rule.get("packages", [])
                dep_constraints = rule.get("constraint", {})
                for pkg_name in pkg_names:
                    pkg = pkg_by_name.get(pkg_name)
                    if not pkg:
                        continue
                    for dep_name, dep_ver_constraint in dep_constraints.items():
                        constraints.setdefault("dependency_constraints", {}).setdefault(
                            dep_name, []
                        ).append(dep_ver_constraint)

    @staticmethod
    def _compare_field(field_val: Any, op: str, target: str) -> bool:
        """Compare field_val against target using operator op."""
        from backend.core.utils import compare_versions

        try:
            cmp = compare_versions(str(field_val), target)
            if op == ">=":
                return cmp >= 0
            if op == "<=":
                return cmp <= 0
            if op == ">":
                return cmp > 0
            if op == "<":
                return cmp < 0
            if op == "==":
                return cmp == 0
            if op == "!=":
                return cmp != 0
        except Exception:
            logger.debug("Field comparison failed: %s %s %s", field_val, op, target, exc_info=True)
            return False
        return False

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
                        version_str = self._var_to_version.get(str(var), str(var).split("_", 1)[-1])
                        display_name = self._name_map.get(pkg_name, pkg_name)
                        pkg_entry: dict[str, Any] = {
                            "version": version_str,
                            "ecosystem": self._get_ecosystem(pkg_name),
                        }
                        node = self._node_by_name.get(pkg_name)
                        if node:
                            nd = self.dependency_graph.nodes.get(node, {})
                            meta = nd.get("_version_metadata", {}).get(version_str, {})
                            if meta.get("yanked"):
                                pkg_entry["yanked"] = True
                            if meta.get("deprecated"):
                                pkg_entry["deprecated"] = True
                        solution["packages"][display_name] = pkg_entry
                        break

            # Fold deprecation/yanked warnings into solution
            dep_warnings = getattr(self, "_deprecation_warnings", [])
            if dep_warnings:
                solution.setdefault("warnings", []).extend(dep_warnings)

            # Post-process: when optimization is not actually active, upgrade
            # each package to the newest candidate that satisfies all constraints.
            if not getattr(self, "_optimization_active", self._use_optimization):
                try:
                    self._upgrade_to_latest(solution, constraints)
                except (KeyError, AttributeError):
                    logger.debug("Upgrade-to-latest skipped (missing solver state)")

            return solution
        if result == z3.unknown:
            logger.warning("Z3 solver returned unknown (likely timeout or incomplete)")
            return {
                "status": "timeout",
                "conflicts": [],
                "message": "Solver timed out or could not determine satisfiability",
            }
        return {"status": "unsatisfiable", "conflicts": self._analyze_conflicts()}

    def _upgrade_to_latest(self, solution: dict, constraints: dict) -> None:
        """Post-process SAT solution: upgrade each package to newest feasible version.

        When optimization is disabled (large graphs), the solver may pick arbitrary
        versions. This method tries each package's newer candidates and keeps the
        upgrade if all dependency constraints remain satisfied.
        """
        candidates = getattr(self, "_candidate_lists", None)
        if candidates is None or len(candidates) > 300:
            return
        pkgs = solution.get("packages", {})
        if not pkgs:
            return

        from packaging.specifiers import InvalidSpecifier, SpecifierSet

        from .constraint_normalizer import normalize_constraint

        # Build lookup: pkg_name -> ecosystem
        pkg_eco = {}
        for node in self.dependency_graph.nodes():
            nd = self.dependency_graph.nodes[node]
            name = nd.get("name")
            if name:
                pkg_eco[name] = nd.get("ecosystem", "pypi")

        # Pre-compute dependency constraints: for each package A that depends on B,
        # store (A_version, B, constraint_str).
        # Iterate edges in dependency graph.
        dep_edges: list[tuple[str, str, str, str]] = []
        for node in self.dependency_graph.nodes():
            nd = self.dependency_graph.nodes[node]
            src_name = nd.get("name")
            if src_name is None:
                continue
            for successor in self.dependency_graph.successors(node):
                edge_data = self.dependency_graph.get_edge_data(node, successor)
                con_str = edge_data.get("constraint", "")
                if not con_str:
                    continue
                snd = self.dependency_graph.nodes.get(successor, {})
                dep_name = snd.get("name")
                if dep_name is None:
                    continue
                dep_eco = pkg_eco.get(dep_name, "pypi")
                parsed = normalize_constraint(con_str, dep_eco)
                if parsed and parsed != "*":
                    dep_edges.append((src_name, dep_name, parsed, dep_eco))

        # Per-version Python requirements, own-version constraints, and CUDA system requirements
        ver_python_reqs: dict[str, dict[str, str]] = {}
        own_constraints: dict[str, str] = {}
        pkg_sys_reqs: dict[str, dict] = {}
        for node in self.dependency_graph.nodes():
            nd = self.dependency_graph.nodes[node]
            name = nd.get("name")
            if name:
                vpr = nd.get("version_requires_python", {})
                if isinstance(vpr, dict):
                    ver_python_reqs[name] = vpr
                vc = nd.get("version_constraint", "")
                if vc and vc != "*":
                    own_constraints[name] = vc
                sr = nd.get("system_requirements", {})
                if isinstance(sr, dict):
                    pkg_sys_reqs[name] = sr

        def _check_version(v: str, constraint: str, eco: str) -> bool:
            try:
                spec = SpecifierSet(constraint)
                return v in spec
            except (InvalidSpecifier, Exception):
                logger.debug(
                    "SpecifierSet parse failed for constraint=%r", constraint, exc_info=True
                )
            return True

        def _check_assignment(assigned: dict[str, str]) -> bool:
            for src, dep, con, eco in dep_edges:
                src_ver = assigned.get(src)
                dep_ver = assigned.get(dep)
                if src_ver is None or dep_ver is None:
                    continue
                if not _check_version(dep_ver, con, eco):
                    return False
            return True

        # Build current assignment
        current = {n: info.get("version", "") for n, info in pkgs.items()}

        # Try upgrading each package (iterate in sorted order for determinism)
        for pkg_name in sorted(self._candidate_lists, key=lambda n: (pkg_eco.get(n, ""), n)):
            candidates = self._candidate_lists[pkg_name]
            if pkg_name not in current or not candidates:
                continue
            current_ver = current[pkg_name]
            # Find best (newest) candidate that is newer than current
            best = current_ver
            for c in candidates:
                if c == current_ver:
                    break  # candidates are sorted newest-first; past current = older
                if self._is_prerelease(c):
                    continue
                # Check own-version constraint (e.g. numpy>=1.20,<1.25)
                own_con = own_constraints.get(pkg_name)
                if own_con and not _check_version(c, own_con, pkg_eco.get(pkg_name, "pypi")):
                    continue
                # Check per-version Python requirement
                py_req = ver_python_reqs.get(pkg_name, {}).get(c)
                if py_req and self._sys_python_version:
                    try:
                        if self._sys_python_version not in SpecifierSet(py_req):
                            continue
                    except Exception:
                        logger.debug("Python version check failed", exc_info=True)
                # Check GPU system requirements for this package
                sr = pkg_sys_reqs.get(pkg_name, {})
                # Check CUDA
                cuda_req = sr.get("cuda") or sr.get("gpu")
                if cuda_req and isinstance(cuda_req, dict):
                    min_cuda = cuda_req.get("min_version", "")
                    if min_cuda and (
                        not self._sys_cuda_version
                        or compare_versions(self._sys_cuda_version, min_cuda) < 0
                    ):
                        continue
                # Check ROCm
                rocm_req = sr.get("rocm")
                if rocm_req and isinstance(rocm_req, dict):
                    min_rocm = rocm_req.get("min_version", "")
                    if min_rocm and (
                        not self._sys_rocm_version
                        or compare_versions(self._sys_rocm_version, min_rocm) < 0
                    ):
                        continue
                # Check Intel GPU
                intel_req = sr.get("intel_gpu")
                if intel_req and isinstance(intel_req, dict):
                    min_intel = intel_req.get("min_version", "")
                    if min_intel and (
                        not self._sys_intel_gpu_version
                        or compare_versions(self._sys_intel_gpu_version, min_intel) < 0
                    ):
                        continue
                # Check Metal
                metal_req = sr.get("metal")
                if metal_req and isinstance(metal_req, dict):
                    min_metal = metal_req.get("min_version", "")
                    if min_metal and (
                        not self._sys_metal_version
                        or compare_versions(self._sys_metal_version, min_metal) < 0
                    ):
                        continue
                # Check deprecation/yanked when SOLVER_REJECT_DEPRECATED is True
                if SOLVER_REJECT_DEPRECATED:
                    node_id = f"{pkg_name}@{pkg_eco.get(pkg_name, 'unknown')}"
                    if node_id in self.dependency_graph:
                        nd = self.dependency_graph.nodes[node_id]
                        meta = nd.get("_version_metadata", {}).get(c, {})
                        if meta.get("yanked") or bool(meta.get("deprecated")):
                            continue
                # Try this version
                old = current[pkg_name]
                current[pkg_name] = c
                if _check_assignment(current):
                    best = c
                else:
                    current[pkg_name] = old
            if best != current_ver:
                current[pkg_name] = best
                pkgs[pkg_name] = {
                    "version": best,
                    "ecosystem": pkg_eco.get(pkg_name, "?"),
                }

    def _resolve_with_alternatives(self, packages: list[dict], system_info: dict) -> dict:
        """Conflict diagnostic tool: explains WHY Z3 could not find a solution.

        Instead of attempting an alternative resolution (Z3's CDCL is already
        complete), this method analyses the dependency graph and produces a
        human-readable explanation of the conflict.

        Returns a dict with ``"status": "unsatisfiable"`` and a ``"diagnosis"``
        field listing the conflicting constraint chains.
        """

        result: dict[str, Any] = {
            "status": "unsatisfiable",
            "packages": {},
            "diagnosis": [],
            "warnings": [],
        }

        pkg_map: dict[str, dict] = {}
        for pkg in packages:
            name = pkg["name"]
            pkg_map[name] = pkg

        # Identify packages with NO compatible versions
        for pkg in packages:
            name = pkg["name"]
            versions = self._find_compatible_versions(pkg, system_info)
            if not versions:
                dep_warnings = getattr(self, "_deprecation_warnings", [])
                dep_msgs = [w for w in dep_warnings if name in w]
                if dep_msgs:
                    result["diagnosis"].append(f"{name}: all versions are yanked or deprecated")
                else:
                    result["diagnosis"].append(f"{name}: no version satisfies system constraints")

        # Build candidate versions per package
        candidate_versions: dict[str, list[str]] = {}
        for pkg in packages:
            name = pkg["name"]
            compatible = self._find_compatible_versions(pkg, system_info)
            candidate_versions[name] = compatible or []

        # Build dependency constraints: for each pkg, store (dep_name, constraint, dep_eco)
        dep_constraints: dict[str, list[tuple[str, str, str]]] = {}
        for pkg in packages:
            name = pkg["name"]
            for eco_key, deps in pkg.get("dependencies", {}).items():
                if isinstance(deps, dict):
                    for dep_name, constraint in deps.items():
                        dep_constraints.setdefault(dep_name, [])
                        dep_constraints[dep_name].append((constraint, eco_key, name))

        if not result["diagnosis"]:
            for pkg in packages:
                name = pkg["name"]
                for eco_key, deps in pkg.get("dependencies", {}).items():
                    if isinstance(deps, dict):
                        for dep_name, constraint in deps.items():
                            if dep_name == name:
                                result["diagnosis"].append(
                                    f"{name}: self-referential dependency {constraint}"
                                )
                            elif dep_name in candidate_versions:
                                dep_versions = candidate_versions[dep_name]
                                from packaging.specifiers import InvalidSpecifier, SpecifierSet

                                from .constraint_normalizer import normalize_constraint

                                normed = normalize_constraint(constraint, eco_key)
                                if normed and normed != "*":
                                    try:
                                        spec = SpecifierSet(normed)
                                        matching = [v for v in dep_versions if v in spec]
                                        if not matching:
                                            result["diagnosis"].append(
                                                f"{name} requires {dep_name} ({constraint}) "
                                                f"but {dep_name} has no matching version"
                                            )
                                    except (InvalidSpecifier, Exception):
                                        pass

        if not result["diagnosis"]:
            result["diagnosis"].append(
                "Constraint conflict detected \u2014 run with --json for full dependency graph"
            )

        return result

    def _find_compatible_versions(self, package: dict, system_info: dict) -> list[str]:
        """Find versions compatible with system requirements."""
        compatible = []
        from backend.settings import SOLVER_REJECT_DEPRECATED as _REJECT_DEP

        deprecation_warnings: list[str] = []
        version_metadata = package.get("_version_metadata", {}) or {}
        pkg_name = package.get("name", "unknown")

        # Apply version_constraint from manifest (e.g. >=3.11,<3.13)
        version_constraint = package.get("version_constraint", "*")

        # Per-version Python requirements (precise per version, not package-level)
        ver_python_reqs = package.get("version_requires_python", {})

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

            # Apply per-version Python requirement (more precise than package-level)
            sys_python = (
                system_info.get("runtime_versions", {}).get("python", {}).get("version", "")
            )
            py_req = ver_python_reqs.get(version_str)
            if py_req and sys_python:
                try:
                    from packaging.specifiers import SpecifierSet

                    if sys_python not in SpecifierSet(py_req):
                        continue
                except Exception:
                    logger.debug("Python version filter failed", exc_info=True)
            elif sys_python and min_python and compare_versions(sys_python, min_python) < 0:
                continue
            if min_cuda:
                sys_cuda = system_info.get("gpu", {}).get("cuda", "")
                if sys_cuda and compare_versions(sys_cuda, min_cuda) < 0:
                    continue

            # Wheel platform compatibility check: skip versions whose wheels
            # are incompatible with the target OS/arch (from PyPI platforms data).
            version_platforms = package.get("version_platforms", {})
            plat_list = version_platforms.get(version_str)
            if plat_list:
                from backend.core.wheel_tags import check_platform_compatibility

                if not check_platform_compatibility(plat_list, system_info):
                    continue

            # Check deprecation/yanked status
            meta = version_metadata.get(version_str, {})
            if meta:
                is_yanked = meta.get("yanked", False)
                is_deprecated = bool(meta.get("deprecated", False))
                if is_yanked or is_deprecated:
                    label = "yanked" if is_yanked else "deprecated"
                    if _REJECT_DEP:
                        deprecation_warnings.append(
                            f"{pkg_name} {version_str} is {label} — excluded"
                        )
                        continue
                    deprecation_warnings.append(
                        f"{pkg_name} {version_str} is {label} — included with warning"
                    )

            # Skip pre-release versions in fallback path
            if self._is_prerelease(version_str):
                continue

            compatible.append(version_str)

        if deprecation_warnings:
            existing = getattr(self, "_deprecation_warnings", [])
            self._deprecation_warnings = existing + deprecation_warnings

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

        # Check ROCm compatibility
        if "rocm" in requirements and "gpu" in system_info:
            sys_rocm = _get_gpu_version(system_info, "rocm")
            if not sys_rocm:
                return False
            min_rocm = requirements["rocm"].get("min_version", "0.0")
            if compare_versions(sys_rocm, min_rocm) < 0:
                return False

        # Check Intel GPU compatibility
        if "intel_gpu" in requirements and "gpu" in system_info:
            sys_intel = _get_gpu_version(system_info, "intel_gpu")
            if not sys_intel:
                return False
            min_intel = requirements["intel_gpu"].get("min_version", "0.0")
            if compare_versions(sys_intel, min_intel) < 0:
                return False

        # Check Metal compatibility
        if "metal" in requirements and "gpu" in system_info:
            sys_metal = _get_gpu_version(system_info, "metal")
            if not sys_metal:
                return False
            min_metal = requirements["metal"].get("min_version", "0.0")
            if compare_versions(sys_metal, min_metal) < 0:
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
                logger.warning("Failed to detect cycles in dependency graph", exc_info=True)
            return list(packages.keys())

    def _get_ecosystem(self, package_name: str) -> str:
        """Get ecosystem for a package from the graph."""
        node = self._node_by_name.get(package_name)
        if node:
            return node.rsplit("@", 1)[-1]
        return "unknown"

    def _get_package_dependencies(self, package_name: str, version_str: str) -> dict:
        """Get dependencies for a specific package version."""
        dependencies: dict[str, Any] = {}

        # Find the node in the graph
        pkg_node = self._node_by_name.get(package_name)

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

            dep_name = successor_data.get("name", successor.split("@", 1)[-1])
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

        for idx, assertion in enumerate(self.solver.assertions()):
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
            elif "Not(" in assertion_str and "_no_compatible_version" not in assertion_str:
                assertion_info[track_var] = {
                    "type": "exclusion",
                    "constraint": assertion_str,
                }
            elif "Or(" in assertion_str:
                assertion_info[track_var] = {
                    "type": "version_selection",
                    "constraint": assertion_str,
                }
            else:
                assertion_info[track_var] = {
                    "type": "other",
                    "constraint": assertion_str,
                }

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
                    package_pattern = r"(.+?)_(\d[\w.]*(?:[-.]\w+)*)"
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
        if info["type"] == "dependency" and len(packages) >= 2:
            return f"{packages[0]['name']} {packages[0]['version']} requires incompatible version of {packages[1]['name']}"
        if info["type"] == "conflict" and len(packages) >= 2:
            return f"{packages[0]['name']} {packages[0]['version']} conflicts with {packages[1]['name']} {packages[1]['version']}"

        return f"Constraint conflict: {info['constraint']}"
