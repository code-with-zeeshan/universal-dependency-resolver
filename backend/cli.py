"""
CLI entry point for Universal Dependency Resolver.

Usage:
    udr serve            Start the API server
    udr check            Check system compatibility
    udr resolve <pkg>    Resolve dependencies for a package
    udr info             Show system information
    udr lock             Auto-detect manifests and resolve all deps
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


def _parse_package_spec(spec: str, default_ecosystem: str = "pypi") -> Tuple[str, str]:
    """Parse pkg@ecosystem syntax, falling back to default ecosystem."""
    if "@" in spec:
        parts = spec.split("@", 1)
        name = parts[0].strip()
        eco = parts[1].strip().lower()
        return name, eco
    return spec.strip(), default_ecosystem


def _extract_cuda_variants(versions_info: List[Dict], base_version: str) -> List[Dict]:
    """Find CUDA-tagged local versions for a given base version."""
    pattern = re.compile(rf"^{re.escape(base_version)}\+cu(\d+)")
    variants = []
    for vinfo in versions_info:
        ver = vinfo.get("version", "")
        match = pattern.match(ver)
        if match:
            variants.append({"version": ver, "cuda_version": match.group(1)})
    return variants


def _select_best_cuda_variant(variants: List[Dict], system_cuda: Optional[str]) -> Optional[str]:
    """Select the best CUDA variant matching system CUDA version."""
    if not variants:
        return None
    if not system_cuda:
        return variants[0]["version"]
    # Try exact match first
    for v in variants:
        if v["cuda_version"] == system_cuda:
            return v["version"]
    # Fall back to highest compatible (<= system CUDA)
    system_major = _parse_major_version(system_cuda)
    compatible = [v for v in variants if _parse_major_version(v["cuda_version"]) <= system_major]
    if compatible:
        compatible.sort(key=lambda x: int(x["cuda_version"]), reverse=True)
        return compatible[0]["version"]
    return variants[0]["version"]


def _parse_major_version(cuda_str: str) -> int:
    try:
        return int(cuda_str.split(".")[0])
    except (ValueError, IndexError):
        return 0


def _aggregator_to_resolver_input(agg_data: Dict, ecosystem: str) -> Dict:
    """Convert DataAggregator output to ConflictResolver input format.

    Aggregator keys: name, ecosystems, versions, dependencies, system_requirements
    Resolver expects: name, ecosystem, available_versions, dependencies, system_requirements
    """
    # Collect available versions (skip CUDA local variants for SAT solving)
    available_versions = []
    raw_versions = agg_data.get("versions", {}).get(ecosystem, [])
    for vinfo in raw_versions:
        ver = vinfo.get("version", "") if isinstance(vinfo, dict) else str(vinfo)
        if "+" not in ver:
            available_versions.append(ver)

    # Extract dependencies
    deps = {}
    eco_deps = agg_data.get("dependencies", {}).get(ecosystem, {})
    for dep in eco_deps.get("all", []):
        deps[dep.name] = dep.version_spec

    # Extract system requirements
    sys_reqs = {}
    eco_reqs = agg_data.get("system_requirements", {}).get(ecosystem, [])
    for req in eco_reqs:
        if req.type == "runtime" and req.name == "python" and req.version_spec:
            min_ver = req.version_spec.lstrip(">= ")
            sys_reqs["python"] = {"min_version": min_ver}

    # Check for CUDA requirements from ecosystem data
    eco_data = agg_data.get("ecosystems", {}).get(ecosystem, {})
    cuda_req = eco_data.get("system_requirements", {}).get("cuda")
    if cuda_req:
        sys_reqs["cuda"] = cuda_req

    return {
        "name": agg_data.get("name"),
        "ecosystem": ecosystem,
        "available_versions": sorted(set(available_versions)),
        "dependencies": {ecosystem: deps},
        "system_requirements": sys_reqs,
    }


async def _resolve_transitive(
    aggregator,
    resolver,
    packages: List[Dict],
    system_info: Dict,
    max_depth: int = 3,
) -> Dict:
    """Resolve dependencies recursively, fetching transitive deps.

    Args:
        aggregator: DataAggregator instance
        resolver: ConflictResolver instance
        packages: Initial list of package dicts (from _aggregator_to_resolver_input)
        system_info: System info dict
        max_depth: Maximum recursion depth for transitive resolution

    Returns:
        Resolution result from resolver.resolve_dependencies()
    """
    visited = set()
    queue = list(packages)
    all_packages = {}
    depth = 0

    while queue and depth <= max_depth:
        depth += 1
        # Process current level
        next_round = []
        for pkg in queue:
            key = (pkg["name"], pkg["ecosystem"])
            if key in visited:
                continue
            visited.add(key)

            if key not in all_packages:
                all_packages[key] = pkg

            # Fetch dependencies of this package
            try:
                info = await aggregator.get_package_info(
                    pkg["name"],
                    ecosystem=pkg["ecosystem"],
                    include_dependencies=True,
                    include_versions=True,
                )
                if not info:
                    continue

                eco = pkg["ecosystem"]
                eco_deps = info.get("dependencies", {}).get(eco, {})
                for dep in eco_deps.get("all", []):
                    dep_key = (dep.name, eco)
                    if dep_key not in visited and dep_key not in all_packages:
                        dep_pkg = {
                            "name": dep.name,
                            "ecosystem": eco,
                            "available_versions": [],
                            "dependencies": {eco: {}},
                            "system_requirements": {},
                        }
                        # Fetch dep info to get versions
                        dep_info = await aggregator.get_package_info(
                            dep.name, ecosystem=eco,
                            include_dependencies=True,
                            include_versions=True,
                        )
                        if dep_info:
                            dep_pkg["available_versions"] = _aggregator_to_resolver_input(
                                dep_info, eco
                            ).get("available_versions", [])
                            dep_deps = dep_info.get("dependencies", {}).get(eco, {})
                            dep_pkg["dependencies"][eco] = {
                                d.name: d.version_spec for d in dep_deps.get("all", [])
                            }
                            dep_reqs = dep_info.get("system_requirements", {}).get(eco, [])
                            for req in dep_reqs:
                                if req.type == "runtime" and req.name == "python" and req.version_spec:
                                    dep_pkg["system_requirements"]["python"] = {
                                        "min_version": req.version_spec.lstrip(">= ")
                                    }
                        all_packages[dep_key] = dep_pkg
                        next_round.append(dep_pkg)
            except Exception as e:
                # Skip transitive deps that can't be fetched
                pass

        queue = next_round

    # Convert to list for resolver
    pkg_list = list(all_packages.values())
    return resolver.resolve_dependencies(pkg_list, system_info, prefer_compatibility=True)


def _apply_cuda_variants(resolved: Dict, package_details: Dict[str, Dict], system_info: Dict) -> Dict:
    """After SAT resolution, select CUDA-tagged variants for PyPI packages.

    Args:
        resolved: Resolution result from resolver (with resolved_packages)
        package_details: dict of pkg_name -> aggregator data
        system_info: System info with GPU/CUDA info

    Returns:
        Resolution result with CUDA variants applied
    """
    resolved_pkgs = resolved.get("resolved_packages", {})
    system_cuda = None
    if system_info and "gpu" in system_info:
        system_cuda = system_info["gpu"].get("cuda")

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
            best = _select_best_cuda_variant(cuda_variants, system_cuda)
            if best and best != base_version:
                resolved_pkgs[pkg_name]["version"] = best
                resolved_pkgs[pkg_name]["cuda_variant"] = True
                resolved_pkgs[pkg_name]["cuda_version"] = next(
                    (v["cuda_version"] for v in cuda_variants if v["version"] == best), None
                )

    if resolved_pkgs:
        resolved["resolved_packages"] = resolved_pkgs
    return resolved


def cmd_serve(args):
    from backend.api.main import app
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


def cmd_check(args):
    from backend.core import SystemScanner

    async def _check():
        scanner = SystemScanner()
        info = await scanner.scan_all()
        ok = True
        print("System Compatibility Check")
        print("=" * 40)
        print(f"  OS:     {info['platform']['system']} {info['platform']['release']}")
        print(f"  CPU:    {info['cpu']['brand']} ({info['cpu']['count']} cores)")
        if info["gpu"]["available"]:
            gpu = info["gpu"]["devices"][0]
            print(f"  GPU:    {gpu['name']} ({gpu['memory_total']} MB)")
            print(f"  CUDA:   {info['gpu'].get('cuda', 'not found')}")
        else:
            print(f"  GPU:    None")
        py = info["runtime_versions"]["python"]
        print(f"  Python: {py['version']}")
        if args.verbose:
            print(f"  Python path: {py['location']}")
            print(f"  CPU arch:    {info['cpu']['arch']}")
            if info["gpu"].get("cuda"):
                print(f"  CUDA version: {info['gpu']['cuda']}")
        return ok

    sys.exit(0 if asyncio.run(_check()) else 1)


def cmd_resolve(args):
    from backend.core import DataAggregator, ConflictResolver
    from packaging import version
    from packaging.version import Version

    async def _resolve():
        aggregator = DataAggregator()
        resolver = ConflictResolver()
        scanner = None

        # Parse package specs: support pkg@ecosystem syntax
        specs = [_parse_package_spec(p, args.ecosystem) for p in args.packages]

        # Scan system for GPU/CUDA info (for variant selection)
        system_info = None
        if any(eco == "pypi" for _, eco in specs):
            from backend.core import SystemScanner
            scanner = SystemScanner()
            system_info = await scanner.scan_all()

        if not system_info:
            system_info = resolver._get_default_system_info()

        # Fetch metadata and transform for resolver
        resolver_inputs = []
        package_details = {}

        for pkg_name, eco in specs:
            print(f"Fetching {pkg_name} from {eco}...", file=sys.stderr)
            try:
                data = await aggregator.get_package_info(
                    pkg_name, ecosystem=eco,
                    include_dependencies=True,
                    include_versions=True,
                )
                if data:
                    package_details[pkg_name] = data
                    rinput = _aggregator_to_resolver_input(data, eco)
                    resolver_inputs.append(rinput)
                    if rinput["available_versions"]:
                        print(f"  → {len(rinput['available_versions'])} versions found", file=sys.stderr)
                    else:
                        print(f"  → no versions found", file=sys.stderr)
                else:
                    print(f"Warning: {pkg_name} not found in {eco}", file=sys.stderr)
            except Exception as e:
                print(f"Error fetching {pkg_name}: {e}", file=sys.stderr)

        if not resolver_inputs:
            print("No packages could be resolved", file=sys.stderr)
            return 1

        # Transitive resolution
        print(f"\nResolving with SAT solver (including transitive deps)...", file=sys.stderr)
        try:
            resolved = await _resolve_transitive(
                aggregator, resolver, resolver_inputs, system_info
            )
        except Exception as e:
            print(f"SAT resolution failed, falling back to alternative resolution: {e}", file=sys.stderr)
            resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)

        # Apply GPU-aware CUDA variant selection
        resolved = _apply_cuda_variants(resolved, package_details, system_info)

        # Output
        if args.format == "json":
            json.dump(resolved, sys.stdout, indent=2, default=str)
            print()
        else:
            rp = resolved.get("resolved_packages", {})
            if not rp:
                print("No packages resolved.")
            else:
                print(f"\nResolved {len(rp)} packages:")
                for name, info in rp.items():
                    ver = info.get("version", "?")
                    eco = info.get("ecosystem", "?")
                    cuda = info.get("cuda_version")
                    cuda_str = f" (CUDA {cuda})" if cuda else ""
                    print(f"  [{eco:>10}] {name} == {ver}{cuda_str}")

            warnings = resolved.get("warnings", [])
            for w in warnings:
                print(f"  ⚠ {w}")

        return 0

    sys.exit(asyncio.run(_resolve()))


def cmd_info(args):
    from backend.core import SystemScanner

    async def _info():
        scanner = SystemScanner()
        info = await scanner.scan_all()
        print(f"System Information for {info['platform']['system']} {info['platform']['release']}")
        print(f"  Architecture: {info['platform']['machine']}")
        print(f"  CPU: {info['cpu']['brand']} ({info['cpu']['count']} cores)")
        print(f"  Python: {info['runtime_versions']['python']['version']}")
        print(f"  Python path: {info['runtime_versions']['python']['location']}")
        if info["gpu"]["available"]:
            gpu = info["gpu"]["devices"][0]
            print(f"  GPU: {gpu['name']} ({gpu['memory_total']} MB)")
            cuda = info["gpu"].get("cuda")
            if cuda:
                print(f"  CUDA: {cuda}")
        import tomllib
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if pyproject.is_file():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            deps = data.get("project", {}).get("dependencies", [])
            print(f"\nInstalled ({len(deps)} core packages)")
            for d in deps:
                print(f"  {d}")

    asyncio.run(_info())


def cmd_lock(args):
    from backend.manifest_detector import ManifestDetector
    from backend.core import DataAggregator, ConflictResolver, SystemScanner
    from backend.core.export_generator import ExportGenerator

    async def _lock():
        directory = Path(args.directory).resolve()
        detector = ManifestDetector(str(directory))
        aggregator = DataAggregator()
        resolver = ConflictResolver()
        scanner = SystemScanner()
        exporter = ExportGenerator()

        # 1. Detect manifests
        manifests = detector.detect()
        if not manifests:
            print(f"No dependency manifests found in {directory}", file=sys.stderr)
            print("Checked for: requirements.txt, package.json, Cargo.toml, pyproject.toml,", file=sys.stderr)
            print("             Pipfile, environment.yml, Gemfile, go.mod, composer.json", file=sys.stderr)
            return 1

        print(f"Found {len(manifests)} manifest(s) in {directory}:")
        for m in manifests:
            print(f"  [{m['ecosystem']:>10}] {m['filename']}")
        print()

        # 2. Parse all manifests
        packages = detector.normalize(detector.parse_all(manifests))
        if not packages:
            print("No packages found in manifests", file=sys.stderr)
            return 1

        print(f"Found {len(packages)} package(s):")
        for pkg in packages:
            print(f"  [{pkg['ecosystem']:>10}] {pkg['name']} ({pkg['constraint']}) — from {pkg['source']}")
        print()

        # 3. Fetch metadata and build SAT solver inputs
        seen = set()
        resolver_inputs = []
        package_details = {}

        for pkg in packages:
            key = (pkg["name"], pkg["ecosystem"])
            if key in seen:
                continue
            seen.add(key)
            print(f"  Fetching {pkg['name']} from {pkg['ecosystem']}...")
            try:
                data = await aggregator.get_package_info(
                    pkg["name"],
                    ecosystem=pkg["ecosystem"],
                    include_dependencies=True,
                    include_versions=True,
                )
                if data:
                    package_details[pkg["name"]] = data
                    rinput = _aggregator_to_resolver_input(data, pkg["ecosystem"])
                    resolver_inputs.append(rinput)
                    print(f"    → {len(rinput['available_versions'])} versions")
                else:
                    print(f"    → not found")
            except Exception as e:
                print(f"    → error: {e}")

        if not resolver_inputs:
            print("No package data could be fetched", file=sys.stderr)
            return 1

        # 4. Scan system
        print("\nScanning system...")
        system_info = await scanner.scan_all()

        # 5. Resolve dependencies (transitive, with SAT solver)
        print("Resolving dependencies (with SAT solver)...")
        try:
            resolved = await _resolve_transitive(
                aggregator, resolver, resolver_inputs, system_info
            )
        except Exception as e:
            print(f"SAT resolution failed, using alternatives: {e}")
            resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)

        # 6. Apply CUDA variant selection
        resolved = _apply_cuda_variants(resolved, package_details, system_info)

        # 7. Build lock data
        resolved_pkgs = resolved.get("resolved_packages", {})
        lock_data = {
            "version": "2.0",
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "resolver": "sat",
            "system": {
                "os": f"{system_info['platform']['system']} {system_info['platform']['release']}",
                "python": system_info["runtime_versions"]["python"]["version"],
                "cpu": system_info["cpu"]["brand"],
                "gpu": system_info["gpu"]["devices"][0]["name"] if system_info["gpu"]["available"] else None,
                "cuda": system_info["gpu"].get("cuda") if system_info["gpu"]["available"] else None,
            },
            "manifests": [m["filename"] for m in manifests],
            "packages": {},
            "warnings": resolved.get("warnings", []),
        }

        for p in packages:
            rp = resolved_pkgs.get(p["name"], {})
            lock_data["packages"][p["name"]] = {
                "name": p["name"],
                "ecosystem": p["ecosystem"],
                "resolved_version": rp.get("version"),
                "cuda_variant": rp.get("cuda_variant", False),
                "cuda_version": rp.get("cuda_version"),
                "original_constraint": p["constraint"],
                "source": p["source"],
            }

        # 8. Write lock file
        lock_path = directory / "udr-lock.json"
        lock_path.write_text(json.dumps(lock_data, indent=2, default=str))
        print(f"\nLock file written: {lock_path}")

        # Print summary
        rp_count = len([p for p in lock_data["packages"].values() if p["resolved_version"]])
        print(f"Resolved {rp_count}/{len(packages)} packages")
        for pname, pinfo in lock_data["packages"].items():
            if pinfo["resolved_version"]:
                cuda = f" (+cu{pinfo['cuda_version']})" if pinfo.get("cuda_variant") else ""
                print(f"  [{pinfo['ecosystem']:>10}] {pname} == {pinfo['resolved_version']}{cuda}")
            else:
                print(f"  [{pinfo['ecosystem']:>10}] {pname} — unresolved")

        # 9. Export if requested
        if args.export:
            export_format = args.export
            print(f"Exporting as {export_format}...")
            try:
                export_content = exporter.generate(
                    {
                        p["name"]: {
                            "version": lock_data["packages"][p["name"]]["resolved_version"],
                            "ecosystem": p["ecosystem"],
                        }
                        for p in packages
                    },
                    format=export_format,
                    system_info=system_info,
                )
                export_path = directory / f"udr-output.{export_format.replace('.', '-')}"
                export_path.write_text(export_content)
                print(f"Exported: {export_path}")
            except Exception as e:
                print(f"Export failed: {e}")

        # 10. Prompt to update manifests in-place
        if not args.yes and not args.dry_run:
            answer = input("\nUpdate manifests in-place with pinned versions? [y/N] ").strip().lower()
            args.yes = answer in ("y", "yes")

        if args.dry_run:
            print("\n[dry-run] No files were modified.")
            return 0

        if args.yes:
            for pkg in packages:
                manifest_path = directory / pkg["source"]
                if not manifest_path.is_file():
                    continue
                resolved_ver = lock_data["packages"][pkg["name"]]["resolved_version"]
                if not resolved_ver:
                    continue
                content = manifest_path.read_text(encoding="utf-8", errors="replace")
                constraint = pkg["constraint"]
                if constraint != resolved_ver and not constraint.startswith("=="):
                    new_content = []
                    replaced = False
                    for line in content.split("\n"):
                        stripped = line.strip()
                        if not replaced and stripped.startswith(pkg["name"]):
                            for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
                                if op in stripped:
                                    name_part = stripped.split(op)[0].strip()
                                    if name_part == pkg["name"]:
                                        indent = line[:len(line) - len(line.lstrip())]
                                        new_content.append(f"{indent}{pkg['name']}=={resolved_ver}")
                                        replaced = True
                                        break
                            else:
                                indent = line[:len(line) - len(line.lstrip())]
                                new_content.append(f"{indent}{pkg['name']}=={resolved_ver}")
                                replaced = True
                        else:
                            new_content.append(line)
                    if replaced:
                        manifest_path.write_text("\n".join(new_content) + "\n")
                        print(f"  Updated {pkg['source']}: {pkg['name']} → {resolved_ver}")

        return 0

    sys.exit(asyncio.run(_lock()))


def main():
    parser = argparse.ArgumentParser(
        prog="udr",
        description="Universal Dependency Resolver — resolve dependencies across ecosystems",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="Start the API server")
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind address")
    serve_p.add_argument("--port", type=int, default=8000, help="Bind port")
    serve_p.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    check_p = sub.add_parser("check", help="Check system compatibility")
    check_p.add_argument("-v", "--verbose", action="store_true", help="Show detailed info")

    resolve_p = sub.add_parser("resolve", help="Resolve dependencies for one or more packages")
    resolve_p.add_argument(
        "packages", nargs="+",
        help="Package names (use pkg@ecosystem syntax, e.g. numpy@pypi express@npm)",
    )
    resolve_p.add_argument(
        "--ecosystem", "-e", default="pypi",
        choices=["pypi", "npm", "cargo", "go", "conda", "maven", "crates", "nuget", "rubygems"],
        help="Default ecosystem (used for packages without @ecosystem suffix)",
    )
    resolve_p.add_argument("--format", "-f", default="text", choices=["text", "json"], help="Output format")

    info_p = sub.add_parser("info", help="Show system information")

    lock_p = sub.add_parser("lock", help="Auto-detect manifests, resolve all dependencies, write lock file")
    lock_p.add_argument("--directory", "-d", default=".", help="Project directory to scan (default: current)")
    lock_p.add_argument("--manifest", "-m", help="Only process a specific manifest file (auto-detect otherwise)")
    lock_p.add_argument("--export", help="Export to a specific format (e.g. requirements.txt, Dockerfile)")
    lock_p.add_argument("--yes", "-y", action="store_true", help="Update manifests in-place without prompting")
    lock_p.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")

    args = parser.parse_args()
    dispatch = {
        "serve": cmd_serve,
        "check": cmd_check,
        "resolve": cmd_resolve,
        "info": cmd_info,
        "lock": cmd_lock,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
