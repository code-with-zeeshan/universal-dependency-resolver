"""List packages with newer versions available in registries."""

import asyncio
import json
import sys
from pathlib import Path

from packaging.version import parse as parse_version
from rich import box
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..shared import _read_lock_file, console, err_console


async def _cmd_outdated_async(args):
    """Cmd outdated async."""
    from backend.core import DataAggregator

    lock_path = Path(args.directory) / "udr.lock"
    if not lock_path.is_file():
        console.print(f"[red]Lock file not found:[/red] {lock_path}")
        return 1

    lock_data = _read_lock_file(lock_path)
    aggregator = DataAggregator()

    packages = lock_data.get("packages", {})
    ecosystem_filter = getattr(args, "ecosystem", None)
    outdated_list = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[green]{task.completed}/{task.total}[/green]"),
        console=err_console,
    ) as progress:
        check_task = progress.add_task("Checking for updates...", total=len(packages))

        async def check_pkg(name: str, info: dict):
            """Check pkg."""
            eco = info.get("ecosystem", "pypi")
            if ecosystem_filter and eco != ecosystem_filter:
                progress.advance(check_task)
                return
            ver = info.get("resolved_version")
            if not ver:
                progress.advance(check_task)
                return
            try:
                data = await aggregator.get_package_info(name, ecosystem=eco, include_versions=True)
                if data:
                    versions = data.get("versions", {}).get(eco, [])
                    version_strings = [
                        v.get("version", "") if isinstance(v, dict) else str(v) for v in versions
                    ]
                    current = parse_version(ver)
                    newer = sorted(
                        [v for v in version_strings if v],
                        key=lambda x: parse_version(x),
                        reverse=True,
                    )
                    latest_str = newer[0] if newer else ver
                    latest_ver = parse_version(latest_str)
                    if latest_ver > current:
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
                pass
            progress.advance(check_task)

        await asyncio.gather(*[check_pkg(n, i) for n, i in packages.items()])

    await aggregator.close()
    outdated_list.sort(key=lambda x: x["name"])

    if getattr(args, "json", False):
        json.dump(outdated_list, sys.stdout, indent=2, default=str)
        print()
        return 0 if not outdated_list else 1

    if not outdated_list:
        console.print("[green]All packages are up to date.[/green]")
        return 0

    table = Table(
        title=f"[yellow]{len(outdated_list)} outdated package(s)[/yellow]",
        box=box.ROUNDED,
    )
    table.add_column("Package", style="cyan")
    table.add_column("Ecosystem")
    table.add_column("Current", style="red")
    table.add_column("Latest", style="green")
    table.add_column("Type")
    for p in outdated_list:
        table.add_row(p["name"], p["ecosystem"], p["current"], p["latest"], p["type"])
    console.print(table)
    console.print("\n[yellow]Run 'udr update <package>' to update a package[/yellow]")
    return 1


def cmd_outdated(args):
    """Cmd outdated."""
    try:
        sys.exit(asyncio.run(_cmd_outdated_async(args)))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Outdated Error"))
        sys.exit(1)
