"""Module docstring."""

import argparse
import asyncio
import json
import sys

from rich.panel import Panel
from rich.tree import Tree

from ..shared import (
    _fetch_package_data_async,
    _parse_package_spec,
    _resolve_transitive,
    console,
    err_console,
)


def _build_recursive_tree(
    rp: dict, name: str, info: dict, max_depth: int = 5, _depth: int = 0
) -> Tree:
    """Build recursive dependency tree."""
    eco = info.get("ecosystem", "?")
    ver = info.get("version", "?")
    node_label = f"[cyan]{name}[/cyan] [yellow]{ver}[/yellow] ({eco})"
    node = Tree(node_label) if _depth == 0 else node_label
    if _depth >= max_depth:
        return node
    deps = info.get("dependencies", {}).get(eco, {})
    if not deps:
        return node
    if _depth == 0:
        for dep_name, dep_ver in deps.items():
            dep_info_sub = rp.get(dep_name, {})
            if dep_info_sub and dep_info_sub.get("dependencies"):
                sub = _build_recursive_tree(rp, dep_name, dep_info_sub, max_depth, _depth + 1)
                node.add(sub)
            else:
                node.add(f"[white]{dep_name}[/white] [dim]{dep_ver}[/dim]")
    else:
        children = []
        for dep_name, dep_ver in deps.items():
            dep_info_sub = rp.get(dep_name, {})
            if dep_info_sub and dep_info_sub.get("dependencies"):
                sub = _build_recursive_tree(rp, dep_name, dep_info_sub, max_depth, _depth + 1)
                children.append(sub)
            else:
                children.append(f"[white]{dep_name}[/white] [dim]{dep_ver}[/dim]")
        if children:
            sub_tree = Tree(node_label)
            for c in children:
                sub_tree.add(c)
            return sub_tree
    return node


def cmd_graph(args: argparse.Namespace):
    """Cmd graph."""
    from backend.core import DataAggregator
    from backend.orchestrator.resolve import create_solver

    async def _graph():
        """Graph."""
        aggregator = DataAggregator()
        resolver = create_solver()
        system_info = resolver._get_default_system_info()

        if args.cuda is not None:
            if "gpu" not in system_info:
                system_info["gpu"] = {}
            system_info["gpu"]["available"] = True
            system_info["gpu"]["cuda"] = args.cuda
        if args.device is not None:
            if "gpu" not in system_info:
                system_info["gpu"] = {}
            if args.device == "cpu":
                system_info["gpu"]["available"] = False
                system_info["gpu"]["cuda"] = ""
            elif args.device == "mps":
                system_info["gpu"]["available"] = True
                system_info["gpu"]["cuda"] = ""
                system_info["gpu"]["mps"] = True
                system_info["gpu"]["metal"] = "3.0"
            elif args.device == "rocm":
                system_info["gpu"]["available"] = True
                system_info["gpu"]["cuda"] = ""
                system_info["gpu"]["rocm"] = "6.0.0"
            elif args.device == "cuda":
                system_info["gpu"]["available"] = True
                if not system_info["gpu"].get("cuda"):
                    system_info["gpu"]["cuda"] = "12.1"

        specs = [_parse_package_spec(p, args.ecosystem) for p in args.packages]
        resolver_inputs, _package_details = await _fetch_package_data_async(aggregator, specs)

        if not resolver_inputs:
            console.print("[red]No packages could be resolved[/red]")
            await aggregator.close()
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
            await aggregator.close()
            return

        if args.json:
            json.dump(resolved, sys.stdout, indent=2, default=str)
            print()
            await aggregator.close()
            return

        tree = Tree("[bold]Dependency Tree[/bold]")
        for name, info in rp.items():
            sub = _build_recursive_tree(rp, name, info, max_depth=5)
            tree.add(sub)

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
