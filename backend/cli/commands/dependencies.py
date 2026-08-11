"""Show a package's dependencies and constraints."""

import argparse
import asyncio
import json
import sys

from rich import box
from rich.panel import Panel
from rich.table import Table

from ..shared import console


async def _cmd_dependencies_async(args: argparse.Namespace) -> int:
    """Show package dependencies."""
    from backend.core import DataAggregator

    aggregator = DataAggregator()
    package = args.package
    ecosystem = args.ecosystem

    try:
        data = await aggregator.get_package_info(
            package,
            ecosystem=ecosystem,
            include_versions=False,
            include_dependencies=True,
        )
    except Exception as e:
        console.print(f"[red]Failed to fetch dependencies:[/red] {e}")
        return 1
    finally:
        await aggregator.close()

    if not data:
        console.print(f"[yellow]No data found for {package} ({ecosystem})[/yellow]")
        return 1

    deps = data.get("dependencies", {}).get(ecosystem, {})

    flat: dict[str, str] = {}
    if isinstance(deps, dict):
        for category in ("all",):
            for dep in deps.get(category, []) if isinstance(deps.get(category), list) else []:
                if isinstance(dep, str):
                    flat[dep] = "*"
                else:
                    name = getattr(dep, "name", None) or str(dep)
                    spec = getattr(dep, "version_spec", None)
                    flat[name] = spec if spec else "*"
        for cat_name, cat_deps in deps.items():
            if cat_name == "all" or not isinstance(cat_deps, list):
                continue
            for dep in cat_deps:
                if isinstance(dep, str):
                    flat.setdefault(dep, "*")
                else:
                    name = getattr(dep, "name", None) or str(dep)
                    spec = getattr(dep, "version_spec", None)
                    flat.setdefault(name, spec if spec else "*")

    if args.json:
        result = {
            "package": package,
            "ecosystem": ecosystem,
            "dependencies": flat,
        }
        json.dump(result, sys.stdout, indent=2, default=str)
        print()
        return 0

    if not flat:
        console.print(f"[yellow]No dependencies found for {package} ({ecosystem})[/yellow]")
        return 0

    table = Table(
        title=f"{package} ({ecosystem}) — {len(flat)} dependencies",
        box=box.SIMPLE,
    )
    table.add_column("Package", style="cyan")
    table.add_column("Constraint")
    for dep_name, constraint in sorted(flat.items()):
        table.add_row(dep_name, str(constraint))
    console.print(table)

    return 0


def cmd_dependencies(args: argparse.Namespace) -> None:
    """Show package dependencies."""
    try:
        sys.exit(asyncio.run(_cmd_dependencies_async(args)))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Dependencies Error"))
        sys.exit(1)
