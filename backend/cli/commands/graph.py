import asyncio
import sys

from rich.panel import Panel
from rich.tree import Tree

from ..shared import (
    console,
    err_console,
    _parse_package_spec,
    _fetch_package_data_async,
    _resolve_transitive,
)


def cmd_graph(args):
    from backend.core import DataAggregator, ConflictResolver

    async def _graph():
        aggregator = DataAggregator()
        resolver = ConflictResolver()
        system_info = resolver._get_default_system_info()

        specs = [_parse_package_spec(p, args.ecosystem) for p in args.packages]
        resolver_inputs, package_details = await _fetch_package_data_async(
            aggregator, specs
        )

        if not resolver_inputs:
            console.print("[red]No packages could be resolved[/red]")
            return

        err_console.print("[dim]Resolving dependencies for dependency tree...[/dim]")
        resolved = await _resolve_transitive(
            aggregator,
            resolver,
            resolver_inputs,
            system_info,
        )

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
        await aggregator.close()

    try:
        asyncio.run(_graph())
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Graph Error"))
        sys.exit(1)
