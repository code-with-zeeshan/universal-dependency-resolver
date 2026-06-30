# backend/api/routes/lock.py
import asyncio
import logging
import os
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.core.data_aggregator import DataAggregator
from backend.core.conflict_resolver import ConflictResolver
from backend.core.system_scanner import SystemScanner
from backend.api.auth import get_current_user
from backend.api.dependencies import get_data_aggregator
from backend.cli import (
    _aggregator_to_resolver_input,
    _resolve_transitive,
    _apply_cuda_variants,
    _parse_package_spec,
)
from backend.cli.shared import _generate_install_command

SOLVER_API_TIMEOUT = int(os.environ.get("SOLVER_API_TIMEOUT", "60"))

logger = logging.getLogger(__name__)
router = APIRouter()


class VerifyRequest(BaseModel):
    lock_data: Dict[str, Any]


class GraphRequest(BaseModel):
    packages: List[str]
    ecosystem: str = "pypi"


class UpdateRequest(BaseModel):
    lock_data: Dict[str, Any]
    package: str
    ecosystem: Optional[str] = None


class GenerateLockRequest(BaseModel):
    packages: List[Dict[str, Any]]
    manifests: List[Dict[str, Any]] = []
    system: Optional[Dict[str, Any]] = None
    resolution: Optional[Dict[str, Any]] = None


class InstallCommandsRequest(BaseModel):
    lock_data: Dict[str, Any]


class RestoreRequest(BaseModel):
    lock_data: Dict[str, Any]


@router.post("/verify")
async def verify_lock(
    req: VerifyRequest,
    current_user=Depends(get_current_user),
):
    """Validate a lock file — check all resolved versions still exist.
    Mirrors `udr verify`."""
    aggregator = DataAggregator()
    lock_data = req.lock_data
    packages = lock_data.get("packages", {})

    if not packages:
        raise HTTPException(status_code=400, detail="No packages in lock data")

    issues = []
    ok_count = 0

    async def check_pkg(name: str, info: Dict) -> Optional[Dict]:
        eco = info.get("ecosystem", "pypi")
        ver = info.get("resolved_version")
        if not ver:
            return {"name": name, "issue": "No resolved version", "severity": "warning"}
        try:
            data = await aggregator.get_package_info(
                name, ecosystem=eco, include_versions=True
            )
            if data:
                versions = data.get("versions", {}).get(eco, [])
                version_strings = [
                    v.get("version", "") if isinstance(v, dict) else str(v)
                    for v in versions
                ]
                if ver not in version_strings:
                    return {
                        "name": name,
                        "issue": f"Version {ver} no longer available",
                        "severity": "error",
                    }
            else:
                return {
                    "name": name,
                    "issue": "Package not found on registry",
                    "severity": "error",
                }
        except Exception as exc:
            return {"name": name, "issue": str(exc), "severity": "error"}
        return None

    results = await asyncio.gather(*[check_pkg(n, i) for n, i in packages.items()])
    for result in results:
        if result:
            issues.append(result)
        else:
            ok_count += 1

    return {
        "status": "ok"
        if not any(i["severity"] == "error" for i in issues)
        else "issues",
        "total": len(packages),
        "ok": ok_count,
        "issues": issues,
    }


@router.post("/graph")
async def dependency_graph(
    req: GraphRequest,
    aggregator: DataAggregator = Depends(get_data_aggregator),
    current_user=Depends(get_current_user),
):
    """Get dependency tree for one or more packages.
    Mirrors `udr graph`."""
    resolver = ConflictResolver()
    specs = [_parse_package_spec(p, req.ecosystem) for p in req.packages]
    system_info = resolver._get_default_system_info()

    resolver_inputs = []
    package_details = {}

    for pkg_name, eco in specs:
        try:
            data = await aggregator.get_package_info(
                pkg_name,
                ecosystem=eco,
                include_dependencies=True,
                include_versions=True,
            )
            if data:
                package_details[pkg_name] = data
                resolver_inputs.append(_aggregator_to_resolver_input(data, eco))
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", pkg_name, e)

    if not resolver_inputs:
        raise HTTPException(status_code=404, detail="No packages could be resolved")

    try:
        resolved = await asyncio.wait_for(
            _resolve_transitive(aggregator, resolver, resolver_inputs, system_info),
            timeout=SOLVER_API_TIMEOUT,
        )
    except (asyncio.TimeoutError, Exception):
        resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)
    resolved = _apply_cuda_variants(resolved, package_details, system_info)
    rp = resolved.get("resolved_packages", {})

    def _build_tree(name: str, info: Dict) -> Dict:
        eco = info.get("ecosystem", "?")
        ver = info.get("version", "?")
        deps_list = []
        deps = info.get("dependencies", {}).get(eco, {})
        for dep_name, dep_ver in deps.items():
            dep_info = rp.get(dep_name, {})
            if dep_info:
                deps_list.append(_build_tree(dep_name, dep_info))
            else:
                deps_list.append(
                    {
                        "name": dep_name,
                        "version": dep_ver,
                        "ecosystem": eco,
                        "children": [],
                    }
                )
        return {"name": name, "version": ver, "ecosystem": eco, "children": deps_list}

    trees = [_build_tree(name, info) for name, info in rp.items()]

    return {
        "status": "success",
        "trees": trees,
    }


@router.post("/update")
async def update_package(
    req: UpdateRequest,
    current_user=Depends(get_current_user),
):
    """Re-resolve a single package and return updated lock data.
    Mirrors `udr update <package> --directory <path> --json`."""
    aggregator = DataAggregator()
    resolver = ConflictResolver()
    scanner = SystemScanner()

    lock_data = req.lock_data
    package_name = req.package
    packages_in_lock = lock_data.get("packages", {})
    if package_name not in packages_in_lock:
        raise HTTPException(
            status_code=404, detail=f"Package '{package_name}' not found in lock data"
        )

    pkg_info = packages_in_lock[package_name]
    ecosystem = req.ecosystem or pkg_info.get("ecosystem", "pypi")

    system_info = await scanner.scan_all()

    resolver_inputs = []
    package_details = {}

    try:
        data = await aggregator.get_package_info(
            package_name,
            ecosystem=ecosystem,
            include_dependencies=True,
            include_versions=True,
        )
        if data:
            package_details[package_name] = data
            resolver_inputs.append(_aggregator_to_resolver_input(data, ecosystem))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch {package_name}: {e}"
        )

    if not resolver_inputs:
        raise HTTPException(status_code=404, detail=f"No data found for {package_name}")

    try:
        resolved = await asyncio.wait_for(
            _resolve_transitive(aggregator, resolver, resolver_inputs, system_info),
            timeout=SOLVER_API_TIMEOUT,
        )
    except (asyncio.TimeoutError, Exception):
        resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)

    resolved = _apply_cuda_variants(resolved, package_details, system_info)
    rp = resolved.get("resolved_packages", {})
    new_version = rp.get(package_name, {}).get("version") if rp else None

    if not new_version:
        raise HTTPException(status_code=500, detail=f"Could not resolve {package_name}")

    old_version = pkg_info.get("resolved_version")

    lock_data["packages"][package_name] = {
        **pkg_info,
        "resolved_version": new_version,
        "cuda_variant": rp[package_name].get("cuda_variant", False),
        "cuda_version": rp[package_name].get("cuda_version"),
    }
    lock_data["generated_at"] = __import__("datetime").datetime.now().isoformat()

    return {
        "status": "success",
        "package": package_name,
        "old_version": old_version,
        "new_version": new_version,
        "updated": new_version != old_version,
        "lock_data": lock_data,
    }


@router.post("/generate-lock")
async def generate_lock(
    req: GenerateLockRequest,
    current_user=Depends(get_current_user),
):
    """Generate a udr-lock.json from scan result data.
    Mirrors `udr lock --json` output format."""
    packages_in = req.packages
    system = req.system or {}
    resolution = req.resolution or {}

    resolved_pkgs = resolution.get("resolved_packages", {})
    plat = system.get("platform", {})
    gpu_info = system.get("gpu", {})
    gpu_name = None
    if gpu_info.get("available"):
        devices = gpu_info.get("devices", [])
        if devices:
            gpu_name = devices[0].get("name")

    pkg_map = {}
    for p in packages_in:
        name = p["name"]
        rp = resolved_pkgs.get(name, {})
        pkg_map[name] = {
            "name": name,
            "ecosystem": p.get("ecosystem", "?"),
            "resolved_version": p.get("resolved_version") or rp.get("version"),
            "direct": True,
            "cuda_variant": p.get("cuda_variant") or rp.get("cuda_variant", False),
            "cuda_version": p.get("cuda_version") or rp.get("cuda_version"),
            "original_constraint": p.get("constraint", "*"),
            "source": p.get("source", "manifest"),
            "vulnerabilities": [],
        }

    for name, rp in resolved_pkgs.items():
        if name not in pkg_map:
            vulns: List[Dict] = []
            pkg_map[name] = {
                "name": name,
                "ecosystem": rp.get("ecosystem", "?"),
                "resolved_version": rp.get("version"),
                "direct": False,
                "cuda_variant": rp.get("cuda_variant", False),
                "cuda_version": rp.get("cuda_version"),
                "original_constraint": "*",
                "source": "transitive",
                "vulnerabilities": vulns,
            }

    lock_data = {
        "version": "2.0",
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "resolver": "sat",
        "system": {
            "os": f"{plat.get('system', '?')} {plat.get('release', '?')}",
            "python": system.get("runtime_versions", {})
            .get("python", {})
            .get("version", "?"),
            "cpu": system.get("cpu", {}).get("brand", "Unknown"),
            "gpu": gpu_name,
            "cuda": gpu_info.get("cuda") if gpu_info.get("available") else None,
        },
        "manifests": [m.get("filename", m.get("path", "?")) for m in req.manifests],
        "packages": pkg_map,
        "warnings": resolution.get("warnings", []),
    }

    return {"status": "success", "lock_data": lock_data}


@router.post("/install-commands")
async def install_commands(
    req: InstallCommandsRequest,
    current_user=Depends(get_current_user),
):
    """Generate native install commands grouped by ecosystem from lock data.
    Mirrors `udr install <package>` using locked versions."""
    lock_data = req.lock_data
    packages = lock_data.get("packages", {})
    ecosystem_groups: Dict[str, List[tuple]] = {}

    for name, info in packages.items():
        if not info.get("direct", True):
            continue
        eco = info.get("ecosystem", "pypi")
        ver = info.get("resolved_version")
        if ver:
            ecosystem_groups.setdefault(eco, []).append((name, ver))

    commands = []
    for eco, pkgs in sorted(ecosystem_groups.items()):
        cmd = _generate_install_command(eco, pkgs)
        if cmd:
            commands.append(
                {"ecosystem": eco, "command": cmd, "package_count": len(pkgs)}
            )

    return {
        "status": "success",
        "commands": commands,
        "total_packages": sum(g["package_count"] for g in commands),
    }


@router.post("/restore-commands")
async def restore_commands(
    req: RestoreRequest,
    current_user=Depends(get_current_user),
):
    """Generate install commands for ALL packages in lock data (direct + transitive).
    Mirrors `udr restore <lockfile>`."""
    lock_data = req.lock_data
    packages = lock_data.get("packages", {})
    ecosystem_groups: Dict[str, List[tuple]] = {}

    for name, info in packages.items():
        eco = info.get("ecosystem", "pypi")
        ver = info.get("resolved_version")
        if ver:
            ecosystem_groups.setdefault(eco, []).append((name, ver))

    commands = []
    for eco, pkgs in sorted(ecosystem_groups.items()):
        cmd = _generate_install_command(eco, pkgs)
        if cmd:
            commands.append(
                {"ecosystem": eco, "command": cmd, "package_count": len(pkgs)}
            )

    return {
        "status": "success",
        "commands": commands,
        "total_packages": sum(g["package_count"] for g in commands),
    }
