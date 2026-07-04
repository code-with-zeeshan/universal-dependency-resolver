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
from backend.settings import ECOSYSTEMS as _SETTINGS_ECOSYSTEMS

_VALID_ECOSYSTEMS = {e for e in _SETTINGS_ECOSYSTEMS if e not in ("docs", "custom_db")}

logger = logging.getLogger(__name__)


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
) -> dict:
    available_versions = []
    raw_versions = agg_data.get("versions", {}).get(ecosystem, [])
    for vinfo in raw_versions:
        ver = vinfo.get("version", "") if isinstance(vinfo, dict) else str(vinfo)
        if not re.search(r"\+cu\d", ver):
            yanked = vinfo.get("yanked", False) if isinstance(vinfo, dict) else False
            deprecated = vinfo.get("deprecated", False) if isinstance(vinfo, dict) else False
            if not yanked and not deprecated:
                available_versions.append(ver)
    deps = {}
    eco_deps = agg_data.get("dependencies", {}).get(ecosystem, {})
    for dep in eco_deps.get("all", []):
        deps[dep.name] = normalize_constraint(dep.version_spec, ecosystem)
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
) -> dict | None:
    try:
        return await aggregator.get_package_info(
            name,
            ecosystem=ecosystem,
            include_dependencies=True,
            include_versions=True,
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


async def _resolve_transitive(
    aggregator: Any,
    resolver: Any,
    packages: list[dict],
    system_info: dict,
    max_depth: int = 10,
) -> dict:
    visited = set()
    queue = list(packages)
    all_packages: dict = {}
    depth = 0
    sem = asyncio.Semaphore(3)

    async def _fetch_with_sem(name: str, ecosystem: str) -> dict | None:
        async with sem:
            return await _fetch_dep_info(aggregator, name, ecosystem)

    while queue and depth <= max_depth:
        depth += 1
        next_round = []
        for pkg in queue:
            key = (pkg["name"], pkg["ecosystem"])
            if key in visited:
                continue
            visited.add(key)
            if key not in all_packages:
                all_packages[key] = pkg
            info = await _fetch_with_sem(pkg["name"], pkg["ecosystem"])
            if not info:
                continue
            all_deps = info.get("dependencies", {})
            dep_fetches = []
            for dep_eco, dep_data in all_deps.items():
                for dep in dep_data.get("all", []):
                    dep_ecosystem_val = _determine_dep_ecosystem(dep, dep_eco, pkg["ecosystem"])
                    dep_key = (dep.name, dep_ecosystem_val)
                    if dep_key not in visited and dep_key not in all_packages:
                        dep_fetches.append((dep, dep_ecosystem_val, dep_key, pkg))
                    if dep_ecosystem_val != pkg["ecosystem"]:
                        _add_cross_eco_edge(
                            all_packages,
                            dep_key,
                            dep,
                            pkg["name"],
                            pkg["ecosystem"],
                            dep_ecosystem_val,
                        )
            dep_info_results = await asyncio.gather(
                *[_fetch_with_sem(d.name, d_eco) for d, d_eco, _, _ in dep_fetches],
                return_exceptions=True,
            )
            for (dep, dep_ecosystem_val, dep_key, source_pkg), dep_info in zip(
                dep_fetches, dep_info_results
            ):
                if isinstance(dep_info, Exception) or not dep_info:
                    continue
                dep_pkg = _build_dep_pkg(
                    dep, dep_ecosystem_val, dep_info, source_pkg["ecosystem"], source_pkg["name"]
                )
                if dep_pkg:
                    all_packages[dep_key] = dep_pkg
                    next_round.append(dep_pkg)
        queue = next_round
    pkg_list = list(all_packages.values())
    result = resolver.resolve_dependencies(pkg_list, system_info, prefer_compatibility=True)
    if "packages" in result and "resolved_packages" not in result:
        result["resolved_packages"] = result.pop("packages")
    return result


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
        raw_versions = details.get("versions", {}).get("pypi", [])
        if not raw_versions:
            raw_versions = details.get("versions", {}).get(pkg_info.get("ecosystem", ""), [])
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
