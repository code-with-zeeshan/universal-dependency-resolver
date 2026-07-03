"""Search for packages across ecosystems."""

import asyncio
import json
import sys

from rich import box
from rich.panel import Panel
from rich.table import Table

from ..shared import console, err_console


async def _cmd_search_async(args):
    """Search packages across ecosystems."""
    from backend.core import DataAggregator

    aggregator = DataAggregator()
    query = args.query
    ecosystems = args.ecosystems
    limit = args.limit

    err_console.print(f"[dim]Searching for '{query}'...[/dim]")

    try:
        results = await aggregator.search_packages(
            query,
            ecosystems=ecosystems.split(",") if ecosystems else None,
            limit=limit,
        )
    except Exception as e:
        console.print(f"[red]Search failed:[/red] {e}")
        return 1
    finally:
        await aggregator.close()

    total = sum(len(items) for items in results.values() if isinstance(items, list))

    if getattr(args, "json", False):
        json.dump(results, sys.stdout, indent=2, default=str)
        print()
        return 0 if total > 0 else 1

    if total == 0:
        console.print(f"[yellow]No results found for '{query}'[/yellow]")
        return 1

    console.print(f"\n[bold]Search results for '{query}'[/bold] ([green]{total}[/green] found)\n")

    for eco, items in sorted(results.items()):
        if not isinstance(items, list) or not items:
            continue
        table = Table(title=f"{eco} ({len(items)})", box=box.SIMPLE)
        table.add_column("Package", style="cyan")
        table.add_column("Version", style="green")
        table.add_column("Description")
        for item in items[:20]:
            name = item.get("name", "?")
            ver = item.get("latest_version", item.get("version", "?"))
            desc = item.get("description", "")
            if desc and len(desc) > 80:
                desc = desc[:77] + "..."
            table.add_row(name, str(ver), desc or "")
        console.print(table)
        console.print()

    return 0


def cmd_search(args):
    """Search packages."""
    try:
        sys.exit(asyncio.run(_cmd_search_async(args)))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Search Error"))
        sys.exit(1)
