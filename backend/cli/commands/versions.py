"""List available versions of a package."""

import argparse
import asyncio
import json
import sys

from rich import box
from rich.panel import Panel
from rich.table import Table

from ..shared import console


async def _cmd_versions_async(args: argparse.Namespace) -> int:
    """List package versions."""
    from backend.core import DataAggregator

    aggregator = DataAggregator()
    package = args.package
    ecosystem = args.ecosystem

    try:
        data = await aggregator.get_package_info(
            package,
            ecosystem=ecosystem,
            include_versions=True,
            include_dependencies=False,
        )
    except Exception as e:
        console.print(f"[red]Failed to fetch versions:[/red] {e}")
        return 1
    finally:
        await aggregator.close()

    if not data:
        console.print(f"[yellow]No data found for {package} ({ecosystem})[/yellow]")
        return 1

    ver_list = data.get("versions", {}).get(ecosystem, [])
    version_strings = [v.get("version", "") if isinstance(v, dict) else str(v) for v in ver_list]
    version_strings = [v for v in version_strings if v]

    if not version_strings:
        if args.json:
            result = {"package": package, "ecosystem": ecosystem, "error": "No versions found"}
            json.dump(result, sys.stdout, indent=2, default=str)
            print()
        else:
            console.print(f"[yellow]No versions found for {package} ({ecosystem})[/yellow]")
        return 1

    if args.json:
        from packaging.version import parse as parse_version

        sorted_vers = sorted(
            version_strings,
            key=lambda x: parse_version(x),
            reverse=True,
        )
        result = {
            "package": package,
            "ecosystem": ecosystem,
            "versions": sorted_vers,
        }
        json.dump(result, sys.stdout, indent=2, default=str)
        print()
        return 0

    from packaging.version import parse as parse_version

    sorted_vers = sorted(
        version_strings,
        key=lambda x: parse_version(x),
        reverse=True,
    )
    table = Table(
        title=f"{package} ({ecosystem}) — {len(sorted_vers)} versions",
        box=box.SIMPLE,
    )
    table.add_column("#", style="dim", justify="right")
    table.add_column("Version", style="cyan")
    for i, v in enumerate(sorted_vers, start=1):
        table.add_row(str(i), v)
    console.print(table)

    return 0


def cmd_versions(args: argparse.Namespace) -> None:
    """List package versions."""
    try:
        sys.exit(asyncio.run(_cmd_versions_async(args)))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Versions Error"))
        sys.exit(1)
