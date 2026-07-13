"""Show detailed package info — versions, dependencies, metadata."""

import argparse
import asyncio
import json
import sys

from rich import box
from rich.panel import Panel
from rich.table import Table

from ..shared import console, err_console


async def _cmd_details_async(args: argparse.Namespace) -> int:
    """Show package details."""
    from backend.core import DataAggregator

    aggregator = DataAggregator()
    package = args.package
    ecosystem = args.ecosystem

    err_console.print(f"[dim]Fetching details for {package} ({ecosystem})...[/dim]")

    try:
        data = await aggregator.get_package_info(
            package,
            ecosystem=ecosystem,
            include_versions=True,
            include_dependencies=True,
        )
    except Exception as e:
        console.print(f"[red]Failed to fetch details:[/red] {e}")
        return 1
    finally:
        await aggregator.close()

    if not data:
        console.print(f"[yellow]No data found for {package} ({ecosystem})[/yellow]")
        return 1

    if args.json:
        json.dump(data, sys.stdout, indent=2, default=str)
        print()
        return 0

    name = data.get("name", package)
    console.print(f"\n[bold]Package:[/bold] {name}  [dim]({ecosystem})[/dim]\n")

    summary = data.get("summary") or data.get("description", "")
    if summary:
        console.print(Panel(summary[:500], title="Description"))

    ver_list = data.get("versions", {}).get(ecosystem, [])
    if ver_list:
        version_strings = [
            v.get("version", "") if isinstance(v, dict) else str(v) for v in ver_list
        ]
        from packaging.version import parse as parse_version

        sorted_vers = sorted(
            [v for v in version_strings if v],
            key=lambda x: parse_version(x),
            reverse=True,
        )
        latest = sorted_vers[0] if sorted_vers else "?"
        total = len(sorted_vers)
        console.print(f"\n[bold]Latest version:[/bold] [green]{latest}[/green]")
        console.print(f"[bold]Total versions:[/bold] {total}")

        if total <= 10:
            table = Table(box=box.SIMPLE)
            table.add_column("Version", style="cyan")
            for v in sorted_vers:
                table.add_row(v)
            console.print(table)

    deps = data.get("dependencies", {}).get(ecosystem, {})
    if deps:
        table = Table(title="Dependencies", box=box.SIMPLE)
        table.add_column("Package", style="cyan")
        table.add_column("Constraint")
        for dep_name, constraint in list(deps.items())[:30]:
            table.add_row(dep_name, str(constraint))
        console.print(table)
        if len(deps) > 30:
            console.print(f"[dim]... and {len(deps) - 30} more dependencies[/dim]")

    return 0


def cmd_details(args: argparse.Namespace) -> None:
    """Show package details."""
    try:
        sys.exit(asyncio.run(_cmd_details_async(args)))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Details Error"))
        sys.exit(1)
