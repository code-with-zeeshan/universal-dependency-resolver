"""Module docstring."""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from packaging.version import Version
from rich import box
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from backend.settings import SOLVER_TIMEOUT

from ..shared import (
    _fetch_package_data_async,
    _read_lock_file,
    _resolve_lock_path,
    _run_resolution,
    console,
    err_console,
)


def _extract_fixed_version(vuln: dict) -> str | None:
    """Extract the first fixed version from an OSV vulnerability entry."""
    for a in vuln.get("affected", []):
        for r in a.get("ranges", []):
            if r.get("type") == "ECOSYSTEM":
                for e in r.get("events", []):
                    if "fixed" in e:
                        return e["fixed"]
    return None


def cmd_update(args: argparse.Namespace):
    """Cmd update."""

    if args.fix_cve:
        sys.exit(asyncio.run(_fix_cve(args)))

    async def _update():
        """Update."""
        from backend.core import DataAggregator, SystemScanner
        from backend.core.conflict_resolver import ConflictResolver
        from backend.orchestrator.resolve import create_solver

        directory = Path(args.directory).resolve()
        lock_path = _resolve_lock_path(
            directory,
            workspace=args.workspace,
            lock_file=args.lock_file,
        ).resolve()
        lock_data = _read_lock_file(lock_path)
        aggregator = DataAggregator()
        resolver = create_solver()
        scanner = SystemScanner()

        package_name = args.package
        if not package_name:
            console.print(
                "[red]No package specified. Use --fix-cve to auto-fix vulnerable packages, or provide a package name.[/red]"
            )
            await aggregator.close()
            return 1

        packages_in_lock = lock_data.get("packages", {})
        if package_name not in packages_in_lock:
            console.print(f"[red]Package '{package_name}' not found in lock file[/red]")
            await aggregator.close()
            return 1

        pkg_info = packages_in_lock[package_name]
        ecosystem = pkg_info.get("ecosystem", "pypi")
        console.print(f"Re-resolving [cyan]{package_name}[/cyan] ([yellow]{ecosystem}[/yellow])...")

        with Progress(
            SpinnerColumn(),
            TextColumn("Scanning system..."),
            transient=True,
            console=err_console,
        ) as p:
            p.add_task("system", total=None)
            system_info = await scanner.scan_all()

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
                system_info["gpu"]["type"] = "mps"
                system_info["gpu"]["cuda"] = ""
                system_info["gpu"]["metal"] = "3.0"
            elif args.device == "rocm":
                if "gpu" not in system_info:
                    system_info["gpu"] = {}
                system_info["gpu"]["available"] = True
                system_info["gpu"]["type"] = "rocm"
                system_info["gpu"]["cuda"] = ""
                system_info["gpu"]["rocm"] = "6.0.0"
            elif args.device == "cuda":
                if "gpu" not in system_info:
                    system_info["gpu"] = {"available": True, "type": "cuda"}
                system_info["gpu"]["available"] = True
                system_info["gpu"]["type"] = "cuda"

        existing_constraint = pkg_info.get("original_constraint")
        constraint = existing_constraint or f">={pkg_info.get('resolved_version', '0.0.0')}"
        specs = [(package_name, ecosystem, constraint)]
        resolver_inputs, package_details = await _fetch_package_data_async(aggregator, specs)

        if not resolver_inputs:
            console.print(f"[red]Could not fetch metadata for {package_name}[/red]")
            await aggregator.close()
            return 1

        err_console.print("[dim]Running SAT resolution...[/dim]")
        resolved = await _run_resolution(
            aggregator,
            resolver,
            resolver_inputs,
            system_info,
            package_details,
            interactive=args.interactive,
            lock_data=lock_data,
            timeout=args.timeout or SOLVER_TIMEOUT,
        )

        rp = resolved.get("resolved_packages", {})
        new_version = rp.get(package_name, {}).get("version") if rp else None

        if not new_version:
            console.print(f"[red]Could not resolve {package_name}[/red]")
            await aggregator.close()
            return 1

        old_version = pkg_info.get("resolved_version")
        if new_version == old_version:
            console.print(
                f"[green]{package_name} is already at version {new_version} — no update needed[/green]"
            )
            await aggregator.close()
            return 0

        console.print(
            f"[green]Update available:[/green] {old_version} → [bold]{new_version}[/bold]"
        )

        # Re-resolve all affected transitive deps by updating the lock
        lock_data["packages"][package_name]["resolved_version"] = new_version
        lock_data["packages"][package_name]["cuda_variant"] = rp.get(package_name, {}).get(
            "cuda_variant", False
        )
        lock_data["packages"][package_name]["cuda_version"] = rp.get(package_name, {}).get(
            "cuda_version"
        )
        lock_data["generated_at"] = datetime.now().isoformat()

        # Update transitive deps for the updated package
        for pname, pinfo in rp.items():
            if pname == package_name:
                continue
            if pname not in lock_data["packages"]:
                lock_data["packages"][pname] = {
                    "name": pname,
                    "ecosystem": pinfo.get("ecosystem", ecosystem),
                    "direct": False,
                }
            lock_data["packages"][pname]["resolved_version"] = pinfo.get("version")
            lock_data["packages"][pname]["cuda_variant"] = pinfo.get("cuda_variant", False)
            lock_data["packages"][pname]["cuda_version"] = pinfo.get("cuda_version")

        # Recompute resolution hash for the updated package
        for rinput in resolver_inputs:
            if rinput["name"] == package_name:
                lock_data["packages"][package_name]["resolution_hash"] = (
                    ConflictResolver.compute_resolution_hash(
                        rinput["name"],
                        rinput["ecosystem"],
                        rinput.get("version_constraint", "*"),
                        rinput.get("dependencies", {}),
                        system_info,
                    )
                )

        if args.dry_run:
            console.print("[yellow]── dry run — lock file not modified ──[/yellow]")
            await aggregator.close()
            return 0

        lock_path.write_text(json.dumps(lock_data, indent=2, default=str))
        console.print(f"[green]Updated lock file:[/green] {lock_path}")
        transitive_count = sum(
            1
            for p in lock_data["packages"].values()
            if not p.get("direct", True) and p.get("resolved_version")
        )
        console.print(
            f"  {package_name}: {old_version} → {new_version} "
            f"({transitive_count} transitive dep(s) refreshed)"
        )
        await aggregator.close()
        return 0

    try:
        sys.exit(asyncio.run(_update()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Update Error"))
        sys.exit(1)


async def _fix_cve(args: argparse.Namespace):
    """Fix vulnerable packages by updating to versions that fix known CVEs."""
    from backend.core import DataAggregator, SystemScanner
    from backend.orchestrator.resolve import create_solver

    directory = Path(args.directory).resolve()
    lock_path = _resolve_lock_path(
        directory,
        workspace=args.workspace,
        lock_file=args.lock_file,
    ).resolve()
    lock_data = _read_lock_file(lock_path)
    aggregator = DataAggregator()
    resolver = create_solver()
    scanner = SystemScanner()

    packages = lock_data.get("packages", {})
    if not packages:
        console.print("[yellow]Lock file has no packages to check.[/yellow]")
        await aggregator.close()
        return 0

    with Progress(
        SpinnerColumn(),
        TextColumn("Scanning system..."),
        transient=True,
        console=err_console,
    ) as p:
        p.add_task("system", total=None)
        system_info = await scanner.scan_all()

    target_package = args.package

    # Determine which packages to check
    if target_package:
        if target_package not in packages:
            console.print(f"[red]Package '{target_package}' not found in lock file[/red]")
            await aggregator.close()
            return 1
        to_check = {target_package: packages[target_package]}
    else:
        to_check = packages

    # Scan each package for CVEs and find the max fixed version
    to_fix: list[tuple[str, str, str, str]] = []  # (name, eco, old_ver, fixed_ver)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=err_console,
    )
    with progress:
        check_task = progress.add_task(
            f"Checking {len(to_check)} packages for CVEs...", total=len(to_check)
        )

        async def _check_one(name: str, info: dict):
            eco = info.get("ecosystem", "pypi")
            ver = info.get("resolved_version", "")
            try:
                vulns = await aggregator.check_vulnerabilities(name, eco, ver)
                fixed_versions: set[str] = set()
                for v in vulns:
                    fv = _extract_fixed_version(v)
                    if fv:
                        fixed_versions.add(fv)
                if fixed_versions:
                    best = max(fixed_versions, key=lambda v: Version(v))
                    try:
                        current = Version(ver) if ver else Version("0.0.0")
                        target_v = Version(best)
                        if target_v > current:
                            to_fix.append((name, eco, ver, str(target_v)))
                    except Exception:
                        logger.warning(
                            "Failed to parse version for CVE fix: %s %s", name, ver, exc_info=True
                        )
            except Exception:
                err_console.print(f"[dim]Warning: CVE check failed for {name}[/dim]")
            progress.advance(check_task)

        if target_package:
            await _check_one(target_package, packages[target_package])
        else:
            await asyncio.gather(
                *[_check_one(n, i) for n, i in to_check.items()],
                return_exceptions=True,
            )

    if not to_fix:
        console.print("[green]✅ No vulnerable packages need updating.[/green]")
        await aggregator.close()
        return 0

    console.print(f"[yellow]Found {len(to_fix)} package(s) with fixable CVEs[/yellow]")

    # Build specs with new constraints
    specs: list[tuple[str, str, str | None]] = []
    constraint_map: dict[str, str] = {}
    for name, eco, old_ver, fixed_ver in to_fix:
        existing_constraint = packages[name].get("original_constraint")
        if existing_constraint and existing_constraint.startswith("=="):
            constraint = f"=={fixed_ver}"
        else:
            constraint = f">={fixed_ver}"
        specs.append((name, eco, constraint))
        constraint_map[name] = constraint

    # Fetch package data for all packages to update
    resolver_inputs, package_details = await _fetch_package_data_async(aggregator, specs)

    if not resolver_inputs:
        console.print("[red]Could not fetch metadata for packages[/red]")
        await aggregator.close()
        return 1

    err_console.print("[dim]Running SAT resolution...[/dim]")
    resolved = await _run_resolution(
        aggregator,
        resolver,
        resolver_inputs,
        system_info,
        package_details,
        interactive=args.interactive,
        lock_data=lock_data,
        timeout=args.timeout or SOLVER_TIMEOUT,
    )

    rp = resolved.get("resolved_packages", {})
    if not rp:
        console.print("[red]Resolution failed — could not resolve updates[/red]")
        await aggregator.close()
        return 1

    # Build summary table
    table = Table(title="CVE Fix Results", box=box.ROUNDED)
    table.add_column("Package", style="cyan")
    table.add_column("Ecosystem")
    table.add_column("Old Version")
    table.add_column("New Version", style="bold green")
    table.add_column("Status")

    updated_count = 0
    unchanged_count = 0
    failed_count = 0
    all_new_transitive: dict[str, dict] = {}

    for name, eco, old_ver, fixed_ver in to_fix:
        new_version = rp.get(name, {}).get("version")
        if not new_version:
            table.add_row(name, eco, old_ver, "", "[red]failed[/red]")
            failed_count += 1
            continue

        if new_version == old_ver:
            table.add_row(name, eco, old_ver, new_version, "[yellow]unchanged[/yellow]")
            unchanged_count += 1
            continue

        lock_data["packages"][name]["resolved_version"] = new_version
        lock_data["packages"][name]["original_constraint"] = constraint_map[name]
        lock_data["packages"][name]["cuda_variant"] = rp.get(name, {}).get("cuda_variant", False)
        lock_data["packages"][name]["cuda_version"] = rp.get(name, {}).get("cuda_version")
        table.add_row(name, eco, old_ver, new_version, "[green]fixed[/green]")
        updated_count += 1

        # Collect transitive deps
        for pname, pinfo in rp.items():
            if pname == name:
                continue
            if pname not in all_new_transitive:
                all_new_transitive[pname] = pinfo

    # Write transitive deps into lock data
    for pname, pinfo in all_new_transitive.items():
        if pname not in lock_data["packages"]:
            lock_data["packages"][pname] = {
                "name": pname,
                "ecosystem": pinfo.get("ecosystem", "pypi"),
                "direct": False,
            }
        lock_data["packages"][pname]["resolved_version"] = pinfo.get("version")
        lock_data["packages"][pname]["cuda_variant"] = pinfo.get("cuda_variant", False)
        lock_data["packages"][pname]["cuda_version"] = pinfo.get("cuda_version")

    lock_data["generated_at"] = datetime.now().isoformat()

    if args.dry_run:
        console.print("[yellow]── dry run — lock file not modified ──[/yellow]")
    else:
        lock_path.write_text(json.dumps(lock_data, indent=2, default=str))

    console.print(table)
    parts = []
    if updated_count:
        parts.append(f"[green]{updated_count} fixed[/green]")
    if unchanged_count:
        parts.append(f"[yellow]{unchanged_count} unchanged[/yellow]")
    if failed_count:
        parts.append(f"[red]{failed_count} failed[/red]")
    console.print(" — ".join(parts))

    if not args.dry_run and updated_count > 0:
        console.print(f"\n[green]Updated lock file:[/green] {lock_path}")

    await aggregator.close()
    return 0 if failed_count == 0 else 1
