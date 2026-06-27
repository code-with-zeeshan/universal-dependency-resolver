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
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Confirm
from rich.table import Table
from rich import box

console = Console()
err_console = Console(stderr=True)


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
        ver = vinfo.get("version", "")
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
            except Exception:
                pass

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


def cmd_serve(args):
    from backend.api.main import app
    import uvicorn
    console.print("[bold green]Starting UDR API server...[/bold green]")
    console.print(f"  Mode: [cyan]{args.mode}[/cyan]")
    console.print(f"  Host: [yellow]{args.host}[/yellow]  Port: [yellow]{args.port}[/yellow]")
    os.environ["UDR_MODE"] = args.mode
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


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

        # Platform info
        table = Table(title="System Compatibility", box=box.ROUNDED)
        table.add_column("Component", style="cyan")
        table.add_column("Value")
        table.add_column("Status", style="bold")

        table.add_row("OS", f"{info['platform']['system']} {info['platform']['release']}", "✅")
        arch = info['platform'].get('machine', info['cpu']['arch'])
        table.add_row("Architecture", arch, "✅")
        table.add_row("CPU", f"{info['cpu']['brand']} ({info['cpu']['count']} cores)", "✅")

        mem = info.get("memory", {})
        if mem:
            total = mem.get("total", 0) / (1024**3)
            avail = mem.get("available", 0) / (1024**3)
            pct = mem.get("percent", 0)
            mem_status = "⚠" if pct > 90 else "✅"
            table.add_row("Memory", f"{total:.1f} GB total, {avail:.1f} GB free", mem_status)

        if info["gpu"]["available"]:
            gpu = info["gpu"]["devices"][0]
            cuda = info["gpu"].get("cuda", "not found")
            table.add_row("GPU", f"{gpu['name']} ({gpu['memory_total']} MB)", "✅")
            table.add_row("CUDA", cuda, "✅" if cuda and cuda != "not found" else "⚠")
        else:
            table.add_row("GPU", "None detected", "ℹ")

        py = info["runtime_versions"]["python"]
        table.add_row("Python", py['version'], "✅")

        if args.verbose:
            table.add_row("Python path", py['location'], "")
            table.add_row("CPU arch", info['cpu']['arch'], "")

        console.print(table)

        if args.verbose:
            # Runtime versions table
            rt_table = Table(title="Runtime Versions", box=box.SIMPLE)
            rt_table.add_column("Runtime", style="cyan")
            rt_table.add_column("Version")
            for rt_name, rt_info in info.get("runtime_versions", {}).items():
                if isinstance(rt_info, dict) and rt_info.get("version"):
                    rt_table.add_row(rt_name, rt_info["version"])
            console.print(rt_table)

        return True

    try:
        asyncio.run(_check())
        sys.exit(0)
    except Exception as e:
        console.print(Panel(f"[red]Check failed:[/red] {e}", title="Error"))
        sys.exit(1)


def _output_json(data: Any, args) -> None:
    """Print JSON output and exit if --json was passed."""
    json.dump(data, sys.stdout, indent=2, default=str)
    print()
    sys.exit(0)


def cmd_resolve(args):
    from backend.core import DataAggregator, ConflictResolver

    async def _resolve():
        aggregator = DataAggregator()
        resolver = ConflictResolver()
        scanner = None

        specs = [_parse_package_spec(p, args.ecosystem) for p in args.packages]

        system_info = None
        if any(eco == "pypi" for _, eco in specs):
            from backend.core import SystemScanner
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

            for pkg_name, eco in specs:
                progress.update(fetch_task, description=f"Fetching [cyan]{pkg_name}[/cyan] from [yellow]{eco}[/yellow]...")
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
                    else:
                        console.print(f"  [yellow]Warning:[/yellow] {pkg_name} not found in {eco}")
                except Exception as e:
                    console.print(f"  [red]Error fetching {pkg_name}:[/red] {e}")
                progress.advance(fetch_task)

        if not resolver_inputs:
            console.print("[red]No packages could be resolved[/red]")
            return 1

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True, console=err_console) as p:
            p.add_task("Resolving dependencies with SAT solver...", total=None)
            try:
                resolved = await _resolve_transitive(
                    aggregator, resolver, resolver_inputs, system_info
                )
            except Exception as e:
                console.print(f"[yellow]SAT resolution fell back to alternatives:[/yellow] {e}")
                resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)

        resolved = _apply_cuda_variants(resolved, package_details, system_info)

        if args.interactive and resolved.get("status") == "unsatisfiable":
            console.print(Panel("[yellow]SAT solver found no valid combination.[/yellow]\n"
                                "Let's resolve manually by selecting alternatives.", title="Interactive"))
            resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)

        if args.format == "json":
            json.dump(resolved, sys.stdout, indent=2, default=str)
            print()
        else:
            rp = resolved.get("resolved_packages", {})
            if not rp:
                console.print("[yellow]No packages resolved.[/yellow]")
            else:
                table = Table(title=f"Resolved {len(rp)} packages", box=box.ROUNDED)
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

                console.print(table)

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

        table = Table(title=f"System: {info['platform']['system']} {info['platform']['release']}", box=box.ROUNDED)
        table.add_column("Property", style="cyan")
        table.add_column("Value")

        table.add_row("Architecture", info['platform']['machine'])
        table.add_row("CPU", f"{info['cpu']['brand']} ({info['cpu']['count']} cores)")
        table.add_row("Python", info['runtime_versions']['python']['version'])
        table.add_row("Python path", info['runtime_versions']['python']['location'])

        if info["gpu"]["available"]:
            gpu = info["gpu"]["devices"][0]
            table.add_row("GPU", f"{gpu['name']} ({gpu['memory_total']} MB)")
            cuda = info["gpu"].get("cuda", "not found")
            if cuda and cuda != "not found":
                table.add_row("CUDA", cuda)

        console.print(table)

        import tomllib
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if pyproject.is_file():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            deps = data.get("project", {}).get("dependencies", [])
            dep_table = Table(title=f"Installed ({len(deps)} core packages)", box=box.SIMPLE)
            dep_table.add_column("Dependency", style="cyan")
            for d in deps:
                dep_table.add_row(d)
            console.print(dep_table)

    asyncio.run(_info())


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

        manifest_table = Table(title=f"Found {len(manifests)} manifest(s)", box=box.SIMPLE)
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

            for pkg in packages:
                key = (pkg["name"], pkg["ecosystem"])
                if key in seen:
                    progress.advance(fetch_task)
                    continue
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
                        package_details[pkg["name"]] = data
                        rinput = _aggregator_to_resolver_input(data, pkg["ecosystem"])
                        resolver_inputs.append(rinput)
                except Exception as e:
                    console.print(f"  [red]Error fetching {pkg['name']}:[/red] {e}")
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
            try:
                resolved = await _resolve_transitive(
                    aggregator, resolver, resolver_inputs, system_info
                )
            except Exception as e:
                console.print(f"[yellow]SAT solver failed: {e}. Using alternatives.[/yellow]")
                resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)

        resolved = _apply_cuda_variants(resolved, package_details, system_info)

        # 6. Interactive conflict resolution
        if args.interactive and resolved.get("status") == "unsatisfiable":
            console.print(Panel("[yellow]SAT solver found conflicts.[/yellow]\n"
                                "Attempting alternative resolution...", title="Conflict Detected"))
            resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)

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

        # 8. JSON output
        if getattr(args, 'json', False):
            return _output_json(lock_data, args)

        # 9. Write lock file
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

        # 10. Export if requested
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

        # 11. Prompt to update manifests
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


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="udr",
        description="Universal Dependency Resolver — resolve dependencies across ecosystems",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="Start the API server")
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind address")
    serve_p.add_argument("--port", type=int, default=8000, help="Bind port")
    serve_p.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    serve_p.add_argument("--mode", choices=["local", "saas"], default="local",
                         help="Run mode: local (no auth, default) or saas (full auth stack)")

    check_p = sub.add_parser("check", help="Check system compatibility")
    check_p.add_argument("-v", "--verbose", action="store_true", help="Show detailed info")
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

    info_p = sub.add_parser("info", help="Show system information")
    info_p.add_argument("--json", action="store_true", help="Output as JSON")

    lock_p = sub.add_parser("lock", help="Auto-detect manifests, resolve all dependencies, write lock file")
    lock_p.add_argument("--directory", "-d", default=".", help="Project directory to scan")
    lock_p.add_argument("--manifest", "-m", help="Only process a specific manifest file")
    lock_p.add_argument("--export", help="Export to a specific format (e.g. requirements.txt, Dockerfile)")
    lock_p.add_argument("--yes", "-y", action="store_true", help="Update manifests without prompting")
    lock_p.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    lock_p.add_argument("--interactive", "-i", action="store_true",
                        help="Interactive mode for resolving conflicts manually")
    lock_p.add_argument("--json", action="store_true", help="Output lock data as JSON")

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
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
