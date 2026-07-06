"""Module docstring."""

import asyncio
import json
import os
import sys

from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from ..shared import (
    _aggregator_to_resolver_input,
    _build_resolved_table,
    _extract_severity,
    _parse_package_spec,
    _run_resolution,
    console,
    err_console,
)


def cmd_resolve(args):
    """Cmd resolve."""
    from backend.core import ConflictResolver, DataAggregator, SystemScanner

    async def _resolve():
        """Resolve."""
        aggregator = DataAggregator()
        resolver = ConflictResolver()

        specs = [_parse_package_spec(p, args.ecosystem) for p in args.packages]

        system_info = None
        if any(eco == "pypi" for _, eco, _ in specs):
            scanner = SystemScanner()
            with Progress(
                SpinnerColumn(),
                TextColumn("Scanning system..."),
                transient=True,
                console=err_console,
            ) as p:
                p.add_task("scan", total=None)
                system_info = await scanner.scan_all()

        if not system_info:
            system_info = resolver._get_default_system_info()

        if args.cuda is not None:
            if "gpu" not in system_info:
                system_info["gpu"] = {}
            system_info["gpu"]["available"] = True
            system_info["gpu"]["cuda"] = args.cuda
        if args.device is not None:
            if args.device == "cpu":
                if "gpu" not in system_info:
                    system_info["gpu"] = {}
                system_info["gpu"]["available"] = False
                system_info["gpu"]["cuda"] = ""
            elif args.device == "mps":
                if "gpu" not in system_info:
                    system_info["gpu"] = {}
                system_info["gpu"]["available"] = True
                system_info["gpu"]["cuda"] = ""
                system_info["gpu"]["mps"] = True
            elif args.device == "cuda":
                if "gpu" not in system_info:
                    system_info["gpu"] = {}
                system_info["gpu"]["available"] = True
                if args.cuda is None and not system_info["gpu"].get("cuda"):
                    system_info["gpu"]["cuda"] = "12.1"

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
                """Fetch one."""
                progress.update(
                    fetch_task,
                    description=f"Fetching [cyan]{pkg_name}[/cyan] from [yellow]{eco}[/yellow]...",
                )
                try:
                    data = await aggregator.get_package_info(
                        pkg_name,
                        ecosystem=eco,
                        include_dependencies=True,
                        include_versions=True,
                    )
                    if data:
                        return (pkg_name, data)
                    err_console.print(f"  [yellow]Warning:[/yellow] {pkg_name} not found in {eco}")
                except Exception as exc:
                    err_console.print(f"  [red]Error fetching {pkg_name}:[/red] {exc}")
                return None

            results = await asyncio.gather(*[fetch_one(n, e) for n, e, _ in specs])

            for spec, result in zip(specs, results):
                if result:
                    pkg_name, data = result
                    package_details[pkg_name] = data
                    rinput = _aggregator_to_resolver_input(data, spec[1], spec[2])
                    resolver_inputs.append(rinput)
                progress.advance(fetch_task)

        if not resolver_inputs:
            console.print("[red]No packages could be resolved[/red]")
            await aggregator.close()
            return 1

        with Progress(
            SpinnerColumn(),
            TextColumn("Resolving dependencies with SAT solver..."),
            transient=True,
            console=err_console,
        ) as p:
            p.add_task("SAT solver", total=None)
            resolved = await _run_resolution(
                aggregator,
                resolver,
                resolver_inputs,
                system_info,
                package_details,
                interactive=args.interactive,
                timeout=getattr(args, "timeout", None)
                or int(os.environ.get("SOLVER_TIMEOUT", 120)),
            )

        resolved_pkgs = resolved.get("resolved_packages", {})

        if args.format == "json":
            json.dump(resolved, sys.stdout, indent=2, default=str)
            print()
        else:
            if not resolved_pkgs:
                console.print("[yellow]No packages resolved.[/yellow]")
            else:
                table = _build_resolved_table(resolved)
                if table:
                    console.print(table)

            vulns_found = []
            for pkg_name, detail in package_details.items():
                for v in detail.get("security", {}).get("vulnerabilities", []):
                    if v.get("id"):
                        vulns_found.append((pkg_name, v))
            if vulns_found:
                critical_high = [
                    v for v in vulns_found if _extract_severity(v[1]) in ("CRITICAL", "HIGH")
                ]
                others = len(vulns_found) - len(critical_high)
                console.print(
                    f"\n[red]⚠ {len(vulns_found)} known vulnerabilities"
                    f" ({len(critical_high)} CRITICAL/HIGH, {others} LOW/MEDIUM/UNKNOWN)[/red]"
                )
                for pname, v in critical_high[:10]:
                    sev = _extract_severity(v)
                    console.print(
                        f"  {pname}: {v.get('id', '?')} ([red]{sev}[/red]) — {v.get('summary', '')[:80]}"
                    )
                if len(critical_high) > 10:
                    console.print(f"  ... and {len(critical_high) - 10} more critical/high")

            warnings = resolved.get("warnings", [])
            for w in warnings:
                console.print(f"  [yellow]⚠[/yellow] {w}")

        await aggregator.close()
        if not resolved_pkgs:
            return 1
        return 0

    try:
        sys.exit(asyncio.run(_resolve()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Resolution Error"))
        sys.exit(1)
