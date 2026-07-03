"""Explain why a package version was selected — show dependency chain."""

import json
import sys
from pathlib import Path

from ..shared import _read_lock_file, console


def _find_dep_chain(
    packages: dict, target: str, chain: list | None = None, visited: set | None = None
) -> list | None:
    """DFS to find the dependency chain leading to target."""
    if chain is None:
        chain = []
    if visited is None:
        visited = set()
    if target in visited:
        return None
    visited.add(target)
    for pkg_name, pinfo in packages.items():
        if pkg_name == target:
            continue
        ver = pinfo.get("resolved_version")
        if not ver:
            continue
        eco = pinfo.get("ecosystem", "pypi")
        deps = pinfo.get("dependencies", {}).get(eco, {})
        if target in deps:
            result = [*chain, (pkg_name, ver, deps.get(target, "?"))]
            return result
        sub = _find_dep_chain(packages, target, [*chain, (pkg_name, ver, "?")], visited)
        if sub is not None:
            return sub
    return None


def cmd_why(args):
    """Cmd why."""
    lock_path = Path(args.directory) / "udr.lock"
    if not lock_path.is_file():
        console.print(f"[red]Lock file not found:[/red] {lock_path}")
        sys.exit(1)

    lock_data = _read_lock_file(lock_path)
    packages = lock_data.get("packages", {})

    target = args.package
    if target not in packages:
        console.print(f"[red]Package '{target}' not found in lock file[/red]")
        sys.exit(1)

    info = packages[target]
    ver = info.get("resolved_version")
    eco = info.get("ecosystem", "?")
    direct = info.get("direct", False)
    constraint = info.get("original_constraint", "*")

    if getattr(args, "json", False):
        data = {
            "package": target,
            "version": ver,
            "ecosystem": eco,
            "direct": direct,
            "original_constraint": constraint,
            "dependency_chain": [],
        }
        if not direct:
            chain = _find_dep_chain(packages, target)
            if chain:
                data["dependency_chain"] = [
                    {"package": p, "version": v, "required_as": r} for p, v, r in chain
                ]
        json.dump(data, sys.stdout, indent=2, default=str)
        print()
        return

    if not ver:
        console.print(f"[yellow]{target} has no resolved version[/yellow]")
        return

    console.print(f"[bold]Why {target} {ver} ({eco})[/bold]")

    if direct:
        console.print(
            f"\n  [green]Direct dependency[/green] — specified in manifest as [cyan]{constraint}[/cyan]"
        )
    else:
        console.print("\n  [yellow]Transitive dependency[/yellow] — pulled in by another package")
        console.print(f"  [dim]Run 'udr graph {target}' to see the full dependency tree[/dim]")

    source = info.get("source", "unknown")
    console.print(f"\n  Source: [dim]{source}[/dim]")
    if constraint and constraint != "*":
        console.print(f"  Original constraint: [dim]{constraint}[/dim]")
