"""Module docstring."""
import asyncio
import json
import sys
from pathlib import Path

from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..shared import (
    console,
    err_console,
    _read_lock_file,
    _fetch_package_data_async,
    _run_resolution,
)


def cmd_update(args):
    """Cmd update."""
    async def _update():
        """Update."""
        from backend.core import DataAggregator, ConflictResolver, SystemScanner

        lock_path = Path(args.directory) / "udr.lock"
        lock_data = _read_lock_file(lock_path)
        aggregator = DataAggregator()
        resolver = ConflictResolver()
        scanner = SystemScanner()

        package_name = args.package
        packages_in_lock = lock_data.get("packages", {})
        if package_name not in packages_in_lock:
            console.print(f"[red]Package '{package_name}' not found in lock file[/red]")
            await aggregator.close()
            return 1

        pkg_info = packages_in_lock[package_name]
        ecosystem = pkg_info.get("ecosystem", "pypi")
        console.print(
            f"Re-resolving [cyan]{package_name}[/cyan] ([yellow]{ecosystem}[/yellow])..."
        )

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
            elif args.device == "cuda":
                if "gpu" not in system_info:
                    system_info["gpu"] = {"available": True, "type": "cuda"}
                system_info["gpu"]["available"] = True
                system_info["gpu"]["type"] = "cuda"

        specs = [(package_name, ecosystem, None)]
        resolver_inputs, package_details = await _fetch_package_data_async(
            aggregator, specs
        )

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
            interactive=getattr(args, "interactive", False),
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
        lock_data["packages"][package_name]["cuda_variant"] = rp.get(
            package_name, {}
        ).get("cuda_variant", False)
        lock_data["packages"][package_name]["cuda_version"] = rp.get(
            package_name, {}
        ).get("cuda_version")
        lock_data["generated_at"] = __import__("datetime").datetime.now().isoformat()

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

        if getattr(args, "dry_run", False):
            console.print("[yellow]── dry run — lock file not modified ──[/yellow]")
            await aggregator.close()
            return 0

        lock_path.write_text(json.dumps(lock_data, indent=2, default=str))
        console.print(
            f"[green]Updated lock file:[/green] {lock_path}"
        )
        transitive_count = sum(
            1 for p in lock_data["packages"].values()
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
