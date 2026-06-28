"""
CLI entry point for Universal Dependency Resolver.

Usage:
    udr serve            Start the API server
    udr check            Check system compatibility
    udr resolve <pkg>    Resolve dependencies for a package
    udr info             Show system information
    udr lock             Auto-detect manifests and resolve all deps
    udr graph            Show dependency tree
    udr verify           Validate lock file
    udr list-ecosystems  List supported ecosystems
    udr update <pkg>     Re-resolve a package and update lock file
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Confirm
from rich.table import Table
from rich.tree import Tree
from rich import box

from backend.settings import ECOSYSTEMS, ECOSYSTEM_NAMES

console = Console()
err_console = Console(stderr=True)
logger = logging.getLogger(__name__)

VERSION = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text().split('version = "')[1].split('"')[0] if (Path(__file__).resolve().parent.parent / "pyproject.toml").is_file() else "unknown"


def _parse_package_spec(spec: str, default_ecosystem: str = "pypi") -> Tuple[str, str]:
    """Parse pkg@ecosystem syntax, falling back to default ecosystem.
    Splits on the last @ so scoped npm packages (e.g. @angular/core) work.
    """
    if "@" in spec:
        name, eco = spec.rsplit("@", 1)
        return name.strip(), eco.strip().lower()
    return spec.strip(), default_ecosystem


def _extract_cuda_variants(versions_info: List[Dict], base_version: str) -> List[Dict]:
    """Find CUDA-tagged local versions for a given base version."""
    pattern = re.compile(rf"^{re.escape(base_version)}\+cu(\d+)")
    variants = []
    for vinfo in versions_info:
        ver = vinfo.get("version", "") if isinstance(vinfo, dict) else str(vinfo)
        match = pattern.match(ver)
        if match:
            variants.append({"version": ver, "cuda_version": match.group(1)})
    return variants


def _normalize_cuda(cuda_str: str) -> int:
    """Convert CUDA version string to comparable int by stripping dots.
    '12.1' -> 121, '118' -> 118, 'cu118' -> 118
    """
    cleaned = cuda_str.replace(".", "").lstrip("cu")
    try:
        return int(cleaned)
    except (ValueError, IndexError):
        return 0


def _select_best_cuda_variant(variants: List[Dict], system_cuda: Optional[str]) -> Optional[str]:
    """Select the best CUDA variant matching system CUDA version."""
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


def _aggregator_to_resolver_input(agg_data: Dict, ecosystem: str) -> Dict:
    """Convert DataAggregator output to ConflictResolver input format."""
    available_versions = []
    raw_versions = agg_data.get("versions", {}).get(ecosystem, [])
    for vinfo in raw_versions:
        ver = vinfo.get("version", "") if isinstance(vinfo, dict) else str(vinfo)
        if "+" not in ver:
            available_versions.append(ver)

    deps = {}
    eco_deps = agg_data.get("dependencies", {}).get(ecosystem, {})
    for dep in eco_deps.get("all", []):
        deps[dep.name] = dep.version_spec

    sys_reqs = {}
    eco_reqs = agg_data.get("system_requirements", {}).get(ecosystem, [])
    for req in eco_reqs:
        if req.type == "runtime" and req.name == "python" and req.version_spec:
            min_ver = req.version_spec.lstrip(">= ")
            sys_reqs["python"] = {"min_version": min_ver}

    eco_data = agg_data.get("ecosystem", {}).get(ecosystem, {})
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
    """Resolve dependencies recursively, fetching transitive deps."""
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
            except Exception as exc:
                logger.warning("Failed to fetch transitive deps for %s/%s: %s", pkg["name"], pkg["ecosystem"], exc)

        queue = next_round

    pkg_list = list(all_packages.values())
    return resolver.resolve_dependencies(pkg_list, system_info, prefer_compatibility=True)


def _apply_cuda_variants(resolved: Dict, package_details: Dict[str, Dict], system_info: Dict) -> Dict:
    """After SAT resolution, select CUDA-tagged variants for PyPI packages."""
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


def _run_resolution(
    aggregator, resolver, resolver_inputs, system_info, package_details,
    interactive: bool = False,
) -> Dict:
    """Run resolution with SAT solver, fallback, CUDA variants, and interactive mode."""
    try:
        resolved = asyncio.run(_resolve_transitive(
            aggregator, resolver, resolver_inputs, system_info,
        ))
    except Exception as exc:
        err_console.print(f"[yellow]SAT resolution fell back to alternatives:[/yellow] {exc}")
        resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)

    resolved = _apply_cuda_variants(resolved, package_details, system_info)

    if interactive and resolved.get("status") == "unsatisfiable":
        err_console.print(Panel(
            "[yellow]SAT solver found no valid combination.[/yellow]\n"
            "Resolving manually by selecting alternatives...",
            title="Conflict Detected",
        ))
        resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)
        resolved = _apply_cuda_variants(resolved, package_details, system_info)

    return resolved


def _fetch_package_data(
    aggregator, specs: List[Tuple[str, str]]
) -> Tuple[List[Dict], Dict[str, Dict]]:
    """Fetch package metadata concurrently. Returns (resolver_inputs, package_details)."""
    async def _fetch():
        resolver_inputs = []
        package_details = {}

        async def fetch_one(pkg_name: str, eco: str) -> Optional[Tuple[Dict, Dict]]:
            try:
                data = await aggregator.get_package_info(
                    pkg_name, ecosystem=eco,
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

    return asyncio.run(_fetch())


def _build_resolved_table(resolved: Dict, title: str = None) -> Table:
    """Build a Rich table from resolved packages."""
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
    """Print JSON output and exit if --json was passed."""
    json.dump(data, sys.stdout, indent=2, default=str)
    print()
    sys.exit(0)


def _read_lock_file(lock_path: Path) -> Dict:
    """Read and parse a udr-lock.json file."""
    if not lock_path.is_file():
        console.print(f"[red]Lock file not found:[/red] {lock_path}")
        sys.exit(1)
    try:
        return json.loads(lock_path.read_text())
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid lock file:[/red] {exc}")
        sys.exit(1)


def _validate_manifest_update_line(line: str, pkg_name: str, resolved_ver: str) -> Optional[str]:
    """Update a single manifest line if it references the given package.
    Handles pip options, comments, and avoids substring matches.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None
    for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
        if op in stripped:
            before_op = stripped.split(op)[0].strip()
            after_op = stripped.split(op, 1)[1].strip()
            after_op = after_op.split("#")[0].split(" --")[0].strip()
            after_op = after_op.split(";")[0].strip()
            if before_op == pkg_name:
                indent = line[:len(line) - len(line.lstrip())]
                trailing = line[line.rfind(after_op) + len(after_op):] if after_op in line else ""
                return f"{indent}{pkg_name}=={resolved_ver}{trailing}"
    if stripped.startswith(pkg_name + " "):
        indent = line[:len(line) - len(line.lstrip())]
        rest = stripped[len(pkg_name):]
        after_comment = rest.split("#")[0].strip()
        if after_comment and not any(c in after_comment for c in "=<>~!"):
            return f"{indent}{pkg_name}=={resolved_ver}"
    return None


# =============================================================================
# Existing commands (fixed)
# =============================================================================

def cmd_serve(args):
    try:
        from backend.api.main import app
        import uvicorn
        console.print("[bold green]Starting UDR API server...[/bold green]")
        console.print(f"  Mode: [cyan]{args.mode}[/cyan]")
        console.print(f"  Host: [yellow]{args.host}[/yellow]  Port: [yellow]{args.port}[/yellow]")
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Server Error"))
        sys.exit(1)


def cmd_check(args):
    from backend.core import SystemScanner

    async def _check():
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=err_console,
        ) as progress:
            progress.add_task("Scanning system...", total=None)
            scanner = SystemScanner()
            info = await scanner.scan_all()

        if getattr(args, 'json', False):
            return _output_json(info, args)

        table = Table(title="System Compatibility", box=box.ROUNDED)
        table.add_column("Component", style="cyan")
        table.add_column("Value")
        table.add_column("Status", style="bold")

        plat = info.get("platform", {})
        table.add_row("OS", f"{plat.get('system', '?')} {plat.get('release', '?')}", "✅")
        arch = plat.get('machine', info.get('cpu', {}).get('arch', 'unknown'))
        table.add_row("Architecture", arch, "✅")
        cpu_cores = info.get('cpu', {}).get('count_logical') or info.get('cpu', {}).get('count_physical') or info.get('cpu', {}).get('count', '?')
        table.add_row("CPU", f"{info.get('cpu', {}).get('brand', 'Unknown')} ({cpu_cores} cores)", "✅")

        mem = info.get("memory", {})
        if mem:
            total = mem.get("total", 0) / (1024**3)
            avail = mem.get("available", 0) / (1024**3)
            pct = mem.get("percent", 0)
            mem_status = "⚠" if pct > 90 else "✅"
            table.add_row("Memory", f"{total:.1f} GB total, {avail:.1f} GB free", mem_status)

        gpu_info = info.get("gpu", {})
        if gpu_info.get("available"):
            gpu_devices = gpu_info.get("devices", [])
            if gpu_devices:
                gpu = gpu_devices[0]
                cuda = gpu_info.get("cuda", "not found")
                table.add_row("GPU", f"{gpu.get('name', '?')} ({gpu.get('memory_total', '?')} MB)", "✅")
                table.add_row("CUDA", cuda, "✅" if cuda and cuda != "not found" else "⚠")
            else:
                table.add_row("GPU", "No GPU devices", "ℹ")
        else:
            table.add_row("GPU", "None detected", "ℹ")

        py = info.get("runtime_versions", {}).get("python", {})
        table.add_row("Python", py.get('version', '?'), "✅")

        if args.verbose:
            table.add_row("Python path", py.get('path', py.get('location', '?')), "")
            table.add_row("CPU arch", info.get('cpu', {}).get('arch', 'unknown'), "")

        console.print(table)

        if args.verbose:
            rt_table = Table(title="Runtime Versions", box=box.SIMPLE)
            rt_table.add_column("Runtime", style="cyan")
            rt_table.add_column("Version")
            for rt_name, rt_info in info.get("runtime_versions", {}).items():
                if isinstance(rt_info, dict) and rt_info.get("version"):
                    rt_table.add_row(rt_name, rt_info["version"])
            console.print(rt_table)

        if args.deps:
            import tomllib
            pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
            if pyproject.is_file():
                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                deps = data.get("project", {}).get("dependencies", [])
                dep_table = Table(title=f"Core Dependencies ({len(deps)} packages)", box=box.SIMPLE)
                dep_table.add_column("Dependency", style="cyan")
                for d in deps:
                    dep_table.add_row(d)
                console.print(dep_table)

        return True

    try:
        asyncio.run(_check())
        sys.exit(0)
    except Exception as e:
        console.print(Panel(f"[red]Check failed:[/red] {e}", title="Error"))
        sys.exit(1)


def cmd_resolve(args):
    from backend.core import DataAggregator, ConflictResolver, SystemScanner

    async def _resolve():
        aggregator = DataAggregator()
        resolver = ConflictResolver()

        specs = [_parse_package_spec(p, args.ecosystem) for p in args.packages]

        system_info = None
        if any(eco == "pypi" for _, eco in specs):
            scanner = SystemScanner()
            with Progress(SpinnerColumn(), TextColumn("Scanning system..."), transient=True, console=err_console) as p:
                p.add_task("scan", total=None)
                system_info = await scanner.scan_all()

        if not system_info:
            system_info = resolver._get_default_system_info()

        resolver_inputs = []
        package_details = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[green]{task.completed}/{task.total}[/green]"),
            console=err_console,
        ) as progress:
            fetch_task = progress.add_task("Fetching package metadata...", total=len(specs))

            async def fetch_one(pkg_name, eco):
                progress.update(fetch_task, description=f"Fetching [cyan]{pkg_name}[/cyan] from [yellow]{eco}[/yellow]...")
                try:
                    data = await aggregator.get_package_info(
                        pkg_name, ecosystem=eco,
                        include_dependencies=True,
                        include_versions=True,
                    )
                    if data:
                        return (pkg_name, data)
                    else:
                        err_console.print(f"  [yellow]Warning:[/yellow] {pkg_name} not found in {eco}")
                except Exception as exc:
                    err_console.print(f"  [red]Error fetching {pkg_name}:[/red] {exc}")
                return None

            results = await asyncio.gather(*[fetch_one(n, e) for n, e in specs])

            for spec, result in zip(specs, results):
                if result:
                    pkg_name, data = result
                    package_details[pkg_name] = data
                    rinput = _aggregator_to_resolver_input(data, spec[1])
                    resolver_inputs.append(rinput)
                progress.advance(fetch_task)

        if not resolver_inputs:
            console.print("[red]No packages could be resolved[/red]")
            return 1

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True, console=err_console) as p:
            p.add_task("Resolving dependencies with SAT solver...", total=None)
            resolved = _run_resolution(
                aggregator, resolver, resolver_inputs, system_info, package_details,
                interactive=args.interactive,
            )

        if args.format == "json":
            json.dump(resolved, sys.stdout, indent=2, default=str)
            print()
        else:
            table = _build_resolved_table(resolved)
            if table:
                console.print(table)
            else:
                console.print("[yellow]No packages resolved.[/yellow]")

            warnings = resolved.get("warnings", [])
            for w in warnings:
                console.print(f"  [yellow]⚠[/yellow] {w}")

        return 0

    try:
        sys.exit(asyncio.run(_resolve()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Resolution Error"))
        sys.exit(1)


def cmd_info(args):
    from backend.core import SystemScanner

    async def _info():
        with Progress(SpinnerColumn(), TextColumn("Scanning system..."), transient=True, console=err_console) as p:
            p.add_task("scan", total=None)
            scanner = SystemScanner()
            info = await scanner.scan_all()

        if getattr(args, 'json', False):
            return _output_json(info, args)

        plat = info.get("platform", {})
        table = Table(title=f"System: {plat.get('system', '?')} {plat.get('release', '?')}", box=box.ROUNDED)
        table.add_column("Property", style="cyan")
        table.add_column("Value")

        table.add_row("Architecture", plat.get('machine', '?'))
        cpu_cores = info.get('cpu', {}).get('count_logical') or info.get('cpu', {}).get('count_physical') or info.get('cpu', {}).get('count', '?')
        table.add_row("CPU", f"{info.get('cpu', {}).get('brand', 'Unknown')} ({cpu_cores} cores)")
        py_info = info.get("runtime_versions", {}).get("python", {})
        table.add_row("Python", py_info.get('version', '?'))
        table.add_row("Python path", py_info.get('path', py_info.get('location', '?')))

        mem = info.get("memory", {})
        if mem:
            total = mem.get("total", 0) / (1024**3)
            avail = mem.get("available", 0) / (1024**3)
            table.add_row("Memory", f"{total:.1f} GB total, {avail:.1f} GB free")

        gpu_info = info.get("gpu", {})
        if gpu_info.get("available"):
            gpu_devices = gpu_info.get("devices", [])
            if gpu_devices:
                gpu = gpu_devices[0]
                table.add_row("GPU", f"{gpu.get('name', '?')} ({gpu.get('memory_total', '?')} MB)")
                cuda = gpu_info.get("cuda", "not found")
                if cuda and cuda != "not found":
                    table.add_row("CUDA", cuda)

        console.print(table)

        import tomllib
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if pyproject.is_file():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            deps = data.get("project", {}).get("dependencies", [])
            dep_table = Table(title=f"Core Dependencies ({len(deps)} packages)", box=box.SIMPLE)
            dep_table.add_column("Dependency", style="cyan")
            for d in deps:
                dep_table.add_row(d)
            console.print(dep_table)

    try:
        asyncio.run(_info())
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Info Error"))
        sys.exit(1)


def _select_manifests_interactive(manifests: List[Dict]) -> List[Dict]:
    """Prompt user to select which manifests to include. Default: all."""
    console.print("\n[bold]Detected manifests:[/bold]")
    for i, m in enumerate(manifests, 1):
        console.print(f"  {i}. [{m['ecosystem']}] {m['filename']}")
    choice = input(
        f"\nSelect manifests to include (enter numbers comma-separated, or 'all' for all, default: all): "
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


def cmd_lock(args):
    from backend.manifest_detector import ManifestDetector
    from backend.core import DataAggregator, ConflictResolver, SystemScanner
    from backend.core.export_generator import ExportGenerator

    async def _lock():
        directory = Path(args.directory).resolve()
        if not directory.is_dir():
            console.print(f"[red]Directory not found:[/red] {directory}")
            return 1

        detector = ManifestDetector(str(directory))
        aggregator = DataAggregator()
        resolver = ConflictResolver()
        scanner = SystemScanner()
        exporter = ExportGenerator()

        # 1. Detect manifests
        with Progress(SpinnerColumn(), TextColumn("Scanning for manifests..."), transient=True, console=err_console) as p:
            p.add_task("detect", total=None)
            manifests = detector.detect()

        if not manifests:
            console.print(f"[red]No dependency manifests found in {directory}[/red]")
            console.print("Checked for: requirements.txt, package.json, Cargo.toml, pyproject.toml,")
            console.print("             Pipfile, environment.yml, Gemfile, go.mod, composer.json")
            return 1

        # Apply --manifest filter
        if args.manifest:
            manifests = [m for m in manifests if m["filename"] == args.manifest]
            if not manifests:
                console.print(f"[red]Manifest '{args.manifest}' not found in {directory}[/red]")
                return 1

        # Interactive manifest selection
        if args.interactive:
            manifests = _select_manifests_interactive(manifests)

        manifest_table = Table(title=f"Selected {len(manifests)} manifest(s)", box=box.SIMPLE)
        manifest_table.add_column("Ecosystem", style="cyan")
        manifest_table.add_column("Filename")
        for m in manifests:
            manifest_table.add_row(m['ecosystem'], m['filename'])
        console.print(manifest_table)

        # 2. Parse manifests
        packages = detector.normalize(detector.parse_all(manifests))
        if not packages:
            console.print("[red]No packages found in manifests[/red]")
            return 1

        pkg_table = Table(title=f"Found {len(packages)} package(s)", box=box.SIMPLE)
        pkg_table.add_column("Ecosystem", style="cyan")
        pkg_table.add_column("Package")
        pkg_table.add_column("Constraint")
        pkg_table.add_column("Source")
        for pkg in packages:
            pkg_table.add_row(pkg['ecosystem'], pkg['name'], pkg['constraint'], pkg['source'])
        console.print(pkg_table)

        # 3. Fetch metadata
        seen = set()
        resolver_inputs = []
        package_details = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[green]{task.completed}/{task.total}[/green]"),
            console=err_console,
        ) as progress:
            fetch_task = progress.add_task("Fetching package metadata...", total=len(packages))

            async def fetch_one(pkg):
                key = (pkg["name"], pkg["ecosystem"])
                if key in seen:
                    return None
                seen.add(key)
                progress.update(fetch_task, description=f"Fetching [cyan]{pkg['name']}[/cyan]...")
                try:
                    data = await aggregator.get_package_info(
                        pkg["name"],
                        ecosystem=pkg["ecosystem"],
                        include_dependencies=True,
                        include_versions=True,
                    )
                    if data:
                        return (pkg, data)
                except Exception as exc:
                    err_console.print(f"  [red]Error fetching {pkg['name']}:[/red] {exc}")
                return None

            results = await asyncio.gather(*[fetch_one(p) for p in packages])

            for pkg, result in zip(packages, results):
                if result:
                    _, data = result
                    package_details[pkg["name"]] = data
                    rinput = _aggregator_to_resolver_input(data, pkg["ecosystem"])
                    resolver_inputs.append(rinput)
                progress.advance(fetch_task)

        if not resolver_inputs:
            console.print("[red]No package data could be fetched[/red]")
            return 1

        # 4. Scan system
        with Progress(SpinnerColumn(), TextColumn("Scanning system..."), transient=True, console=err_console) as p:
            p.add_task("system", total=None)
            system_info = await scanner.scan_all()

        # 5. Resolve
        with Progress(SpinnerColumn(), TextColumn("Resolving dependencies..."), transient=True, console=err_console) as p:
            p.add_task("SAT solver", total=None)
            resolved = _run_resolution(
                aggregator, resolver, resolver_inputs, system_info, package_details,
                interactive=args.interactive,
            )

        # 6. Build lock data
        resolved_pkgs = resolved.get("resolved_packages", {})
        plat = system_info.get("platform", {})
        gpu_info = system_info.get("gpu", {})
        gpu_name = None
        if gpu_info.get("available"):
            gpu_devices = gpu_info.get("devices", [])
            if gpu_devices:
                gpu_name = gpu_devices[0].get("name")
        lock_data = {
            "version": "2.0",
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "resolver": "sat",
            "system": {
                "os": f"{plat.get('system', '?')} {plat.get('release', '?')}",
                "python": system_info.get("runtime_versions", {}).get("python", {}).get("version", "?"),
                "cpu": system_info.get("cpu", {}).get("brand", "Unknown"),
                "gpu": gpu_name,
                "cuda": gpu_info.get("cuda") if gpu_info.get("available") else None,
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

        # 7. JSON output
        if getattr(args, 'json', False):
            return _output_json(lock_data, args)

        # 8. Write lock file
        lock_path = directory / "udr-lock.json"
        lock_path.write_text(json.dumps(lock_data, indent=2, default=str))

        rp_count = len([p for p in lock_data["packages"].values() if p["resolved_version"]])
        summary_table = Table(title=f"Resolved {rp_count}/{len(packages)} packages — {lock_path.name}", box=box.ROUNDED)
        summary_table.add_column("Package", style="cyan")
        summary_table.add_column("Ecosystem")
        summary_table.add_column("Resolved Version", style="bold green")
        summary_table.add_column("Notes")

        for pname, pinfo in lock_data["packages"].items():
            if pinfo["resolved_version"]:
                cuda_str = f"(+cu{pinfo['cuda_version']})" if pinfo.get("cuda_variant") else ""
                summary_table.add_row(pname, pinfo['ecosystem'], pinfo['resolved_version'], cuda_str)
            else:
                summary_table.add_row(pname, pinfo['ecosystem'], "[red]unresolved[/red]", "")

        console.print(summary_table)

        # 9. Export if requested
        if args.export:
            export_format = args.export
            with Progress(SpinnerColumn(), TextColumn(f"Exporting as {export_format}..."), transient=True, console=err_console) as p:
                p.add_task("export", total=None)
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
                    console.print(f"[green]Exported:[/green] {export_path}")
                except Exception as e:
                    console.print(f"[red]Export failed:[/red] {e}")

        if args.dry_run:
            console.print("[yellow]── dry run — no files modified ──[/yellow]")
            return 0

        # 10. Prompt to update manifests
        if not args.yes:
            proceed = Confirm.ask("\nUpdate manifests in-place with pinned versions?", default=False)
            if not proceed:
                return 0

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
                new_lines = []
                replaced = False
                for line in content.split("\n"):
                    result = _validate_manifest_update_line(line, pkg["name"], resolved_ver)
                    if result is not None and not replaced:
                        new_lines.append(result)
                        replaced = True
                    else:
                        new_lines.append(line)
                if replaced:
                    manifest_path.write_text("\n".join(new_lines) + "\n")
                    console.print(f"  [green]Updated[/green] {pkg['source']}: {pkg['name']} → {resolved_ver}")

        return 0

    try:
        sys.exit(asyncio.run(_lock()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Lock Error"))
        sys.exit(1)


# =============================================================================
# New commands
# =============================================================================

def cmd_graph(args):
    """Display dependency tree for one or more packages."""
    from backend.core import DataAggregator, ConflictResolver

    try:
        specs = [_parse_package_spec(p, args.ecosystem) for p in args.packages]
        aggregator = DataAggregator()
        resolver = ConflictResolver()
        system_info = resolver._get_default_system_info()

        resolver_inputs, package_details = _fetch_package_data(aggregator, specs)

        if not resolver_inputs:
            console.print("[red]No packages could be resolved[/red]")
            sys.exit(1)

        err_console.print("[dim]Resolving dependencies for dependency tree...[/dim]")
        resolved = asyncio.run(_resolve_transitive(
            aggregator, resolver, resolver_inputs, system_info,
        ))

        rp = resolved.get("resolved_packages", {})
        if not rp:
            console.print("[yellow]No packages resolved.[/yellow]")
            return

        tree = Tree("[bold]Dependency Tree[/bold]")

        for name, info in rp.items():
            eco = info.get("ecosystem", "?")
            ver = info.get("version", "?")
            node = tree.add(f"[cyan]{name}[/cyan] [yellow]{ver}[/yellow] ({eco})")
            deps = info.get("dependencies", {}).get(eco, {})
            for dep_name, dep_ver in deps.items():
                node.add(f"[white]{dep_name}[/white] [dim]{dep_ver}[/dim]")

        console.print(tree)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Graph Error"))
        sys.exit(1)


def cmd_verify(args):
    """Validate lock file: check all resolved versions still exist."""
    try:
        from backend.core import DataAggregator

        lock_path = Path(args.lock_file)
        lock_data = _read_lock_file(lock_path)
        aggregator = DataAggregator()

        packages = lock_data.get("packages", {})
        if not packages:
            console.print("[yellow]No packages in lock file[/yellow]")
            return

        issues = []
        ok_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[green]{task.completed}/{task.total}[/green]"),
            console=err_console,
        ) as progress:
            verify_task = progress.add_task("Verifying packages...", total=len(packages))

            async def check_pkg(name: str, info: Dict) -> Optional[Dict]:
                eco = info.get("ecosystem", "pypi")
                ver = info.get("resolved_version")
                if not ver:
                    return {"name": name, "issue": "No resolved version", "severity": "warning"}
                try:
                    data = await aggregator.get_package_info(
                        name, ecosystem=eco, include_versions=True,
                    )
                    if data:
                        versions = data.get("versions", {}).get(eco, [])
                        version_strings = [
                            v.get("version", "") if isinstance(v, dict) else str(v)
                            for v in versions
                        ]
                        if ver not in version_strings:
                            return {"name": name, "issue": f"Version {ver} no longer available", "severity": "error"}
                    else:
                        return {"name": name, "issue": "Package not found on registry", "severity": "error"}
                except Exception as exc:
                    return {"name": name, "issue": str(exc), "severity": "error"}
                return None

            results = asyncio.run(asyncio.gather(*[check_pkg(n, i) for n, i in packages.items()]))

            for result in results:
                if result:
                    issues.append(result)
                    progress.update(verify_task, description=f"[red]Issue: {result['name']}[/red]")
                else:
                    ok_count += 1
                progress.advance(verify_task)

        summary = Table(title=f"Lock File Verification — {lock_path.name}", box=box.ROUNDED)
        summary.add_column("Status", style="bold")
        summary.add_column("Count")
        summary.add_row("✅ OK", str(ok_count))
        summary.add_row("⚠ Issues", str(len(issues)))
        console.print(summary)

        if issues:
            issue_table = Table(box=box.SIMPLE)
            issue_table.add_column("Severity", style="bold")
            issue_table.add_column("Package")
            issue_table.add_column("Issue")
            for iss in issues:
                sev_icon = "[red]ERROR[/red]" if iss["severity"] == "error" else "[yellow]WARN[/yellow]"
                issue_table.add_row(sev_icon, iss["name"], iss["issue"])
            console.print(issue_table)

        if issues and any(i["severity"] == "error" for i in issues):
            sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Verify Error"))
        sys.exit(1)


def cmd_list_ecosystems(args):
    """List all supported ecosystems."""
    table = Table(title=f"Supported Ecosystems ({len(ECOSYSTEMS)})", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Identifier")

    for eco in ECOSYSTEMS:
        display = ECOSYSTEM_NAMES.get(eco, eco.replace("_", " ").title())
        table.add_row(eco, display, eco)

    console.print(table)


def cmd_update(args):
    """Re-resolve a single package and update the lock file."""
    try:
        from backend.core import DataAggregator, ConflictResolver, SystemScanner

        lock_path = Path(args.directory) / "udr-lock.json"
        lock_data = _read_lock_file(lock_path)
        aggregator = DataAggregator()
        resolver = ConflictResolver()
        scanner = SystemScanner()

        package_name = args.package
        packages_in_lock = lock_data.get("packages", {})
        if package_name not in packages_in_lock:
            console.print(f"[red]Package '{package_name}' not found in lock file[/red]")
            sys.exit(1)

        pkg_info = packages_in_lock[package_name]
        ecosystem = pkg_info.get("ecosystem", "pypi")
        console.print(f"Re-resolving [cyan]{package_name}[/cyan] ([yellow]{ecosystem}[/yellow])...")

        with Progress(SpinnerColumn(), TextColumn("Scanning system..."), transient=True, console=err_console) as p:
            p.add_task("system", total=None)
            system_info = asyncio.run(scanner.scan_all())

        specs = [(package_name, ecosystem)]
        resolver_inputs, package_details = _fetch_package_data(aggregator, specs)

        if not resolver_inputs:
            console.print(f"[red]Could not fetch metadata for {package_name}[/red]")
            sys.exit(1)

        err_console.print("[dim]Running SAT resolution...[/dim]")
        resolved = _run_resolution(
            aggregator, resolver, resolver_inputs, system_info, package_details,
            interactive=args.interactive,
        )

        rp = resolved.get("resolved_packages", {})
        new_version = rp.get(package_name, {}).get("version") if rp else None

        if not new_version:
            console.print(f"[red]Could not resolve {package_name}[/red]")
            sys.exit(1)

        old_version = pkg_info.get("resolved_version")
        if new_version == old_version:
            console.print(f"[green]{package_name} is already at version {new_version} — no update needed[/green]")
            return

        lock_data["packages"][package_name]["resolved_version"] = new_version
        lock_data["packages"][package_name]["cuda_variant"] = rp.get(package_name, {}).get("cuda_variant", False)
        lock_data["packages"][package_name]["cuda_version"] = rp.get(package_name, {}).get("cuda_version")
        lock_data["generated_at"] = __import__("datetime").datetime.now().isoformat()

        lock_path.write_text(json.dumps(lock_data, indent=2, default=str))
        console.print(f"[green]Updated[/green] {package_name}: {old_version} → [bold]{new_version}[/bold]")
        console.print(f"[dim]Lock file: {lock_path}[/dim]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Update Error"))
        sys.exit(1)


# =============================================================================
# Parser
# =============================================================================

def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="udr",
        description="Universal Dependency Resolver — resolve dependencies across ecosystems",
    )
    parser.add_argument("--version", action="version", version=f"udr {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="Start the API server")
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind address")
    serve_p.add_argument("--port", type=int, default=8000, help="Bind port")
    serve_p.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    serve_p.add_argument("--mode", choices=["local", "saas"], default="local",
                         help="Run mode: local (no auth, default) or saas (full auth stack)")

    check_p = sub.add_parser("check", help="Check system compatibility")
    check_p.add_argument("-v", "--verbose", action="store_true", help="Show detailed info")
    check_p.add_argument("--deps", action="store_true", help="Show project core dependencies")
    check_p.add_argument("--json", action="store_true", help="Output as JSON")

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
    resolve_p.add_argument("--interactive", "-i", action="store_true",
                           help="Interactive mode for resolving conflicts manually")

    info_p = sub.add_parser("info", help="Show detailed system information and project dependencies")
    info_p.add_argument("--json", action="store_true", help="Output as JSON")

    lock_p = sub.add_parser("lock", help="Auto-detect manifests, resolve all dependencies, write lock file")
    lock_p.add_argument("--directory", "-d", default=".", help="Project directory to scan")
    lock_p.add_argument("--manifest", "-m", help="Only process a specific manifest file")
    lock_p.add_argument("--export", help="Export to a specific format (e.g. requirements.txt, Dockerfile)")
    lock_p.add_argument("--yes", "-y", action="store_true", help="Update manifests without prompting")
    lock_p.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    lock_p.add_argument("--interactive", "-i", action="store_true",
                        help="Interactive mode: select manifests + resolve conflicts manually")
    lock_p.add_argument("--json", action="store_true", help="Output lock data as JSON")

    graph_p = sub.add_parser("graph", help="Show dependency tree for one or more packages")
    graph_p.add_argument(
        "packages", nargs="+",
        help="Package names (use pkg@ecosystem syntax)",
    )
    graph_p.add_argument(
        "--ecosystem", "-e", default="pypi",
        choices=["pypi", "npm", "cargo", "go", "conda", "maven", "crates", "nuget", "rubygems"],
        help="Default ecosystem",
    )

    verify_p = sub.add_parser("verify", help="Validate lock file — check all versions still exist")
    verify_p.add_argument(
        "lock_file", nargs="?", default="udr-lock.json",
        help="Path to lock file (default: udr-lock.json)",
    )

    list_eco_p = sub.add_parser("list-ecosystems", help="List all supported ecosystems")
    list_eco_p.add_argument("--json", action="store_true", help="Output as JSON")

    update_p = sub.add_parser("update", help="Re-resolve a package and update lock file")
    update_p.add_argument("package", help="Package name to re-resolve")
    update_p.add_argument("--directory", "-d", default=".", help="Project directory with lock file")
    update_p.add_argument("--interactive", "-i", action="store_true",
                          help="Interactive mode for resolving conflicts manually")

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if getattr(args, 'mode', None):
        os.environ["UDR_MODE"] = args.mode

    dispatch = {
        "serve": cmd_serve,
        "check": cmd_check,
        "resolve": cmd_resolve,
        "info": cmd_info,
        "lock": cmd_lock,
        "graph": cmd_graph,
        "verify": cmd_verify,
        "list-ecosystems": cmd_list_ecosystems,
        "update": cmd_update,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
