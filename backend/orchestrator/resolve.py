"""Resolution orchestration — shared by CLI and API.

Pure-logic functions for package spec parsing, transitive resolution,
CUDA variant selection, and aggregator → resolver data conversion.
"""

import asyncio
import logging
import re
from typing import Any

from packaging import version as _pkg_version

from backend.core.constraint_normalizer import normalize_constraint, normalize_version
from backend.core.markers import evaluate_marker_string
from backend.settings import (
    BFS_BATCH_SIZE,
    INCREMENTAL_RESOLUTION,
    PEER_DEP_MODE,
    SOLVER_MAX_VARIABLES,
)
from backend.settings import ECOSYSTEMS as _SETTINGS_ECOSYSTEMS
from backend.tracing_config import get_tracer

_VALID_ECOSYSTEMS = {e for e in _SETTINGS_ECOSYSTEMS if e not in ("docs", "custom_db")}

logger = logging.getLogger(__name__)


def _maybe_wrap_forking(solver: Any) -> Any:
    """Wrap *solver* with ``ForkingResolver`` when ``USE_FORKING_SOLVER=true``."""
    import backend.settings as _s

    if not _s.USE_FORKING_SOLVER:
        return solver

    try:
        from backend.core.forking_resolver import ForkingResolver

        logger.info("Wrapping solver with ForkingResolver (USE_FORKING_SOLVER=true)")
        return ForkingResolver(
            base_solver=solver,
            max_forks=_s.FORKING_MAX_FORKS,
            fork_timeout_ratio=_s.FORKING_TIMEOUT_RATIO,
        )
    except ImportError:
        logger.warning("ForkingResolver module not available; using unwrapped solver")
        return solver


def create_solver(*, use_optimization: bool = True, solver_timeout: int | None = None) -> Any:
    """Create a solver instance.

    Default: AutoSolver — profiles the dependency graph and selects the
    fastest solver backend automatically.

    Override via env vars (in priority order):
      1. USE_Z3_SOLVER=true        → ConflictResolver (Z3)
      2. USE_HYBRID_SOLVER=true    → HybridSolver (PubGrub + Z3)
      3. USE_PUBGRUB_SOLVER=true   → PubGrubSolver
      4. Default                   → AutoSolver

    When ``USE_FORKING_SOLVER=true``, the selected solver is wrapped in
    a :class:`ForkingResolver` that forks parallel alternatives on failure.
    """
    import backend.settings as _s

    solver: Any = None

    if _s.USE_Z3_SOLVER:
        try:
            from backend.core.conflict_resolver import ConflictResolver

            logger.info("Using Z3 ConflictResolver (USE_Z3_SOLVER=true)")
            solver = ConflictResolver(use_optimization=use_optimization)
            return _maybe_wrap_forking(solver)
        except ImportError:
            logger.warning(
                "USE_Z3_SOLVER is true but z3-solver is not installed; falling back to AutoSolver"
            )

    if _s.USE_HYBRID_SOLVER:
        try:
            from backend.core.hybrid_solver import HybridSolver

            logger.info("Using HybridSolver (USE_HYBRID_SOLVER=true)")
            solver = HybridSolver(
                use_optimization=use_optimization,
                solver_timeout=solver_timeout,
            )
            return _maybe_wrap_forking(solver)
        except ImportError:
            logger.warning(
                "USE_HYBRID_SOLVER is true but hybrid_solver module not available; "
                "falling back to AutoSolver"
            )

    if _s.USE_PUBGRUB_SOLVER:
        try:
            from backend.core.pubgrub_solver import PubGrubSolver

            logger.info("Using PubGrubSolver (USE_PUBGRUB_SOLVER=true)")
            solver = PubGrubSolver(
                use_optimization=use_optimization,
                solver_timeout=solver_timeout,
            )
            return _maybe_wrap_forking(solver)
        except ImportError:
            logger.warning(
                "USE_PUBGRUB_SOLVER is true but pubgrub_solver module not available; "
                "falling back to AutoSolver"
            )

    # Default: AutoSolver — profiles and delegates automatically
    try:
        from backend.core.auto_solver import AutoSolver

        logger.info("Using AutoSolver (profiles graph and selects best backend)")
        solver = AutoSolver(
            use_optimization=use_optimization,
            solver_timeout=solver_timeout,
        )
        return _maybe_wrap_forking(solver)
    except ImportError:
        logger.info("AutoSolver not available; falling back to PubGrub")

    try:
        from backend.core.pubgrub_solver import PubGrubSolver

        logger.info("Using PubGrub solver (fallback)")
        solver = PubGrubSolver(
            use_optimization=use_optimization,
            solver_timeout=solver_timeout,
        )
        return _maybe_wrap_forking(solver)
    except ImportError:
        logger.info("PubGrubSolver not available; falling back to Z3")

    from backend.core.conflict_resolver import ConflictResolver

    solver = ConflictResolver(use_optimization=use_optimization)
    return _maybe_wrap_forking(solver)


def _safe_version_key(v: str, ecosystem: str) -> _pkg_version.Version:
    try:
        return _pkg_version.parse(v)
    except Exception:
        try:
            return _pkg_version.parse(normalize_version(v, ecosystem))
        except Exception:
            logger = logging.getLogger(__name__)
            logger.warning("Failed to parse version string '%s'", v, exc_info=True)
            return _pkg_version.parse("0.0.0")


def _parse_package_spec(
    spec: str,
    default_ecosystem: str = "pypi",
) -> tuple[str, str, str | None]:
    spec = spec.strip()
    constraint: str | None = None
    name_part = spec
    eco = default_ecosystem
    if "@" in spec:
        name_part, eco = spec.rsplit("@", 1)
        name_part = name_part.strip()
        eco = eco.strip().lower()
        if not name_part and eco in _VALID_ECOSYSTEMS:
            return spec.lstrip("@"), default_ecosystem, None
        if eco not in _VALID_ECOSYSTEMS:
            logger.warning("Unknown ecosystem '%s' in '%s'", eco, spec)
            return spec, default_ecosystem, None
    constraint_match = re.match(
        r"^([a-zA-Z0-9][a-zA-Z0-9._\-]*)([><=!]+.*)$",
        name_part,
    )
    if constraint_match:
        name_part = constraint_match.group(1)
        constraint = constraint_match.group(2).strip()
    return name_part, eco, constraint


def _extract_system_requirements(agg_data: dict, ecosystem: str) -> dict:
    sys_reqs: dict = {}
    eco_reqs = agg_data.get("system_requirements", {}).get(ecosystem, [])
    runtime_map = {
        "pypi": "python",
        "npm": "node",
        "crates": "rust",
        "rubygems": "ruby",
        "packagist": "php",
        "nuget": "dotnet",
    }
    runtime_field = runtime_map.get(ecosystem, ecosystem)
    os_list: list[str] = []
    arch_list: list[str] = []
    for req in eco_reqs:
        if req.type == "runtime" and req.name == runtime_field and req.version_spec:
            min_ver = req.version_spec.lstrip(">= ")
            sys_reqs[runtime_field] = {"min_version": min_ver}
        elif req.type == "os" and req.name:
            os_list.append(req.name)
        elif req.type == "arch" and req.name:
            arch_list.append(req.name)
    if os_list:
        sys_reqs["os"] = os_list
    if arch_list:
        sys_reqs["arch"] = arch_list
    eco_data = agg_data.get("ecosystems", {}).get(ecosystem, {})
    cuda_req = eco_data.get("system_requirements", {}).get("cuda")
    if cuda_req:
        sys_reqs["cuda"] = cuda_req
    return sys_reqs


def _aggregator_to_resolver_input(
    agg_data: dict,
    ecosystem: str,
    constraint: str | None = None,
    extras: list[str] | None = None,
    system_info: dict | None = None,
    include_optional: bool = False,
) -> dict:
    available_versions = []
    version_requires_python: dict[str, str] = {}
    version_platforms: dict[str, list[str]] = {}
    raw_versions = agg_data.get("versions", {}).get(ecosystem, [])
    for vinfo in raw_versions:
        ver = vinfo.get("version", "") if isinstance(vinfo, dict) else str(vinfo)
        # Handle nested version objects (e.g. CocoaPods: {"version": {"name": "1.0.0", ...}})
        if isinstance(ver, dict):
            ver = ver.get("name", "") if isinstance(ver, dict) else str(ver)
        if isinstance(ver, str) and not re.search(r"\+cu\d", ver):
            available_versions.append(ver)
            if isinstance(vinfo, dict):
                rp = vinfo.get("requires_python") or vinfo.get("python_requires")
                if rp:
                    version_requires_python[ver] = rp
                platforms = vinfo.get("platforms")
                if platforms:
                    version_platforms[ver] = (
                        list(platforms) if isinstance(platforms, (list, set)) else []
                    )
    deps = {}
    eco_deps = agg_data.get("dependencies", {})
    eco_deps = {} if isinstance(eco_deps, list) else eco_deps.get(ecosystem, {})
    for dep in eco_deps.get("all", []):
        if not include_optional:
            if getattr(dep, "dev_only", False):
                continue
            if getattr(dep, "optional", False):
                continue
        if PEER_DEP_MODE == "advisory" and getattr(dep, "peer", False):
            continue
        marker = getattr(dep, "marker", None)
        if marker and not evaluate_marker_string(marker, system_info):
            continue
        deps[dep.name] = normalize_constraint(dep.version_spec, ecosystem)
    if extras:
        extra_map = eco_deps.get("extras", {})
        for extra_name in extras:
            for pkg_name, version_spec in extra_map.get(extra_name, {}).items():
                if pkg_name not in deps:
                    deps[pkg_name] = normalize_constraint(version_spec, ecosystem)
    sys_reqs = _extract_system_requirements(agg_data, ecosystem)
    norm_constraint = normalize_constraint(constraint or "*", ecosystem)
    sorted_versions = sorted(
        set(available_versions),
        key=lambda v: _safe_version_key(v, ecosystem),
        reverse=True,
    )
    go_replace = agg_data.get("_go_replace", {}).get(ecosystem) or agg_data.get("go_replace")
    result: dict[str, Any] = {
        "name": agg_data.get("name"),
        "ecosystem": ecosystem,
        "version_constraint": norm_constraint,
        "available_versions": sorted_versions,
        "version_requires_python": version_requires_python,
        "version_platforms": version_platforms,
        "dependencies": {ecosystem: deps},
        "system_requirements": sys_reqs,
        "cross_ecosystem_deps": agg_data.get("cross_ecosystem_deps", []),
    }
    if go_replace:
        result["_go_replace"] = go_replace
    return result


async def _fetch_dep_info(
    aggregator,
    name: str,
    ecosystem: str,
    include_extended: bool = True,
) -> dict | None:
    try:
        return await aggregator.get_package_info(
            name,
            ecosystem=ecosystem,
            include_dependencies=True,
            include_versions=True,
            include_extended=include_extended,
        )
    except Exception as exc:
        logger.warning("Failed to fetch transitive dep %s/%s: %s", name, ecosystem, exc)
        return None


def _determine_dep_ecosystem(dep: Any, dep_eco: str, pkg_ecosystem: str) -> str:
    dep_ecosystem = getattr(dep, "ecosystem", None)
    if dep_ecosystem is not None:
        dep_eco_str = dep_ecosystem.value if hasattr(dep_ecosystem, "value") else str(dep_ecosystem)
        if dep_eco_str != pkg_ecosystem:
            return dep_eco_str
    if dep_eco != pkg_ecosystem:
        return dep_eco
    return pkg_ecosystem


def _build_dep_pkg(
    dep: Any,
    dep_ecosystem_val: str,
    dep_info: dict,
    system_info: dict | None = None,
    include_optional: bool = False,
) -> dict | None:
    dep_resolver_input = _aggregator_to_resolver_input(
        dep_info, dep_ecosystem_val, system_info=system_info, include_optional=include_optional
    )
    dep_avail = dep_resolver_input.get("available_versions", [])
    if not dep_avail:
        return None
    dep_pkg: dict = {
        "name": dep.name,
        "ecosystem": dep_ecosystem_val,
        "available_versions": dep_avail,
        "version_requires_python": dep_resolver_input.get("version_requires_python", {}),
        "version_platforms": dep_resolver_input.get("version_platforms", {}),
        "dependencies": {},
        "system_requirements": {},
        "cross_ecosystem_deps": dep_resolver_input.get("cross_ecosystem_deps", []),
    }
    dep_deps_all = dep_info.get("dependencies", {})
    for d_eco, d_data in dep_deps_all.items():
        filtered = []
        for d in d_data.get("all", []):
            if not include_optional:
                if getattr(d, "dev_only", False):
                    continue
                if getattr(d, "optional", False):
                    continue
            if PEER_DEP_MODE == "advisory" and getattr(d, "peer", False):
                continue
            marker = getattr(d, "marker", None)
            if marker and not evaluate_marker_string(marker, system_info):
                continue
            filtered.append(d)
        dep_pkg["dependencies"][d_eco] = {
            d.name: normalize_constraint(d.version_spec, d_eco) for d in filtered
        }
    dep_reqs_all = dep_info.get("system_requirements", {})
    for req_list in dep_reqs_all.values():
        for req in req_list:
            if req.type == "runtime" and req.version_spec:
                dep_pkg["system_requirements"][req.name] = {
                    "min_version": req.version_spec.lstrip(">= "),
                }
            elif req.type == "os" and req.name:
                dep_pkg["system_requirements"].setdefault("os", []).append(req.name)
            elif req.type == "arch" and req.name:
                dep_pkg["system_requirements"].setdefault("arch", []).append(req.name)
    return dep_pkg


def _add_cross_eco_edge(
    all_packages: dict,
    dep_key: tuple,
    dep: Any,
    pkg_name: str,
    pkg_ecosystem: str,
    dep_ecosystem_val: str,
) -> None:
    existing = all_packages.get(dep_key)
    if not existing:
        return
    existing.setdefault("cross_ecosystem_deps", [])
    source_tag = f"{pkg_name}@{pkg_ecosystem}"
    if any(x.get("source") == source_tag for x in existing["cross_ecosystem_deps"]):
        return
    dep_constraint = (
        normalize_constraint(dep.version_spec, dep_ecosystem_val)
        if hasattr(dep, "version_spec")
        else "*"
    )
    existing["cross_ecosystem_deps"].append(
        {
            "source": source_tag,
            "name": dep.name,
            "target_ecosystem": dep_ecosystem_val,
            "constraint": dep_constraint,
        }
    )


def _collect_locked_transitive_deps(
    locked_pkgs: dict,
    root_name: str,
    root_eco: str,
) -> dict[tuple[str, str], str]:
    """Walk the lock file's depends_on graph to collect all transitive deps of a root package."""
    collected: dict[tuple[str, str], str] = {}
    queue = [root_name]
    visited_lock = {root_name}
    while queue:
        pname = queue.pop(0)
        entry = locked_pkgs.get(pname, {})
        pkey = (pname, entry.get("ecosystem", root_eco))
        ver = entry.get("resolved_version") or entry.get("version", "")
        if ver:
            collected[pkey] = ver
        for dep_name in entry.get("depends_on", {}):
            if dep_name not in visited_lock and dep_name in locked_pkgs:
                visited_lock.add(dep_name)
                queue.append(dep_name)
    return collected


def _system_info_fingerprint(system_info: dict | None) -> dict:
    """Extract only deterministic fields from system_info for hash computation.

    Returns a filtered dict containing only ``os``, ``arch``, ``cuda_version``,
    and ``python_version``.  Non-deterministic fields like ``memory``,
    ``disks``, and ``hostname`` are excluded so that the resolution hash
    is stable across runs.
    """
    if not system_info:
        return {}
    result: dict = {}
    plat = system_info.get("platform", {})
    if plat.get("system"):
        result.setdefault("platform", {})["system"] = plat["system"]
    arch = plat.get("architecture") or system_info.get("cpu", {}).get("arch")
    if arch:
        result.setdefault("platform", {})["architecture"] = arch
    gpu = system_info.get("gpu", {})
    if not isinstance(gpu, dict):
        gpu = {}
    gpu_subset: dict[str, str] = {}
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
            gpu_subset[gpu_type] = ver
    if gpu_subset:
        result["gpu"] = gpu_subset
    rt = system_info.get("runtime_versions", {})
    py = rt.get("python", {})
    if py and py.get("version"):
        result["runtime_versions"] = {"python": {"version": py["version"]}}
    return result


def _check_dep_hash(
    dep_name: str,
    dep_eco: str,
    lock_data: dict | None,
    system_info: dict | None,
) -> str | None:
    """If *dep_name* in *lock_data* has a matching resolution_hash, return its locked version."""
    if not lock_data:
        return None
    locked_pkgs = lock_data.get("packages", {})
    entry = locked_pkgs.get(dep_name)
    if not entry:
        return None
    stored_hash = entry.get("resolution_hash", "")
    if not stored_hash:
        return None
    deps_by_eco: dict[str, dict[str, str]] = {}
    for d_name, d_constraint in entry.get("depends_on", {}).items():
        d_entry = locked_pkgs.get(d_name, {})
        d_eco = d_entry.get("ecosystem")
        if d_eco:
            deps_by_eco.setdefault(d_eco, {})[d_name] = d_constraint
    from backend.core.conflict_resolver import ConflictResolver

    fingerprint = _system_info_fingerprint(system_info)
    norm_constraint = normalize_constraint(
        entry.get("original_constraint", "*"),
        entry.get("ecosystem", dep_eco),
    )
    current_hash = ConflictResolver.compute_resolution_hash(
        dep_name,
        entry.get("ecosystem", dep_eco),
        norm_constraint,
        deps_by_eco,
        fingerprint,
    )
    if stored_hash == current_hash:
        return entry.get("resolved_version") or entry.get("version", "")
    return None


def _group_by_ecosystem(packages: list[dict]) -> dict[str, list[dict]]:
    """Group packages by ecosystem for per-ecosystem solver isolation.

    Packages whose dependency graph is entirely within a single ecosystem
    are grouped by ecosystem for independent resolution.  Packages that
    participate in cross-ecosystem dependencies — along with ALL packages
    from their ecosystem (to keep the dependency graph consistent) — go
    into a special ``"__cross__"`` group resolved by the original single-solver
    code path.

    This prevents a conflict in one ecosystem from blocking resolution in
    another, while ensuring cross-ecosystem packages still have access to
    all same-ecosystem dependencies they need.
    """
    # First pass: identify ecosystems with any cross-eco package
    eco_has_cross: dict[str, bool] = {}
    for pkg in packages:
        eco = pkg.get("ecosystem", "unknown")
        deps = pkg.get("dependencies", {})
        cross_deps = pkg.get("cross_ecosystem_deps", [])
        has_cross = bool(cross_deps) or any(k != eco for k in deps)
        if has_cross:
            eco_has_cross[eco] = True

    # Second pass: group packages
    groups: dict[str, list[dict]] = {}
    for pkg in packages:
        eco = pkg.get("ecosystem", "unknown")
        if eco_has_cross.get(eco):
            groups.setdefault("__cross__", []).append(pkg)
        else:
            groups.setdefault(eco, []).append(pkg)
    return groups


def _merge_solver_results(results: list[dict]) -> dict:
    """Merge multiple solver result dicts into one.

    Handles ``resolved_packages`` merging, status propagation
    (order: unsatisfiable > partial > satisfiable), and best-effort
    collection of other metadata keys.
    """
    merged: dict = {"status": "satisfiable", "resolved_packages": {}}
    for res in results:
        status = res.get("status", "satisfiable")
        if status == "unsatisfiable":
            merged["status"] = "unsatisfiable"
            merged["resolution_error"] = res.get(
                "resolution_error", "One or more ecosystem groups are unsatisfiable"
            )
        elif status == "partial" and merged["status"] != "unsatisfiable":
            merged["status"] = "partial"
            merged.setdefault(
                "resolution_error", "One or more ecosystem groups are partially resolved"
            )
        for key, val in res.items():
            if key == "resolved_packages":
                merged.setdefault("resolved_packages", {}).update(val)
            elif key == "status":
                continue
            elif key == "warnings":
                merged.setdefault("warnings", []).extend(val if isinstance(val, list) else [val])
            elif key == "dependency_tree":
                merged.setdefault("dependency_tree", {}).update(
                    val if isinstance(val, dict) else {}
                )
            elif key == "installation_order":
                merged.setdefault("installation_order", []).extend(
                    val if isinstance(val, list) else [val]
                )
            elif key not in merged:
                merged[key] = val
    return merged


async def _resolve_transitive(
    aggregator: Any,
    resolver: Any,
    packages: list[dict],
    system_info: dict,
    max_depth: int = 10,
    lock_data: dict | None = None,
    solver_timeout: int | None = None,
    lock_tree_data: dict[str, dict[str, dict]] | None = None,
    bfs_timeout: int | None = None,
    incremental: bool = True,
    cross_deps: list[dict] | None = None,
    include_optional: bool = False,
) -> dict:
    """Resolve packages with optional incremental resolution from existing lock data.

    When lock_data is provided, each root package's resolution hash is compared
    against the stored hash.  Packages whose hash hasn't changed are pinned to
    their locked version, skipping the SAT solver for them and their subtrees.
    Only packages whose resolution context changed go through the full BFS+SAT path.

    When lock_tree_data is provided (from e.g. package-lock.json), the BFS uses
    it to resolve transitive deps without making API calls for locked packages.
    Format: {ecosystem: {package_name: {version, dependencies: {dep_name: constraint}}}}

    Per-ecosystem solver isolation: packages whose dependency graph is entirely
    within a single ecosystem are resolved independently per ecosystem.  Packages
    that participate in cross-ecosystem dependencies (along with all packages from
    their ecosystem) are grouped into a ``"__cross__"`` group that uses the
    original single-solver path.  This prevents a conflict in one ecosystem from
    blocking resolution in another.
    """
    from backend.core.conflict_resolver import ConflictResolver

    # Disable incremental resolution when the flag is False or the env var is False
    if not incremental or not INCREMENTAL_RESOLUTION:
        lock_data = None

    # Build a lookup: (name, ecosystem) -> {version, dependencies} from lock_tree_data
    lock_tree_lookup: dict[tuple[str, str], dict] = {}
    if lock_tree_data:
        for eco, pkgs in lock_tree_data.items():
            for name, info in pkgs.items():
                lock_tree_lookup[(name, eco)] = info

    # Pre-resolve unchanged packages from lock data
    pre_resolved: dict[tuple[str, str], str] = {}  # (name, ecosystem) -> version
    changed_packages: list[dict] = []

    if lock_data:
        locked_pkgs = lock_data.get("packages", {})
        fingerprint = _system_info_fingerprint(system_info)
        for pkg in packages:
            key = (pkg["name"], pkg["ecosystem"])
            locked_entry = locked_pkgs.get(pkg["name"], {})
            stored_hash = locked_entry.get("resolution_hash", "")
            norm_constraint = normalize_constraint(
                pkg.get("version_constraint", "*"),
                pkg["ecosystem"],
            )
            current_hash = ConflictResolver.compute_resolution_hash(
                pkg["name"],
                pkg["ecosystem"],
                norm_constraint,
                pkg.get("dependencies", {}),
                fingerprint,
            )
            if stored_hash and stored_hash == current_hash:
                locked_ver = locked_entry.get("resolved_version") or locked_entry.get("version", "")
                if locked_ver:
                    pre_resolved[key] = locked_ver
                    # Also pre-resolve all transitive deps of this root from the lock file
                    transitive_deps = _collect_locked_transitive_deps(
                        locked_pkgs, pkg["name"], pkg["ecosystem"]
                    )
                    # Verify every transitive dep has a resolution_hash before pre-resolving
                    transitive_valid = True
                    for dk in transitive_deps:
                        d_entry = locked_pkgs.get(dk[0], {})
                        if not d_entry.get("resolution_hash"):
                            transitive_valid = False
                            break
                    if transitive_valid:
                        for dep_key, dep_ver in transitive_deps.items():
                            if dep_key not in pre_resolved:
                                pre_resolved[dep_key] = dep_ver
                    else:
                        # Fall back: unchanged root, but transitive deps not fully validated
                        for dep_key in transitive_deps:
                            pre_resolved.pop(dep_key, None)
                        changed_packages.append(pkg)
                        continue
                    continue
            changed_packages.append(pkg)
    else:
        changed_packages = list(packages)

    if not changed_packages:
        # Everything is unchanged — return lock data as-is
        return (
            _lock_data_to_result(lock_data)
            if lock_data
            else {"status": "satisfiable", "resolved_packages": {}}
        )

    def _collect_current_deps(
        pkg: dict,
        visited: set,
        all_packages: dict,
        pre_resolved: dict,
        out_list: list[tuple],
        pkg_name: str,
        pkg_eco: str,
        include_optional: bool = False,
    ) -> None:
        """Extract dependency names from *pkg* and append (name, eco, source) tuples to *out_list*.
        Skips already visited, pre-resolved, or collected packages.
        """
        if not pkg:
            return
        deps_by_eco = pkg.get("dependencies", {})
        if not deps_by_eco and isinstance(pkg, dict) and "dependencies" not in pkg:
            return
        for dep_eco, dep_data in deps_by_eco.items():
            if isinstance(dep_data, dict) and "all" in dep_data:
                deps_iter: list = dep_data["all"]
            elif isinstance(dep_data, dict):
                deps_iter = [
                    type("_Dep", (), {"name": k, "version_spec": v, "ecosystem": dep_eco})()
                    for k, v in dep_data.items()
                ]
            else:
                continue
            for dep in deps_iter:
                if not include_optional and getattr(dep, "optional", False):
                    continue
                if PEER_DEP_MODE == "advisory" and getattr(dep, "peer", False):
                    continue
                dep_ecosystem_val = _determine_dep_ecosystem(dep, dep_eco, pkg_eco)
                key = (dep.name, dep_ecosystem_val)
                if key in visited or key in all_packages or key in pre_resolved:
                    continue
                out_list.append((dep.name, dep_ecosystem_val, dep))

    # BFS transitive resolution — level-by-level parallel batches
    # Phase 1: batch-fetch all root packages (not pre-resolved) in parallel.
    # Phase 2: level-by-level: collect deps → batch-fetch → recurse.
    visited: set = set()
    all_packages: dict = {}

    async def _fetch_one(item: tuple) -> tuple:
        name, eco = item[0], item[1]
        lk = lock_tree_lookup.get((name, eco))
        if lk is not None:
            deps: dict[str, list] = {"all": []}
            for dep_name, dep_ver in lk.get("dependencies", {}).items():
                deps["all"].append(
                    type(
                        "_Dep",
                        (),
                        {"name": dep_name, "version_spec": dep_ver, "ecosystem": eco},
                    )()
                )
            return (
                name,
                eco,
                {
                    "name": name,
                    "version": lk.get("version", "0.0.0"),
                    "versions": [{"version": lk.get("version", "0.0.0")}],
                    "dependencies": {eco: deps},
                    "_version_metadata": {},
                },
            )
        info = await _fetch_dep_info(aggregator, name, eco, include_extended=False)
        return (name, eco, info)

    async def _batch_fetch(
        items: list[tuple],
        batch_size: int,
    ) -> list[tuple]:
        """Fetch *items* in chunks of *batch_size*, gathering each chunk in parallel."""
        _tracer = get_tracer(__name__)
        with _tracer.start_as_current_span("resolve._batch_fetch") as _span:
            _span.set_attribute("total_items", len(items))
            _span.set_attribute("batch_size", batch_size)
            results: list[tuple] = []
            for i in range(0, len(items), batch_size):
                chunk = items[i : i + batch_size]
                chunk_results = await asyncio.gather(
                    *[_fetch_one(item) for item in chunk], return_exceptions=True
                )
                for r in chunk_results:
                    if isinstance(r, (list, tuple)) and len(r) > 2 and r[2] is not None:
                        results.append(r)
                    elif isinstance(r, BaseException):
                        logger.warning("Batch fetch failed: %s", r)
            _span.set_attribute("fetched_count", len(results))
            return results

    # Phase 1: batch-fetch root packages that aren't pre-resolved
    roots_to_fetch = [
        (p["name"], p["ecosystem"], p)
        for p in changed_packages
        if (p["name"], p["ecosystem"]) not in pre_resolved
    ]
    if roots_to_fetch:
        root_batch = [(n, e) for n, e, _ in roots_to_fetch]
        batch_sz = min(BFS_BATCH_SIZE, len(root_batch))
        fetched = await _batch_fetch(root_batch, batch_sz)
        for name, eco, info in fetched:
            key = (name, eco)
            if key in all_packages:
                continue
            visited.add(key)
            # find the original pkg dict
            pkg = next(p for n, e, p in roots_to_fetch if n == name and e == eco)
            all_packages[key] = pkg
            # cross-eco edges from root packages
            all_deps = info.get("dependencies", {})
            for dep_eco, dep_data in all_deps.items():
                for dep in dep_data.get("all", []):
                    if not include_optional:
                        if getattr(dep, "dev_only", False):
                            continue
                        if getattr(dep, "optional", False):
                            continue
                    if PEER_DEP_MODE == "advisory" and getattr(dep, "peer", False):
                        continue
                    dep_ecosystem_val = _determine_dep_ecosystem(dep, dep_eco, eco)
                    dep_key = (dep.name, dep_ecosystem_val)
                    if dep_ecosystem_val != eco:
                        _add_cross_eco_edge(
                            all_packages, dep_key, dep, name, eco, dep_ecosystem_val
                        )

    # Phase 2: level-by-level batch fetch of transitive deps
    current_level_deps: list[tuple] = []
    # Collect deps from root packages
    for (name, eco), pkg in list(all_packages.items()):
        _collect_current_deps(
            pkg,
            visited,
            all_packages,
            pre_resolved,
            current_level_deps,
            name,
            eco,
            include_optional=include_optional,
        )

    # Inject cross-ecosystem dependency edges from config (udr.json cross_deps)
    if cross_deps:
        for xdep in cross_deps:
            source_raw = xdep.get("from", "")
            if "@" not in source_raw:
                continue
            src_name, src_eco = source_raw.rsplit("@", 1)
            dep_name = xdep.get("dep", "")
            dep_eco = xdep.get("target_ecosystem", "")
            if "@" in dep_name:
                dep_name, dep_eco_from_dep = dep_name.rsplit("@", 1)
                if dep_eco_from_dep:
                    dep_eco = dep_eco_from_dep
            constraint = xdep.get("constraint", "*")
            src_key = (src_name, src_eco)
            dep_key = (dep_name, dep_eco)
            # Inject edge: if source is already fetched, add dep
            src_pkg = all_packages.get(src_key)
            if src_pkg:
                src_pkg.setdefault("dependencies", {}).setdefault(dep_eco, {})
                # Add dep in flat format for the SAT solver: {eco: {name: constraint}}
                src_pkg["dependencies"][dep_eco][dep_name] = constraint
                # Also add in _collect_current_deps "all" format for BFS traversal
                src_pkg["dependencies"][dep_eco].setdefault("all", [])
                src_pkg["dependencies"][dep_eco]["all"].append(
                    type(
                        "_Dep",
                        (),
                        {"name": dep_name, "version_spec": constraint, "ecosystem": dep_eco},
                    )()
                )
                # Mark as cross-eco edge
                _add_cross_eco_edge(
                    all_packages,
                    dep_key,
                    type(
                        "_Dep",
                        (),
                        {"name": dep_name, "version_spec": constraint, "ecosystem": dep_eco},
                    )(),
                    src_name,
                    src_eco,
                    dep_eco,
                )
            # Ensure target dep is in the BFS fetch queue if not already known
            if (
                dep_key not in visited
                and dep_key not in all_packages
                and dep_key not in pre_resolved
            ):
                current_level_deps.append((dep_name, dep_eco, None))

    if bfs_timeout is not None:
        bfs_deadline = asyncio.get_event_loop().time() + bfs_timeout
    else:
        bfs_deadline = None

    depth = 0
    while current_level_deps:
        depth += 1
        if depth > max_depth:
            logger.warning(
                "BFS max depth %d reached — continuing with %d packages fetched",
                max_depth,
                len(all_packages),
            )
            break
        if bfs_deadline is not None and asyncio.get_event_loop().time() >= bfs_deadline:
            logger.warning(
                "BFS timed out after %ds — continuing with %d packages fetched",
                bfs_timeout,
                len(all_packages),
            )
            break

        # Deduplicate by key — also check resolution hash for each dep
        seen = set()
        unique_deps = []
        for item in current_level_deps:
            key = (item[0], item[1])
            if key not in seen and key not in visited and key not in pre_resolved:
                seen.add(key)
                # Check if transitive dep can be pre-resolved from lock hash
                locked_ver = _check_dep_hash(item[0], item[1], lock_data, system_info)
                if locked_ver:
                    pre_resolved[key] = locked_ver
                    # Pre-resolve all transitive deps of this dep from lock data
                    if lock_data:
                        td = _collect_locked_transitive_deps(
                            lock_data.get("packages", {}), item[0], item[1]
                        )
                        # Verify every transitive dep has a resolution_hash
                        transitive_valid = True
                        for dk in td:
                            d_entry = lock_data.get("packages", {}).get(dk[0], {})
                            if not d_entry.get("resolution_hash"):
                                transitive_valid = False
                                break
                        if transitive_valid:
                            for dk, dv in td.items():
                                if dk not in pre_resolved:
                                    pre_resolved[dk] = dv
                        else:
                            # Missing hash — fall back to BFS for this chain
                            pre_resolved.pop(key, None)
                            unique_deps.append(item)
                else:
                    unique_deps.append(item)
        if not unique_deps:
            break

        # Batch-fetch this level
        fetch_items = [(n, e) for n, e, _source in unique_deps]
        batch_sz = min(BFS_BATCH_SIZE, len(fetch_items))
        fetched = await _batch_fetch(fetch_items, batch_sz)

        # Process fetched deps
        next_level_deps: list[tuple] = []
        for name, eco, info in fetched:
            key = (name, eco)
            if key in visited or key in all_packages or key in pre_resolved:
                continue
            visited.add(key)
            # Find the source info for this dep
            source_info = next((src for n, e, src in unique_deps if n == name and e == eco), None)
            dep_pkg = _build_dep_pkg(
                getattr(source_info, "_dep", source_info) if source_info else None,
                eco,
                info,
                system_info=system_info,
                include_optional=include_optional,
            )
            if dep_pkg and key not in all_packages:
                all_packages[key] = dep_pkg
            # Collect deps from this package for next level
            _collect_current_deps(
                dep_pkg or {},
                visited,
                all_packages,
                pre_resolved,
                next_level_deps,
                name,
                eco,
                include_optional=include_optional,
            )

        current_level_deps = next_level_deps

    # Pin any package with an exact version constraint (e.g. from lock files)
    # before sending to the SAT solver — avoids solver blow-up for huge lock files
    # like Gemfile.lock with 200+ packages.
    sat_packages = []
    for pkg in list(all_packages.values()):
        vc = (pkg.get("version_constraint") or "").strip()
        if vc.startswith("==") or re.match(r"^\d+\.", vc):
            ver = vc.lstrip("= ").strip()
            key = (pkg["name"], pkg["ecosystem"])
            if ver and key not in pre_resolved:
                pre_resolved[key] = ver
        else:
            sat_packages.append(pkg)

    # Pre-check: total version capacity before solver
    if sat_packages:
        total_versions = sum(len(p.get("available_versions", []) or []) for p in sat_packages)
        if total_versions > SOLVER_MAX_VARIABLES:
            logger.warning(
                "Too many versions (%d) — exceeds SOLVER_MAX_VARIABLES (%d), "
                "falling back to pre-resolved packages only",
                total_versions,
                SOLVER_MAX_VARIABLES,
            )
            # Return with whatever was pre-resolved from lock data
            result = {"status": "partial", "resolved_packages": {}}
            if pre_resolved:
                for (name, eco), version in pre_resolved.items():
                    result["resolved_packages"][name] = {
                        "version": version,
                        "ecosystem": eco,
                    }
                result["error"] = (
                    f"Too many versions ({total_versions}) — "
                    f"exceeds SOLVER_MAX_VARIABLES ({SOLVER_MAX_VARIABLES}). "
                    f"Using {len(pre_resolved)} pre-resolved packages from lock file."
                )
            else:
                result["error"] = (
                    f"Too many versions ({total_versions}) — "
                    f"exceeds SOLVER_MAX_VARIABLES ({SOLVER_MAX_VARIABLES})"
                )
            return result

    # Resolve with SAT solver — per-ecosystem isolation
    if sat_packages:
        groups = _group_by_ecosystem(sat_packages)

        # Use the original single-solver path when:
        #   - There's a cross-ecosystem group, or
        #   - Only one ecosystem group exists (no isolation benefit)
        if "__cross__" in groups or len(groups) <= 1:
            logger.debug(
                "Single-solver path: %d groups, cross=%s",
                len(groups),
                "__cross__" in groups,
            )
            result = resolver.resolve_dependencies(
                sat_packages,
                system_info,
                prefer_compatibility=True,
                solver_timeout=solver_timeout,
            )
            if "packages" in result and "resolved_packages" not in result:
                result["resolved_packages"] = result.pop("packages")
        else:
            logger.info(
                "Per-ecosystem solver isolation: %d groups (%s)",
                len(groups),
                ", ".join(sorted(groups.keys())),
            )
            results: list[dict] = []
            for eco, eco_pkgs in sorted(groups.items()):
                if not eco_pkgs:
                    continue
                logger.debug("Resolving ecosystem group '%s' (%d packages)", eco, len(eco_pkgs))
                eco_result = resolver.resolve_dependencies(
                    eco_pkgs,
                    system_info,
                    prefer_compatibility=True,
                    solver_timeout=solver_timeout,
                )
                if "packages" in eco_result and "resolved_packages" not in eco_result:
                    eco_result["resolved_packages"] = eco_result.pop("packages")
                results.append(eco_result)

                if eco_result.get("status") == "unsatisfiable":
                    logger.warning("Ecosystem '%s' is unsatisfiable — skipping remaining", eco)
                    continue

            result = _merge_solver_results(results)
    else:
        result = {"status": "satisfiable", "resolved_packages": {}}

    # Merge pre-resolved (unchanged) packages into result
    if pre_resolved:
        for (name, eco), version in pre_resolved.items():
            if name not in result.get("resolved_packages", {}):
                result.setdefault("resolved_packages", {})[name] = {
                    "version": version,
                    "ecosystem": eco,
                }

    return result


def _lock_data_to_result(lock_data: dict) -> dict:
    """Convert existing lock data to a resolution result dict."""
    pkgs = {}
    for name, info in lock_data.get("packages", {}).items():
        ver = info.get("resolved_version") or info.get("version", "")
        if ver:
            pkgs[name] = {
                "version": ver,
                "ecosystem": info.get("ecosystem", "unknown"),
            }
    return {
        "status": "satisfiable",
        "resolved_packages": pkgs,
        "dependency_tree": {},
        "warnings": [],
        "installation_order": list(pkgs.keys()),
    }


def _extract_cuda_variants(versions_info: list[dict], base_version: str) -> list[dict]:
    pattern = re.compile(rf"^{re.escape(base_version)}\+cu(\d+)")
    variants = []
    for vinfo in versions_info:
        ver = vinfo.get("version", "") if isinstance(vinfo, dict) else str(vinfo)
        match = pattern.match(ver)
        if match:
            variants.append({"version": ver, "cuda_version": match.group(1)})
    return variants


def _normalize_cuda(cuda_str: str) -> int:
    cleaned = cuda_str.replace(".", "").lstrip("cu")
    try:
        return int(cleaned)
    except (ValueError, IndexError):
        return 0


def _select_best_cuda_variant(
    variants: list[dict],
    system_cuda: str | None,
) -> str | None:
    if not variants:
        return None
    if not system_cuda:
        return variants[0]["version"]
    sys_norm = _normalize_cuda(system_cuda)
    for v in variants:
        if _normalize_cuda(v["cuda_version"]) == sys_norm:
            return v["version"]
    compatible = [v for v in variants if _normalize_cuda(v["cuda_version"]) <= sys_norm]
    if compatible:
        compatible.sort(key=lambda x: _normalize_cuda(x["cuda_version"]), reverse=True)
        return compatible[0]["version"]
    return variants[0]["version"]


def _apply_cuda_variants(
    resolved: dict,
    package_details: dict[str, dict],
    system_info: dict,
) -> dict:
    resolved_pkgs = resolved.get("resolved_packages", {})
    system_cuda = None
    if system_info and "gpu" in system_info:
        system_cuda = system_info["gpu"].get("cuda")
    has_cuda_variants = False
    for pkg_name, pkg_info in resolved_pkgs.items():
        if pkg_info.get("ecosystem") != "pypi":
            continue
        base_version = pkg_info.get("version", "")
        if not base_version:
            continue
        details = package_details.get(pkg_name, {})
        versions_data = details.get("versions", {})
        if isinstance(versions_data, list):
            raw_versions = versions_data
        else:
            raw_versions = versions_data.get("pypi", [])
            if not raw_versions:
                raw_versions = versions_data.get(pkg_info.get("ecosystem", ""), [])
        cuda_variants = _extract_cuda_variants(raw_versions, base_version)
        if cuda_variants:
            has_cuda_variants = True
            if not system_cuda:
                logger.info("CUDA variant available for %s but no GPU detected", pkg_name)
                continue
            best = _select_best_cuda_variant(cuda_variants, system_cuda)
            if best and best != base_version:
                resolved_pkgs[pkg_name]["version"] = best
                resolved_pkgs[pkg_name]["cuda_variant"] = True
                resolved_pkgs[pkg_name]["cuda_version"] = next(
                    (v["cuda_version"] for v in cuda_variants if v["version"] == best),
                    None,
                )
    if has_cuda_variants and not system_cuda:
        logger.info("CUDA variants exist but were not selected — resolution is CPU-only")
    if resolved_pkgs:
        resolved["resolved_packages"] = resolved_pkgs
    return resolved
