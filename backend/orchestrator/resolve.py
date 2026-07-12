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
from backend.settings import BFS_BATCH_SIZE, USE_HYBRID_SOLVER, USE_PUBGRUB_SOLVER
from backend.settings import ECOSYSTEMS as _SETTINGS_ECOSYSTEMS

_VALID_ECOSYSTEMS = {e for e in _SETTINGS_ECOSYSTEMS if e not in ("docs", "custom_db")}

logger = logging.getLogger(__name__)


def create_solver(*, use_optimization: bool = True, solver_timeout: int | None = None) -> Any:
    """Create a solver instance based on USE_PUBGRUB_SOLVER / USE_HYBRID_SOLVER settings.

    Priority: USE_HYBRID_SOLVER > USE_PUBGRUB_SOLVER > ConflictResolver (Z3 default).
    """
    if USE_HYBRID_SOLVER:
        try:
            from backend.core.hybrid_solver import HybridSolver

            logger.info("Using HybridSolver (PubGrub per-ecosystem + Z3 cross-eco)")
            return HybridSolver(
                use_optimization=use_optimization,
                solver_timeout=solver_timeout,
            )
        except ImportError:
            logger.warning(
                "USE_HYBRID_SOLVER is true but hybrid_solver module not available; "
                "falling back to Z3 ConflictResolver"
            )

    if USE_PUBGRUB_SOLVER:
        try:
            # Check that pubgrub-py is actually importable (not just the wrapper class)
            from pubgrub_py import Resolver as _PubGrubResolver  # noqa: F401

            from backend.core.pubgrub_solver import PubGrubSolver

            logger.info("Using PubGrub solver")
            return PubGrubSolver(
                use_optimization=use_optimization,
                solver_timeout=solver_timeout,
            )
        except ImportError:
            logger.warning(
                "USE_PUBGRUB_SOLVER is true but pubgrub-py is not installed; "
                "falling back to Z3 ConflictResolver"
            )
    from backend.core.conflict_resolver import ConflictResolver

    return ConflictResolver(
        use_optimization=use_optimization,
    )


def _safe_version_key(v: str, ecosystem: str) -> _pkg_version.Version:
    try:
        return _pkg_version.parse(v)
    except Exception:
        try:
            return _pkg_version.parse(normalize_version(v, ecosystem))
        except Exception:
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
    for req in eco_reqs:
        if req.type == "runtime" and req.name == runtime_field and req.version_spec:
            min_ver = req.version_spec.lstrip(">= ")
            sys_reqs[runtime_field] = {"min_version": min_ver}
    eco_data = agg_data.get("ecosystem", {}).get(ecosystem, {})
    cuda_req = eco_data.get("system_requirements", {}).get("cuda")
    if cuda_req:
        sys_reqs["cuda"] = cuda_req
    return sys_reqs


def _aggregator_to_resolver_input(
    agg_data: dict,
    ecosystem: str,
    constraint: str | None = None,
    extras: list[str] | None = None,
) -> dict:
    available_versions = []
    raw_versions = agg_data.get("versions", {}).get(ecosystem, [])
    for vinfo in raw_versions:
        ver = vinfo.get("version", "") if isinstance(vinfo, dict) else str(vinfo)
        # Handle nested version objects (e.g. CocoaPods: {"version": {"name": "1.0.0", ...}})
        if isinstance(ver, dict):
            ver = ver.get("name", "") if isinstance(ver, dict) else str(ver)
        if isinstance(ver, str) and not re.search(r"\+cu\d", ver):
            yanked = vinfo.get("yanked", False) if isinstance(vinfo, dict) else False
            deprecated = vinfo.get("deprecated", False) if isinstance(vinfo, dict) else False
            if not yanked and not deprecated:
                available_versions.append(ver)
    deps = {}
    eco_deps = agg_data.get("dependencies", {})
    eco_deps = {} if isinstance(eco_deps, list) else eco_deps.get(ecosystem, {})
    for dep in eco_deps.get("all", []):
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
    return {
        "name": agg_data.get("name"),
        "ecosystem": ecosystem,
        "version_constraint": norm_constraint,
        "available_versions": sorted_versions,
        "dependencies": {ecosystem: deps},
        "system_requirements": sys_reqs,
        "cross_ecosystem_deps": agg_data.get("cross_ecosystem_deps", []),
    }


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
    if dep_ecosystem:
        return dep_ecosystem.value if hasattr(dep_ecosystem, "value") else str(dep_ecosystem)
    if dep_eco != pkg_ecosystem:
        return dep_eco
    return pkg_ecosystem


def _build_dep_pkg(
    dep: Any,
    dep_ecosystem_val: str,
    dep_info: dict,
    pkg_ecosystem: str,
    pkg_name: str,
) -> dict | None:
    dep_avail = _aggregator_to_resolver_input(dep_info, dep_ecosystem_val).get(
        "available_versions", []
    )
    if not dep_avail:
        return None
    dep_pkg: dict = {
        "name": dep.name,
        "ecosystem": dep_ecosystem_val,
        "available_versions": dep_avail,
        "dependencies": {},
        "system_requirements": {},
    }
    dep_deps_all = dep_info.get("dependencies", {})
    for d_eco, d_data in dep_deps_all.items():
        dep_pkg["dependencies"][d_eco] = {
            d.name: normalize_constraint(d.version_spec, d_eco) for d in d_data.get("all", [])
        }
    dep_reqs_all = dep_info.get("system_requirements", {})
    for req_list in dep_reqs_all.values():
        for req in req_list:
            if req.type == "runtime" and req.version_spec:
                dep_pkg["system_requirements"][req.name] = {
                    "min_version": req.version_spec.lstrip(">= "),
                }
    dep_constraint = (
        normalize_constraint(dep.version_spec, dep_ecosystem_val)
        if hasattr(dep, "version_spec")
        else "*"
    )
    if dep_ecosystem_val != pkg_ecosystem:
        dep_pkg.setdefault("cross_ecosystem_deps", []).append(
            {
                "source": f"{pkg_name}@{pkg_ecosystem}",
                "name": dep.name,
                "target_ecosystem": dep_ecosystem_val,
                "constraint": dep_constraint,
            }
        )
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

    current_hash = ConflictResolver.compute_resolution_hash(
        dep_name,
        entry.get("ecosystem", dep_eco),
        entry.get("original_constraint", "*"),
        deps_by_eco,
        system_info,
    )
    if stored_hash == current_hash:
        return entry.get("resolved_version") or entry.get("version", "")
    return None


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
) -> dict:
    """Resolve packages with optional incremental resolution from existing lock data.

    When lock_data is provided, each root package's resolution hash is compared
    against the stored hash.  Packages whose hash hasn't changed are pinned to
    their locked version, skipping the SAT solver for them and their subtrees.
    Only packages whose resolution context changed go through the full BFS+SAT path.

    When lock_tree_data is provided (from e.g. package-lock.json), the BFS uses
    it to resolve transitive deps without making API calls for locked packages.
    Format: {ecosystem: {package_name: {version, dependencies: {dep_name: constraint}}}}
    """
    from backend.core.conflict_resolver import ConflictResolver

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
        for pkg in packages:
            key = (pkg["name"], pkg["ecosystem"])
            locked_entry = locked_pkgs.get(pkg["name"], {})
            stored_hash = locked_entry.get("resolution_hash", "")
            current_hash = ConflictResolver.compute_resolution_hash(
                pkg["name"],
                pkg["ecosystem"],
                pkg.get("version_constraint", "*"),
                pkg.get("dependencies", {}),
                system_info,
            )
            if stored_hash and stored_hash == current_hash:
                locked_ver = locked_entry.get("resolved_version") or locked_entry.get("version", "")
                if locked_ver:
                    pre_resolved[key] = locked_ver
                    # Also pre-resolve all transitive deps of this root from the lock file
                    transitive_deps = _collect_locked_transitive_deps(
                        locked_pkgs, pkg["name"], pkg["ecosystem"]
                    )
                    for dep_key, dep_ver in transitive_deps.items():
                        if dep_key not in pre_resolved:
                            pre_resolved[dep_key] = dep_ver
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
            for dep in dep_data.get("all", []):
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

    async def _batch_fetch(
        items: list[tuple],
        batch_size: int,
    ) -> list[tuple]:
        """Fetch *items* in parallel batches, each batch limited by batch_size semaphore."""
        results: list[tuple] = []
        sem = asyncio.Semaphore(batch_size)

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
                    },
                )
            async with sem:
                info = await _fetch_dep_info(aggregator, name, eco, include_extended=False)
            return (name, eco, info)

        batch_results = await asyncio.gather(*[_fetch_one(item) for item in items])
        for r in batch_results:
            if r[2] is not None:
                results.append(r)
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
            pkg, visited, all_packages, pre_resolved, current_level_deps, name, eco
        )

    if bfs_timeout is not None:
        bfs_deadline = asyncio.get_event_loop().time() + bfs_timeout
    else:
        bfs_deadline = None

    while current_level_deps:
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
                        for dk, dv in td.items():
                            if dk not in pre_resolved:
                                pre_resolved[dk] = dv
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
                eco,  # _source_eco
                name,  # _source_name
            )
            if dep_pkg and key not in all_packages:
                all_packages[key] = dep_pkg
            # Collect deps from this package for next level
            _collect_current_deps(
                dep_pkg or {}, visited, all_packages, pre_resolved, next_level_deps, name, eco
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

    # Resolve with SAT solver for remaining packages
    if sat_packages:
        result = resolver.resolve_dependencies(
            sat_packages, system_info, prefer_compatibility=True, solver_timeout=solver_timeout
        )
        if "packages" in result and "resolved_packages" not in result:
            result["resolved_packages"] = result.pop("packages")
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
