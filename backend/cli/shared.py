"""Shared CLI helpers for Universal Dependency Resolver."""

import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from backend.core.constraint_normalizer import normalize_constraint

console = Console()
err_console = Console(stderr=True)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from importlib.metadata import version as _importlib_version

    VERSION = _importlib_version("ud-resolver")
except (ImportError, Exception):
    _ver_path = PROJECT_ROOT / "pyproject.toml"
    VERSION = (
        _ver_path.read_text().split('version = "')[1].split('"')[0]
        if _ver_path.is_file()
        else "unknown"
    )

LOCK_FILE_VERSION = "2.0"
LOCK_SUPPORTED_VERSIONS = {"1.0", "2.0"}


def _parse_package_spec(spec: str, default_ecosystem: str = "pypi") -> Tuple[str, str]:
    if "@" in spec:
        name, eco = spec.rsplit("@", 1)
        return name.strip(), eco.strip().lower()
    return spec.strip(), default_ecosystem


def _extract_cuda_variants(versions_info: List[Dict], base_version: str) -> List[Dict]:
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


def _extract_severity(vuln: Dict) -> str:
    sev = vuln.get("severity", [])
    if isinstance(sev, list) and sev:
        return sev[0].get("score", sev[0].get("type", "UNKNOWN"))
    if isinstance(sev, str):
        return sev
    return "UNKNOWN"


def _select_best_cuda_variant(
    variants: List[Dict], system_cuda: Optional[str]
) -> Optional[str]:
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


def _aggregator_to_resolver_input(
    agg_data: Dict, ecosystem: str, constraint: Optional[str] = None
) -> Dict:
    available_versions = []
    raw_versions = agg_data.get("versions", {}).get(ecosystem, [])
    for vinfo in raw_versions:
        ver = vinfo.get("version", "") if isinstance(vinfo, dict) else str(vinfo)
        if not re.search(r"\+cu\d", ver):
            yanked = vinfo.get("yanked", False) if isinstance(vinfo, dict) else False
            deprecated = (
                vinfo.get("deprecated", False) if isinstance(vinfo, dict) else False
            )
            if not yanked and not deprecated:
                available_versions.append(ver)

    deps = {}
    eco_deps = agg_data.get("dependencies", {}).get(ecosystem, {})
    for dep in eco_deps.get("all", []):
        deps[dep.name] = normalize_constraint(dep.version_spec, ecosystem)

    sys_reqs = _extract_system_requirements(agg_data, ecosystem)

    norm_constraint = normalize_constraint(constraint or "*", ecosystem)

    return {
        "name": agg_data.get("name"),
        "ecosystem": ecosystem,
        "version_constraint": norm_constraint,
        "available_versions": sorted(set(available_versions), reverse=True),
        "dependencies": {ecosystem: deps},
        "system_requirements": sys_reqs,
        "cross_ecosystem_deps": agg_data.get("cross_ecosystem_deps", []),
    }


def _extract_system_requirements(agg_data: Dict, ecosystem: str) -> Dict:
    sys_reqs = {}
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


async def _resolve_transitive(
    aggregator,
    resolver,
    packages: List[Dict],
    system_info: Dict,
    max_depth: int = 10,
) -> Dict:
    visited = set()
    queue = list(packages)
    all_packages = {}
    depth = 0

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

            try:
                info = await aggregator.get_package_info(
                    pkg["name"],
                    ecosystem=pkg["ecosystem"],
                    include_dependencies=True,
                    include_versions=True,
                )
                if not info:
                    continue

                all_deps = info.get("dependencies", {})
                for dep_eco, dep_data in all_deps.items():
                    for dep in dep_data.get("all", []):
                        dep_key_eco = (
                            dep_eco if dep_eco != pkg["ecosystem"] else pkg["ecosystem"]
                        )
                        dep_ecosystem = getattr(dep, "ecosystem", None)
                        if dep_ecosystem and dep_ecosystem.value != pkg["ecosystem"]:
                            dep_key_eco = dep_ecosystem.value
                        dep_eco_val = dep_key_eco

                        dep_key = (dep.name, dep_eco_val)
                        if dep_key not in visited and dep_key not in all_packages:
                            dep_pkg = None
                            try:
                                dep_info = await aggregator.get_package_info(
                                    dep.name,
                                    ecosystem=dep_eco_val,
                                    include_dependencies=True,
                                    include_versions=True,
                                )
                                if dep_info:
                                    dep_avail = _aggregator_to_resolver_input(
                                        dep_info, dep_eco_val
                                    ).get("available_versions", [])
                                    if dep_avail:
                                        dep_pkg = {
                                            "name": dep.name,
                                            "ecosystem": dep_eco_val,
                                            "available_versions": dep_avail,
                                            "dependencies": {dep_eco_val: {}},
                                            "system_requirements": {},
                                        }
                                        dep_deps = dep_info.get("dependencies", {}).get(
                                            dep_eco_val, {}
                                        )
                                        dep_pkg["dependencies"][dep_eco_val] = {
                                            d.name: normalize_constraint(
                                                d.version_spec, dep_eco_val
                                            )
                                            for d in dep_deps.get("all", [])
                                        }
                                        dep_reqs = dep_info.get(
                                            "system_requirements", {}
                                        ).get(dep_eco_val, [])
                                        for req in dep_reqs:
                                            if (
                                                req.type == "runtime"
                                                and req.name == "python"
                                                and req.version_spec
                                            ):
                                                dep_pkg["system_requirements"][
                                                    "python"
                                                ] = {
                                                    "min_version": req.version_spec.lstrip(
                                                        ">= "
                                                    )
                                                }
                                        if dep_eco_val != pkg["ecosystem"]:
                                            if "cross_ecosystem_deps" not in dep_pkg:
                                                dep_pkg["cross_ecosystem_deps"] = []
                                            dep_pkg["cross_ecosystem_deps"].append(
                                                {
                                                    "source": f"{pkg['name']}@{pkg['ecosystem']}",
                                                    "target_ecosystem": dep_eco_val,
                                                }
                                            )
                            except Exception as exc:
                                logger.warning(
                                    "Failed to fetch transitive deps for %s/%s: %s",
                                    dep.name,
                                    dep_eco_val,
                                    exc,
                                )
                            if dep_pkg:
                                all_packages[dep_key] = dep_pkg
                                next_round.append(dep_pkg)

                        if dep_key in all_packages and dep_eco_val != pkg["ecosystem"]:
                            existing = all_packages.get(dep_key)
                            if existing and "cross_ecosystem_deps" not in existing:
                                existing["cross_ecosystem_deps"] = []
                            if existing and not any(
                                x.get("source") == f"{pkg['name']}@{pkg['ecosystem']}"
                                for x in existing.get("cross_ecosystem_deps", [])
                            ):
                                existing.setdefault("cross_ecosystem_deps", []).append(
                                    {
                                        "source": f"{pkg['name']}@{pkg['ecosystem']}",
                                        "target_ecosystem": dep_eco_val,
                                    }
                                )

            except Exception as exc:
                logger.warning(
                    "Failed to fetch transitive deps for %s/%s: %s",
                    pkg["name"],
                    pkg["ecosystem"],
                    exc,
                )

        queue = next_round

    pkg_list = list(all_packages.values())
    return resolver.resolve_dependencies(
        pkg_list, system_info, prefer_compatibility=True
    )


async def _run_resolution(
    aggregator,
    resolver,
    resolver_inputs,
    system_info,
    package_details,
    interactive: bool = False,
) -> Dict:
    timeout = int(os.environ.get("SOLVER_TIMEOUT", 30))
    try:
        resolved = await asyncio.wait_for(
            _resolve_transitive(aggregator, resolver, resolver_inputs, system_info),
            timeout=timeout,
        )
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning("Transitive resolution %s: falling back to alternatives", exc)
        resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)
        resolved["resolved_packages"] = resolved.pop("packages", {})

    resolved = _apply_cuda_variants(resolved, package_details, system_info)

    if interactive and resolved.get("status") == "unsatisfiable":
        err_console.print(
            Panel(
                "[yellow]SAT solver found no valid combination.[/yellow]\n"
                "Resolving manually by selecting alternatives...",
                title="Conflict Detected",
            )
        )
        resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)
        resolved["resolved_packages"] = resolved.pop("packages", {})
        resolved = _apply_cuda_variants(resolved, package_details, system_info)

    return resolved


def _apply_cuda_variants(
    resolved: Dict, package_details: Dict[str, Dict], system_info: Dict
) -> Dict:
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
            raw_versions = details.get("versions", {}).get(
                pkg_info.get("ecosystem", ""), []
            )

        cuda_variants = _extract_cuda_variants(raw_versions, base_version)
        if cuda_variants:
            has_cuda_variants = True
            if not system_cuda:
                err_console.print(
                    f"  [yellow]⚠ CUDA variant available for {pkg_name} but no GPU detected[/yellow]"
                )
                err_console.print(
                    "     Use --cuda <version> to target a specific CUDA version"
                )
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
        err_console.print(
            "  [yellow]⚠ CUDA variants exist but were not selected — resolution is CPU-only[/yellow]"
        )

    if resolved_pkgs:
        resolved["resolved_packages"] = resolved_pkgs
    return resolved


def _fetch_package_data(
    aggregator, specs: List[Tuple[str, str]]
) -> Tuple[List[Dict], Dict[str, Dict]]:
    return asyncio.run(_fetch_package_data_async(aggregator, specs))


async def _fetch_package_data_async(
    aggregator, specs: List[Tuple[str, str]]
) -> Tuple[List[Dict], Dict[str, Dict]]:
    resolver_inputs = []
    package_details = {}

    async def fetch_one(pkg_name: str, eco: str) -> Optional[Tuple[Dict, Dict]]:
        try:
            data = await aggregator.get_package_info(
                pkg_name,
                ecosystem=eco,
                include_dependencies=True,
                include_versions=True,
            )
            if data:
                rinput = _aggregator_to_resolver_input(data, eco)
                return (rinput, data)
        except Exception as exc:
            err_console.print(f"  [red]Error fetching {pkg_name}:[/red] {exc}")
        return None

    results = await asyncio.gather(*[fetch_one(n, e) for n, e in specs])

    for spec, result in zip(specs, results):
        pkg_name = spec[0]
        if result:
            rinput, data = result
            resolver_inputs.append(rinput)
            package_details[pkg_name] = data
        else:
            err_console.print(f"  [yellow]Warning:[/yellow] {pkg_name} not found")

    return resolver_inputs, package_details


def _build_resolved_table(resolved: Dict, title: Optional[str] = None) -> Optional[Table]:
    rp = resolved.get("resolved_packages", {})
    if not rp:
        return None
    table = Table(title=title or f"Resolved {len(rp)} packages", box=box.ROUNDED)
    table.add_column("Package", style="cyan")
    table.add_column("Ecosystem")
    table.add_column("Version", style="bold green")
    table.add_column("Notes")
    for name, info in rp.items():
        ver = info.get("version", "?")
        eco = info.get("ecosystem", "?")
        cuda = info.get("cuda_version")
        notes = f"CUDA {cuda}" if cuda else ""
        table.add_row(name, eco, ver, notes)
    return table


def _output_json(data: Any, args) -> None:
    json.dump(data, sys.stdout, indent=2, default=str)
    print()
    sys.exit(0)


def _read_lock_file(lock_path: Path) -> Dict:
    if not lock_path.is_file():
        console.print(f"[red]Lock file not found:[/red] {lock_path}")
        sys.exit(1)
    try:
        data = json.loads(lock_path.read_text())
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid lock file:[/red] {exc}")
        sys.exit(1)
    ver = data.get("version", "0.0")
    if ver not in LOCK_SUPPORTED_VERSIONS:
        console.print(
            f"[red]Unsupported lock file version: {ver} (expected one of: {', '.join(sorted(LOCK_SUPPORTED_VERSIONS))})[/red]"
        )
        sys.exit(1)
    return data


def _validate_manifest_update_line(
    line: str, pkg_name: str, resolved_ver: str
) -> Optional[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None

    quote = ""
    for q in ['"', "'"]:
        if stripped.startswith(q):
            quote = q
            break

    for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
        if op in stripped:
            before_op = stripped.split(op)[0].strip().strip("\"'")
            if before_op != pkg_name:
                continue
            after_op = stripped.split(op, 1)[1].strip()
            after_op = after_op.split("#")[0].split(" --")[0].strip()
            after_op = after_op.split(";")[0].strip().rstrip("\"'").rstrip(",")
            indent = line[: len(line) - len(line.lstrip())]
            trailing = ""
            raw = line.strip()
            after_version_pos = raw.rfind(after_op) + len(after_op) if after_op else -1
            if after_version_pos > 0:
                trailing = raw[after_version_pos:]
            if quote:
                return f"{indent}{quote}{pkg_name}=={resolved_ver}{quote}{trailing}"
            return f"{indent}{pkg_name}=={resolved_ver}{trailing}"
    if stripped.startswith(pkg_name + " "):
        indent = line[: len(line) - len(line.lstrip())]
        rest = stripped[len(pkg_name):]
        after_comment = rest.split("#")[0].strip()
        if after_comment and not any(c in after_comment for c in "=<>~!"):
            return f"{indent}{pkg_name}=={resolved_ver}"
    return None


def _select_manifests_interactive(manifests: List[Dict]) -> List[Dict]:
    console.print("\n[bold]Detected manifests:[/bold]")
    for i, m in enumerate(manifests, 1):
        console.print(f"  {i}. [{m['ecosystem']}] {m['filename']}")
    choice = input(
        "\nSelect manifests to include (enter numbers comma-separated, or 'all' for all, default: all): "
    ).strip()
    if not choice or choice.lower() == "all":
        return manifests
    try:
        indices = [int(x.strip()) for x in choice.split(",")]
        selected = [manifests[i - 1] for i in indices if 1 <= i <= len(manifests)]
        if not selected:
            console.print("[yellow]No valid selections — using all manifests[/yellow]")
            return manifests
        return selected
    except (ValueError, IndexError):
        console.print("[yellow]Invalid input — using all manifests[/yellow]")
        return manifests


def _generate_install_command(
    ecosystem: str, packages: List[Tuple[str, str]]
) -> Optional[str]:
    if not packages:
        return None
    installers = {
        "pypi": ("pip", "install"),
        "npm": ("npm", "install"),
        "crates": ("cargo", "add"),
        "gomodules": ("go", "get"),
        "conda": ("conda", "install"),
        "rubygems": ("gem", "install"),
        "packagist": ("composer", "require"),
        "pub": ("dart", "pub", "add"),
        "nuget": ("dotnet", "add", "package"),
        "cocoapods": ("pod", "install"),
        "maven": ("mvn", "dependency:copy-dependencies"),
    }
    installer = installers.get(ecosystem)
    if not installer:
        logger.warning(f"No installer known for ecosystem: {ecosystem}")
        return None
    if ecosystem == "npm":
        specs = [f"{name}@{ver}" for name, ver in packages]
    elif ecosystem == "pub":
        specs = [f"{name}:{ver}" for name, ver in packages]
    elif ecosystem in ("gomodules", "cocoapods"):
        specs = [f"{name}@{ver}" for name, ver in packages]
    else:
        specs = [f"{name}=={ver}" for name, ver in packages]
    return " ".join(list(installer) + specs)
