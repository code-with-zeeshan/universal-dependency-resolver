"""Module docstring."""

from __future__ import annotations

# backend/api/routes/lock.py
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator

from backend.api.auth import get_current_user
from backend.api.dependencies import get_data_aggregator
from backend.core.data_aggregator import DataAggregator
from backend.core.system_scanner import SystemScanner
from backend.manifest_detector import ManifestDetector
from backend.orchestrator import (
    _aggregator_to_resolver_input,
    _apply_cuda_variants,
    _parse_package_spec,
    _resolve_transitive,
    create_solver,
)
from backend.orchestrator.install import _generate_install_command
from backend.settings import SOLVER_API_TIMEOUT

logger = logging.getLogger(__name__)
router = APIRouter()


class VerifyRequest(BaseModel):
    """Verify Request functionality."""

    lock_data: dict[str, Any]


class GraphRequest(BaseModel):
    """Graph Request functionality."""

    packages: list[str]
    ecosystem: str = "pypi"


class UpdateRequest(BaseModel):
    """Update Request functionality."""

    lock_data: dict[str, Any]
    package: str
    ecosystem: str | None = None


class GenerateLockRequest(BaseModel):
    """Generate Lock Request functionality.

    Two modes:
    1. Pre-parsed mode (original): provide `packages`, `manifests`, `system`, `resolution`
    2. Manifest content mode (mirrors `udr lock`): provide `manifest_contents` with filename->content
       Optionally set `manifest_filter` to target a specific manifest file.
       Optionally set `system` to override auto-detected system info.
    """

    packages: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    system: dict[str, Any] | None = None
    resolution: dict[str, Any] | None = None
    manifest_contents: dict[str, str] | None = None
    manifest_filter: str | None = None

    @field_validator("manifest_contents")
    @classmethod
    def validate_manifest_contents(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is None:
            return v
        if len(v) > 50:
            raise ValueError("Too many manifest files (max 50)")
        for fname, content in v.items():
            if not isinstance(fname, str) or not isinstance(content, str):
                raise ValueError(f"Invalid manifest entry type for {fname}")
            if len(fname) > 200:
                raise ValueError(f"Manifest filename too long: {fname}")
            if len(content) > 10 * 1024 * 1024:
                raise ValueError(f"Manifest content too large: {fname}")
        return v


class WhyRequest(BaseModel):
    """Why Request — explain why a package version was selected."""

    lock_data: dict[str, Any]
    package: str


class OutdatedRequest(BaseModel):
    """Outdated Request — check for newer versions in registries."""

    lock_data: dict[str, Any]
    ecosystem: str | None = None


class DiffRequest(BaseModel):
    """Diff Request — compare two lock files."""

    lock_a: dict[str, Any]
    lock_b: dict[str, Any]


class InstallCommandsRequest(BaseModel):
    """Install Commands Request functionality."""

    lock_data: dict[str, Any]


class RestoreRequest(BaseModel):
    """Restore Request functionality."""

    lock_data: dict[str, Any]


@router.post("/verify")
async def verify_lock(
    req: VerifyRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Validate a lock file — check all resolved versions still exist.
    Mirrors `udr verify`.
    """
    aggregator = DataAggregator()
    lock_data = req.lock_data
    packages = lock_data.get("packages", {})

    if not packages:
        await aggregator.close()
        raise HTTPException(status_code=400, detail="No packages in lock data")

    issues = []
    ok_count = 0

    async def check_pkg(name: str, info: dict) -> dict | None:
        """Check pkg."""
        eco = info.get("ecosystem", "pypi")
        ver = info.get("resolved_version")
        if not ver:
            return {"name": name, "issue": "No resolved version", "severity": "warning"}
        try:
            data = await aggregator.get_package_info(name, ecosystem=eco, include_versions=True)
            if data:
                versions = data.get("versions", {}).get(eco, [])
                version_strings = [
                    v.get("version", "") if isinstance(v, dict) else str(v) for v in versions
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

    results = await asyncio.gather(
        *[check_pkg(n, i) for n, i in packages.items()], return_exceptions=True
    )
    for result in results:
        if isinstance(result, Exception):
            logger.debug("Outdated check failed for package: %s", result)
        elif result:
            issues.append(result)
        else:
            ok_count += 1

    try:
        return {
            "status": "ok" if not any(i["severity"] == "error" for i in issues) else "issues",
            "total": len(packages),
            "ok": ok_count,
            "issues": issues,
        }
    finally:
        await aggregator.close()


@router.post("/graph")
async def dependency_graph(
    req: GraphRequest,
    aggregator: DataAggregator = Depends(get_data_aggregator),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get dependency tree for one or more packages.
    Mirrors `udr graph`.
    """
    resolver = create_solver()
    specs = [_parse_package_spec(p, req.ecosystem) for p in req.packages]
    system_info = resolver._get_default_system_info()

    resolver_inputs = []
    package_details = {}

    for pkg_name, eco, _ in specs:
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
        bfs_budget = max(5, int(SOLVER_API_TIMEOUT * 0.5))
        solver_ms = max(10000, int((SOLVER_API_TIMEOUT - bfs_budget) * 1000))
        resolved = await asyncio.wait_for(
            _resolve_transitive(
                aggregator,
                resolver,
                resolver_inputs,
                system_info,
                solver_timeout=solver_ms,
                bfs_timeout=bfs_budget,
                cross_deps=None,
            ),
            timeout=SOLVER_API_TIMEOUT,
        )
    except (TimeoutError, Exception):
        resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)
    resolved = _apply_cuda_variants(resolved, package_details, system_info)
    rp = resolved.get("resolved_packages", {})

    def _build_tree(name: str, info: dict) -> dict:
        """Build tree."""
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
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Re-resolve a single package and return updated lock data.
    Mirrors `udr update <package> --directory <path> --json`.
    """
    aggregator = DataAggregator()
    resolver = create_solver()
    scanner = SystemScanner()
    try:
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
            raise HTTPException(status_code=500, detail=f"Failed to fetch {package_name}: {e}")

        if not resolver_inputs:
            raise HTTPException(status_code=404, detail=f"No data found for {package_name}")

        try:
            bfs_budget = max(5, int(SOLVER_API_TIMEOUT * 0.5))
            solver_ms = max(5000, int((SOLVER_API_TIMEOUT - bfs_budget) * 1000))
            resolved = await asyncio.wait_for(
                _resolve_transitive(
                    aggregator,
                    resolver,
                    resolver_inputs,
                    system_info,
                    solver_timeout=solver_ms,
                    bfs_timeout=bfs_budget,
                    cross_deps=None,
                ),
                timeout=SOLVER_API_TIMEOUT,
            )
        except (TimeoutError, Exception):
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
    finally:
        await aggregator.close()
        if hasattr(scanner, "close"):
            await scanner.close()


async def _run_lock_pipeline(
    manifest_contents: dict[str, str],
    manifest_filter: str | None = None,
    system_override: dict[str, Any] | None = None,
) -> dict:
    """Full pipeline: write manifests to temp dir, detect, parse, fetch, resolve, build lock data.
    Mirrors ``udr lock --json`` internally.
    """
    tmp = Path(tempfile.mkdtemp(prefix="udr_lock_"))
    try:
        for filename, content in manifest_contents.items():
            fp = tmp / filename
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)

        detector = ManifestDetector(str(tmp))
        aggregator = DataAggregator()
        resolver = create_solver()
        scanner = SystemScanner()

        manifests = detector.detect()
        if not manifests:
            return {"status": "no_manifests", "lock_data": None}

        if manifest_filter:
            target = manifest_filter.replace("\\", "/")
            manifests = [
                m
                for m in manifests
                if m["filename"] == target or m["path"].replace("\\", "/").endswith("/" + target)
            ]
            if not manifests:
                return {"status": "manifest_filter_no_match", "lock_data": None}

        packages = detector.normalize(detector.parse_all(manifests))
        if not packages:
            return {"status": "no_packages", "lock_data": None}

        seen = set()
        resolver_inputs = []
        package_details = {}

        for pkg in packages:
            key = (pkg["name"], pkg["ecosystem"])
            if key in seen:
                continue
            seen.add(key)
            try:
                data = await aggregator.get_package_info(
                    pkg["name"],
                    ecosystem=pkg["ecosystem"],
                    include_dependencies=True,
                    include_versions=True,
                )
                if data:
                    package_details[pkg["name"]] = data
                    rinput = _aggregator_to_resolver_input(
                        data, pkg["ecosystem"], extras=pkg.get("extras")
                    )
                    resolver_inputs.append(rinput)
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", pkg["name"], e)

        if system_override:
            system_info = system_override
        else:
            system_info = await scanner.scan_all()

        try:
            bfs_budget = max(5, int(SOLVER_API_TIMEOUT * 0.5))
            solver_ms = max(10000, int((SOLVER_API_TIMEOUT - bfs_budget) * 1000))
            resolved = await asyncio.wait_for(
                _resolve_transitive(
                    aggregator,
                    resolver,
                    resolver_inputs,
                    system_info,
                    solver_timeout=solver_ms,
                    bfs_timeout=bfs_budget,
                    cross_deps=None,
                ),
                timeout=SOLVER_API_TIMEOUT,
            )
        except (TimeoutError, Exception):
            resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)

        resolved = _apply_cuda_variants(resolved, package_details, system_info)
        resolved_pkgs = resolved.get("resolved_packages", {})

        plat = system_info.get("platform", {})
        gpu_info = system_info.get("gpu", {})
        gpu_name = None
        if gpu_info.get("available"):
            devices = gpu_info.get("devices", [])
            if devices:
                gpu_name = devices[0].get("name")

        lock_data = {
            "version": "2.0",
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "resolver": "sat",
            "system": {
                "os": f"{plat.get('system', '?')} {plat.get('release', '?')}",
                "python": system_info.get("runtime_versions", {})
                .get("python", {})
                .get("version", "?"),
                "cpu": system_info.get("cpu", {}).get("brand", "Unknown"),
                "gpu": gpu_name,
                "cuda": gpu_info.get("cuda") if gpu_info.get("available") else None,
            },
            "manifests": [m["filename"] for m in manifests],
            "packages": {},
            "warnings": resolved.get("warnings", []),
        }

        manifest_pkg_info = {
            p["name"]: {
                "constraint": p.get("constraint", "*"),
                "source": p.get("source", "unknown"),
            }
            for p in packages
        }

        for pkg_name, rp in resolved_pkgs.items():
            minfo = manifest_pkg_info.get(pkg_name, {})
            is_direct = pkg_name in manifest_pkg_info
            pkg_detail = package_details.get(pkg_name, {})
            vulns = pkg_detail.get("security", {}).get("vulnerabilities", [])
            lock_data["packages"][pkg_name] = {
                "name": pkg_name,
                "ecosystem": rp.get("ecosystem", "?"),
                "resolved_version": rp.get("version"),
                "direct": is_direct,
                "cuda_variant": rp.get("cuda_variant", False),
                "cuda_version": rp.get("cuda_version"),
                "original_constraint": minfo.get("constraint", "*"),
                "source": minfo.get("source", "transitive"),
                "vulnerabilities": [
                    {
                        "id": v.get("id", ""),
                        "summary": v.get("summary", ""),
                        "severity": v.get("severity", "UNKNOWN"),
                        "fixed_version": v.get("fixed_version"),
                    }
                    for v in vulns
                    if v.get("id")
                ],
            }

        return {"status": "success", "lock_data": lock_data}
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


def _build_lock_from_synthesis(
    packages_in: list[dict[str, Any]],
    manifests: list[dict[str, Any]],
    system: dict[str, Any],
    resolution: dict[str, Any],
) -> dict:
    """Build lock data dict from pre-parsed inputs (original mode)."""
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
            pkg_map[name] = {
                "name": name,
                "ecosystem": rp.get("ecosystem", "?"),
                "resolved_version": rp.get("version"),
                "direct": False,
                "cuda_variant": rp.get("cuda_variant", False),
                "cuda_version": rp.get("cuda_version"),
                "original_constraint": "*",
                "source": "transitive",
                "vulnerabilities": [],
            }

    return {
        "version": "2.0",
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "resolver": "sat",
        "system": {
            "os": f"{plat.get('system', '?')} {plat.get('release', '?')}",
            "python": system.get("runtime_versions", {}).get("python", {}).get("version", "?"),
            "cpu": system.get("cpu", {}).get("brand", "Unknown"),
            "gpu": gpu_name,
            "cuda": gpu_info.get("cuda") if gpu_info.get("available") else None,
        },
        "manifests": [m.get("filename", m.get("path", "?")) for m in manifests],
        "packages": pkg_map,
        "warnings": resolution.get("warnings", []),
    }


MANIFEST_MAX_BYTES = 10 * 1024 * 1024


async def _check_request_body(request: Request) -> None:
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise HTTPException(status_code=415, detail="Content-Type must be application/json")
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MANIFEST_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Request body too large")


@router.post("/generate-lock")
async def generate_lock(
    request: Request,
    req: GenerateLockRequest,
    export_format: str | None = Query(
        None, description="Optional export format (e.g. requirements.txt, Dockerfile)"
    ),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate a udr.lock from project manifests or pre-parsed data.

    Two modes:
      1. **Manifest content mode** (mirrors ``udr lock``):
         POST ``manifest_contents`` as a dict of ``{filename: content}``.
         Optionally set ``manifest_filter`` to target one manifest file,
         and ``system`` to override auto-detected system info.
      2. **Pre-parsed mode** (original):
         POST ``packages``, ``manifests``, ``system``, ``resolution``.

    Optionally pass ``?export_format=requirements.txt`` to also generate
    export content alongside the lock data (mirrors ``udr lock --export``).

    Returns ``{"status": "success", "lock_data": {...}}`` plus
    ``"export_content"`` if ``export_format`` was provided.
    """
    await _check_request_body(request)
    if req.manifest_contents:
        result = await _run_lock_pipeline(
            req.manifest_contents,
            manifest_filter=req.manifest_filter,
            system_override=req.system,
        )
        if result["status"] != "success":
            raise HTTPException(
                status_code=400,
                detail=f"Lock generation failed: {result['status']}",
            )
        lock_data = result["lock_data"]
    else:
        if not req.packages:
            raise HTTPException(
                status_code=400,
                detail="Provide either 'manifest_contents' (dict of filename->content) or 'packages' (pre-parsed)",
            )
        lock_data = _build_lock_from_synthesis(
            req.packages,
            req.manifests,
            req.system or {},
            req.resolution or {},
        )

    # Optional export chaining (mirrors --export flag on CLI lock)
    export_content = None
    if export_format:
        try:
            from backend.core.export_generator import ExportGenerator

            exporter = ExportGenerator()
            resolved_packages = lock_data.get("packages", {})
            system = lock_data.get("system", {})
            export_content = exporter.generate(
                {
                    name: {
                        "version": info.get("resolved_version"),
                        "ecosystem": info.get("ecosystem", "?"),
                    }
                    for name, info in resolved_packages.items()
                },
                format=export_format,
                system_info={
                    "os": {"system": system.get("os", "Unknown")},
                    "runtime_versions": {"python": {"version": system.get("python", "3.x")}},
                    "gpu": {"available": bool(system.get("cuda")), "cuda": system.get("cuda")},
                },
            )
        except Exception as e:
            logger.warning("Export generation failed: %s", e)

    result = {"status": "success", "lock_data": lock_data}
    if export_content is not None:
        result["export_content"] = export_content
        result["export_format"] = export_format
    return result


@router.post("/install-commands")
async def install_commands(
    req: InstallCommandsRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate native install commands grouped by ecosystem from lock data.
    Mirrors `udr install <package>` using locked versions.
    """
    lock_data = req.lock_data
    packages = lock_data.get("packages", {})
    ecosystem_groups: dict[str, list[tuple]] = {}

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
            commands.append({"ecosystem": eco, "command": cmd, "package_count": len(pkgs)})

    return {
        "status": "success",
        "commands": commands,
        "total_packages": sum(g["package_count"] for g in commands),
    }


def _find_dep_chain(
    packages: dict, target: str, chain: list | None = None, visited: set | None = None
) -> list | None:
    """DFS to find the dependency chain leading to target."""
    if chain is None:
        chain = []
    if visited is None:
        visited = set()
    if target in visited:
        return None
    visited.add(target)
    for pkg_name, pinfo in packages.items():
        if pkg_name == target:
            continue
        ver = pinfo.get("resolved_version")
        if not ver:
            continue
        eco = pinfo.get("ecosystem", "pypi")
        deps = pinfo.get("dependencies", {}).get(eco, {})
        if target in deps:
            return [*chain, (pkg_name, ver, deps.get(target, "?"))]
        sub = _find_dep_chain(packages, target, [*chain, (pkg_name, ver, "?")], visited)
        if sub is not None:
            return sub
    return None


@router.post("/why")
async def why_package(
    req: WhyRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Explain why a package version was selected — dependency chain, constraint, direct/transitive.
    Mirrors `udr why <package>`.
    """
    lock_data = req.lock_data
    packages = lock_data.get("packages", {})
    target = req.package

    if target not in packages:
        raise HTTPException(status_code=404, detail=f"Package '{target}' not found in lock data")

    info = packages[target]
    ver = info.get("resolved_version")
    eco = info.get("ecosystem", "?")
    direct = info.get("direct", False)
    constraint = info.get("original_constraint", "*")

    chain = []
    if not direct:
        found = _find_dep_chain(packages, target)
        if found:
            chain = [{"package": p, "version": v, "required_as": r} for p, v, r in found]

    return {
        "status": "success",
        "package": target,
        "version": ver,
        "ecosystem": eco,
        "direct": direct,
        "original_constraint": constraint,
        "source": info.get("source", "unknown"),
        "dependency_chain": chain,
    }


@router.post("/outdated")
async def outdated_packages(
    req: OutdatedRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Check all packages against registries for newer versions.
    Mirrors `udr outdated --json`.
    """
    aggregator = DataAggregator()
    lock_data = req.lock_data
    packages = lock_data.get("packages", {})
    ecosystem_filter = req.ecosystem
    outdated_list: list[dict] = []

    async def check_pkg(name: str, info: dict) -> None:
        eco = info.get("ecosystem", "pypi")
        if ecosystem_filter and eco != ecosystem_filter:
            return
        ver = info.get("resolved_version")
        if not ver:
            return
        try:
            data = await aggregator.get_package_info(name, ecosystem=eco, include_versions=True)
            if data:
                versions = data.get("versions", {}).get(eco, [])
                version_strings = [
                    v.get("version", "") if isinstance(v, dict) else str(v) for v in versions
                ]
                sorted_vers = sorted(
                    [v for v in version_strings if v],
                    key=lambda x: __import__("packaging.version").parse(x),
                    reverse=True,
                )
                latest_str = sorted_vers[0] if sorted_vers else ver
                if latest_str != ver:
                    outdated_list.append(
                        {
                            "name": name,
                            "ecosystem": eco,
                            "current": ver,
                            "latest": latest_str,
                            "type": "direct" if info.get("direct") else "transitive",
                        }
                    )
        except Exception:
            logger.warning("Failed to check outdated status for %s", name, exc_info=True)

    try:
        await asyncio.gather(
            *[check_pkg(n, i) for n, i in packages.items()], return_exceptions=True
        )
    finally:
        await aggregator.close()
    outdated_list.sort(key=lambda x: x["name"])

    return {
        "status": "success",
        "outdated_count": len(outdated_list),
        "packages": outdated_list,
    }


@router.post("/diff")
async def diff_lock_files(
    req: DiffRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Compare two lock data objects and report package differences.
    Mirrors `udr diff <file_a> <file_b> --json`.
    """
    pkgs_a = req.lock_a.get("packages", {})
    pkgs_b = req.lock_b.get("packages", {})

    all_names = sorted(set(list(pkgs_a.keys()) + list(pkgs_b.keys())))

    added = []
    removed = []
    changed = []
    unchanged = 0

    for name in all_names:
        info_a = pkgs_a.get(name, {})
        info_b = pkgs_b.get(name, {})
        ver_a = info_a.get("resolved_version")
        ver_b = info_b.get("resolved_version")

        if not ver_a and ver_b:
            added.append(
                {"name": name, "ecosystem": info_b.get("ecosystem", "?"), "version": ver_b}
            )
        elif ver_a and not ver_b:
            removed.append(
                {"name": name, "ecosystem": info_a.get("ecosystem", "?"), "version": ver_a}
            )
        elif ver_a != ver_b:
            changed.append(
                {
                    "name": name,
                    "ecosystem": info_a.get("ecosystem", info_b.get("ecosystem", "?")),
                    "from": ver_a or "?",
                    "to": ver_b or "?",
                }
            )
        elif ver_a == ver_b:
            unchanged += 1

    return {
        "status": "success",
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_count": unchanged,
    }


@router.post("/restore-commands")
async def restore_commands(
    req: RestoreRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate install commands for ALL packages in lock data."""
    lock_data = req.lock_data
    packages = lock_data.get("packages", {})
    ecosystem_groups: dict[str, list[tuple]] = {}
    for name, info in packages.items():
        eco = info.get("ecosystem", "pypi")
        ver = info.get("resolved_version")
        if ver:
            ecosystem_groups.setdefault(eco, []).append((name, ver))
    commands = []
    for eco, pkgs in sorted(ecosystem_groups.items()):
        cmd = _generate_install_command(eco, pkgs)
        if cmd:
            commands.append({"ecosystem": eco, "command": cmd, "package_count": len(pkgs)})
    return {
        "status": "success",
        "commands": commands,
        "total_packages": sum(g["package_count"] for g in commands),
    }


class LockCheckRequest(BaseModel):
    manifest_contents: dict[str, str] | None = None
    existing_lock_data: dict[str, Any] | None = None


class SignedLockData(BaseModel):
    lock_data: dict[str, Any]


class UpdateFixRequest(BaseModel):
    lock_data: dict[str, Any]
    package: str | None = None


@router.post("/lock/check")
async def lock_check(
    req: LockCheckRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    from backend.core.data_aggregator import DataAggregator
    from backend.manifest_detector import ManifestDetector

    if not req.manifest_contents:
        raise HTTPException(status_code=400, detail="manifest_contents is required")
    detector = ManifestDetector()
    manifests = []
    for filename, content in req.manifest_contents.items():
        result = detector.parse_source(content, filename=filename)
        if result:
            manifests.append({"filename": filename, "dependencies": result})
    if not manifests:
        raise HTTPException(status_code=400, detail="Could not parse any manifests")
    all_deps: dict[str, list] = {}
    for m in manifests:
        for dep in m["dependencies"]:
            name = dep.get("name", "")
            if name:
                all_deps.setdefault(name, []).append(dep)
    aggregator = DataAggregator()
    resolver = create_solver()
    system_scanner = SystemScanner()
    system_info = await system_scanner.scan_all()
    try:
        resolved_packages = {}
        for name, deps_list in all_deps.items():
            eco = deps_list[0].get("ecosystem", "pypi")
            constraint = deps_list[0].get("constraint", "")
            info = await aggregator.get_package_info(name, ecosystem=eco)
            if info:
                versions = info.get("versions", {}).get(eco, [])
                version_strings = [
                    v.get("version", "") if isinstance(v, dict) else str(v) for v in versions
                ]
                resolved_packages[name] = {
                    "name": name,
                    "ecosystem": eco,
                    "versions": version_strings,
                    "constraint": constraint,
                }
        resolver_input = {
            "packages": {
                n: {"name": n, "ecosystem": p["ecosystem"], "versions": p["versions"]}
                for n, p in resolved_packages.items()
            },
            "root_packages": list(resolved_packages.keys()),
            "constraints": {
                n: p["constraint"] for n, p in resolved_packages.items() if p["constraint"]
            },
            "system_info": system_info,
        }
        resolution = resolver.resolve_dependencies(**resolver_input)
        new_pkgs = resolution.get("packages", {})
        old_pkgs = (req.existing_lock_data or {}).get("packages", {})
        all_names = sorted(set(list(new_pkgs.keys()) + list(old_pkgs.keys())))
        added, removed, changed = [], [], []
        for name in all_names:
            old_info = old_pkgs.get(name)
            new_info = new_pkgs.get(name)
            if old_info is None:
                added.append(
                    {
                        "name": name,
                        "version": new_info.get("resolved_version", "?"),
                        "direct": new_info.get("direct", False),
                    }
                )
            elif new_info is None:
                removed.append(
                    {
                        "name": name,
                        "version": old_info.get("resolved_version", "?"),
                        "direct": old_info.get("direct", False),
                    }
                )
            elif old_info.get("resolved_version") != new_info.get("resolved_version"):
                changed.append(
                    {
                        "name": name,
                        "from": old_info.get("resolved_version", "?"),
                        "to": new_info.get("resolved_version", "?"),
                    }
                )
        return {
            "status": "drift" if (added or removed or changed) else "ok",
            "drift_detected": bool(added or removed or changed),
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged_count": len(all_names) - len(added) - len(removed) - len(changed),
        }
    finally:
        await aggregator.close()


@router.post("/lock/sign")
async def lock_sign(
    req: SignedLockData,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    import base64
    import hashlib
    import json
    from pathlib import Path

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    lock_data = req.lock_data
    config_dir = Path.home() / ".config" / "udr"
    key_path = config_dir / "signing.key"
    if key_path.is_file():
        private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if not isinstance(private_key, ed25519.Ed25519PrivateKey):
            private_key = ed25519.Ed25519PrivateKey.generate()
            config_dir.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            key_path.chmod(0o600)
    else:
        config_dir.mkdir(parents=True, exist_ok=True)
        private_key = ed25519.Ed25519PrivateKey.generate()
        key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        key_path.chmod(0o600)
    pub_key_bytes = private_key.public_key().public_bytes_raw()
    (config_dir / "signing.pub").write_text(base64.b64encode(pub_key_bytes).decode() + "\n")
    exclude_keys = {"signature", "provenance"}
    canonical = json.dumps(
        {k: v for k, v in sorted(lock_data.items()) if k not in exclude_keys},
        sort_keys=True,
        default=str,
        ensure_ascii=False,
    )
    lock_data["signature"] = {
        "algorithm": "ed25519",
        "value": base64.b64encode(
            private_key.sign(hashlib.sha256(canonical.encode("utf-8")).digest())
        ).decode(),
        "public_key": base64.b64encode(pub_key_bytes).decode(),
    }
    return {
        "status": "success",
        "lock_data": lock_data,
        "signature": lock_data["signature"]["value"],
        "public_key": lock_data["signature"]["public_key"],
        "algorithm": "ed25519",
    }


@router.post("/lock/update-with-fix")
async def lock_update_with_fix(
    req: UpdateFixRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    from backend.core.data_aggregator import DataAggregator

    aggregator = DataAggregator()
    lock_data = req.lock_data
    packages = lock_data.get("packages", {})
    targets = (
        {n: i for n, i in packages.items() if n == req.package} if req.package else dict(packages)
    )
    vuln_map: dict[str, list[str]] = {}
    for pname, pinfo in targets.items():
        eco, ver = pinfo.get("ecosystem", ""), pinfo.get("resolved_version", "")
        if not eco or not ver:
            continue
        try:
            for v in await aggregator.check_vulnerabilities(pname, eco, ver):
                fixed = v.get("fixed_version")
                if fixed:
                    vuln_map.setdefault(pname, []).append(fixed)
        except Exception:
            logger.warning("CVE check failed for %s", pname, exc_info=True)
    await aggregator.close()
    if not vuln_map:
        return {
            "status": "ok",
            "message": "No vulnerabilities found with available fixes.",
            "lock_data": lock_data,
        }
    for pname, fixes in vuln_map.items():
        best = sorted(
            fixes,
            key=lambda x: tuple(int(p) if p.lstrip("-").isdigit() else 99999 for p in x.split(".")),
        )[-1]
        if pname in packages:
            packages[pname]["constraint"] = f">={best}"
    return {
        "status": "success",
        "fixes": {p: sorted(f)[-1] for p, f in vuln_map.items()},
        "lock_data": lock_data,
    }


class UpdateManifestsRequest(BaseModel):
    lock_data: dict[str, Any]
    manifest_contents: dict[str, str]


@router.post("/lock/update-manifests")
async def lock_update_manifests(
    req: UpdateManifestsRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Suggest version bump targets from lock data for each manifest file.

    Returns per-ecosystem suggestions for packages whose resolved version
    differs from their original constraint. Use the CLI ``udr update`` to
    apply these changes, since manifest file mutation requires filesystem access.
    """
    lock_data = req.lock_data
    packages = lock_data.get("packages", {})
    suggestions: dict[str, list[dict]] = {}

    for pname, pinfo in packages.items():
        eco = pinfo.get("ecosystem", "")
        ver = pinfo.get("resolved_version", "")
        constraint = pinfo.get("constraint", "")
        if constraint and constraint != f"=={ver}":
            suggestions.setdefault(eco, []).append(
                {
                    "package": pname,
                    "current_constraint": constraint,
                    "resolved_version": ver,
                    "ecosystem": eco,
                }
            )

    return {
        "status": "success",
        "suggestions": suggestions,
        "note": "Use `udr update` to apply manifest changes (requires filesystem access).",
    }


class LockReportRequest(BaseModel):
    lock_data: dict[str, Any]


@router.post("/lock/report")
async def lock_report(
    req: LockReportRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate a human-readable summary report from lock data.

    Mirrors the report step of ``udr lock --report``.
    """
    lock_data = req.lock_data
    packages = lock_data.get("packages", {})
    total = len(packages)
    direct = sum(1 for p in packages.values() if p.get("direct"))
    transitive = total - direct
    ecosystems: dict[str, int] = {}
    for p in packages.values():
        eco = p.get("ecosystem", "unknown")
        ecosystems[eco] = ecosystems.get(eco, 0) + 1

    resolver = lock_data.get("resolver", "?")
    host_system = lock_data.get("system", {})
    vuln_count = 0
    cves = []
    for pname, pinfo in packages.items():
        if "cves" in pinfo:
            vuln_count += len(pinfo["cves"])
            for c in pinfo["cves"]:
                cves.append(
                    {"package": pname, "id": c.get("id", "?"), "severity": c.get("severity", "?")}
                )

    report_lines = [
        "=" * 60,
        "Dependency Lock Report",
        "=" * 60,
        f"Resolver:              {resolver}",
        f"Total packages:        {total}",
        f"  Direct dependencies: {direct}",
        f"  Transitive:          {transitive}",
        f"Ecosystems:            {', '.join(f'{k}={v}' for k, v in sorted(ecosystems.items()))}",
        f"System:                {host_system.get('os', '?')}",
    ]
    if vuln_count:
        report_lines.append(f"Known vulnerabilities: {vuln_count}")
    report_lines.append("")
    report_lines.append(f"{'Package':40s} {'Version':20s} {'Type':10s} {'Vulns'}")
    report_lines.append("-" * 80)
    for pname in sorted(packages):
        pinfo = packages[pname]
        ver = pinfo.get("resolved_version", "?")
        ptype = "direct" if pinfo.get("direct") else "transitive"
        c = next((c["id"] for c in cves if c["package"] == pname), "")
        report_lines.append(f"{pname:40s} {ver:20s} {ptype:10s} {c}")

    return {
        "status": "success",
        "report": "\n".join(report_lines),
        "summary": {
            "total": total,
            "direct": direct,
            "transitive": transitive,
            "ecosystems": ecosystems,
            "vulnerabilities": vuln_count,
        },
        "cves": cves,
    }


class ApplyPinningRequest(BaseModel):
    lock_data: dict[str, Any]
    pin: list[str] | None = None
    block: list[str] | None = None
    pin_mode: str | None = None
    freeze: bool = False


@router.post("/lock/apply-pinning")
async def lock_apply_pinning(
    req: ApplyPinningRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Apply pin/block/freeze constraints to lock data.

    Mirrors ``udr lock --pin --block --freeze --pin-mode``.
    """
    from dataclasses import asdict

    from backend.core.pinning import PinningPolicy

    lock_data = req.lock_data
    packages = lock_data.get("packages", {})

    pp = PinningPolicy(
        pinned=dict(p.split("==", 1) for p in (req.pin or []) if "==" in p),
        blocked=set(req.block or []),
        pin_mode=req.pin_mode or "major",
        freeze=req.freeze,
    )

    pp.apply(packages)

    return {
        "status": "success",
        "lock_data": lock_data,
        "pinning_policy": {k: v for k, v in asdict(pp).items() if v},
    }
