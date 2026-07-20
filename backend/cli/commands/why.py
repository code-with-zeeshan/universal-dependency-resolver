"""Explain why a package version was selected — show dependency chain."""

import argparse
import json
import sys
from pathlib import Path

from rich import box
from rich.table import Table

from ..shared import _read_lock_file, _resolve_lock_path, console


def _build_reverse_deps(packages: dict) -> dict[str, list[tuple[str, str, str]]]:
    """Build reverse dependency map: target -> [(source_pkg, source_ver, constraint)]."""
    rev: dict[str, list[tuple[str, str, str]]] = {}
    for pkg_name, pinfo in packages.items():
        for dep_name, dep_val in pinfo.get("depends_on", {}).items():
            dep_constraint = (
                dep_val.get("constraint", "*") if isinstance(dep_val, dict) else dep_val
            )
            rev.setdefault(dep_name, []).append(
                (pkg_name, pinfo.get("resolved_version", "?"), dep_constraint)
            )
    return rev


def _find_dep_chain(
    packages: dict,
    rev_deps: dict,
    target: str,
    max_depth: int = 10,
) -> list[tuple[str, str, str, bool]] | None:
    """Find shortest chain from a direct package down to target via reverse deps.

    Returns list of (package, version, constraint_from_parent, is_direct)
    ordered from closest to target up to the root direct package.
    """
    if target not in rev_deps:
        return None
    visited = {target}

    def _dfs(
        current: str, path: list[tuple[str, str, str, bool]], depth: int
    ) -> list[tuple[str, str, str, bool]] | None:
        if depth > max_depth:
            return None
        for parent_name, parent_ver, constraint in rev_deps.get(current, []):
            if parent_name in visited:
                continue
            visited.add(parent_name)
            pinfo = packages.get(parent_name, {})
            is_direct = bool(pinfo.get("direct", False))
            inserted = [*[(parent_name, parent_ver, constraint, is_direct)], *path]
            if is_direct:
                return inserted
            result = _dfs(parent_name, inserted, depth + 1)
            if result is not None:
                return result
        return None

    return _dfs(target, [], 0)


def _render_dep_table(
    packages: dict,
    rev_deps: dict,
    target: str,
    ver: str,
    eco: str,
    direct: bool,
    constraint: str,
) -> None:
    """Render dependency information tables."""
    # Header
    console.print(f"[bold]Why {target} {ver} ({eco})[/bold]")

    if direct:
        source = packages[target].get("source", "manifest")
        console.print(f"\n  [green]Direct dependency[/green] — declared in [cyan]{source}[/cyan]")
        if constraint and constraint != "*":
            console.print(f"  Constraint: [dim]{constraint}[/dim]")
    else:
        console.print("\n  [yellow]Transitive dependency[/yellow]")

    # Reverse dependencies
    dep_list = rev_deps.get(target, [])
    if dep_list:
        console.print("\n  Required by:")
        rev_table = Table(box=box.SIMPLE)
        rev_table.add_column("Package", style="cyan")
        rev_table.add_column("Version")
        rev_table.add_column("Constraint")
        for parent_name, parent_ver, dep_constraint in sorted(dep_list):
            rev_table.add_row(parent_name, parent_ver, dep_constraint)
        console.print(rev_table)
    elif not direct:
        console.print(
            "\n  [dim]No reverse dependency info — orphaned or missing depends_on data[/dim]"
        )

    # Dependency chain
    if not direct:
        chain = _find_dep_chain(packages, rev_deps, target)
        if chain:
            chain_table = Table(
                title=f"Dependency chain for [cyan]{target}[/cyan]",
                box=box.ROUNDED,
            )
            chain_table.add_column("Level", style="dim")
            chain_table.add_column("Package")
            chain_table.add_column("Version")
            chain_table.add_column("Required By")
            for i, (pname, pver, req_constraint, is_direct) in enumerate(chain, 1):
                label = (
                    "[green]manifest (direct)[/green]"
                    if is_direct
                    else f"parent ({req_constraint})"
                )
                chain_table.add_row(str(i), pname, pver, label)
            chain_table.add_row(
                str(len(chain) + 1),
                f"[bold]{target}[/bold]",
                f"[bold]{ver}[/bold]",
                f"[cyan]{eco}[/cyan]",
            )
            console.print()
            console.print(chain_table)

    # Version selection info
    console.print("\n  Version selection:")
    console.print(f"    Resolved: [green]{ver}[/green]")
    if constraint and constraint != "*":
        console.print(f"    Constraint: [cyan]{constraint}[/cyan]")
    if packages.get(target, {}).get("cuda_variant"):
        console.print(f"    CUDA variant: [yellow]cu{packages[target]['cuda_version']}[/yellow]")
    if dep_list and not direct:
        console.print(f"    Pulled in by: [cyan]{dep_list[0][0]}[/cyan]")


def _explain_package_json(
    packages: dict,
    rev_deps: dict,
    target: str,
) -> dict:
    """Build JSON explanation for a single package."""
    info = packages.get(target, {})
    ver = info.get("resolved_version")
    eco = info.get("ecosystem", "?")
    direct = info.get("direct", False)
    constraint = info.get("original_constraint", "*")

    data: dict = {
        "package": target,
        "version": ver,
        "ecosystem": eco,
        "direct": direct,
        "original_constraint": constraint,
        "depended_by": [
            {"package": p, "version": v, "constraint": c}
            for p, v, c in sorted(rev_deps.get(target, []))
        ],
        "dependency_chain": [],
    }
    if not direct:
        chain = _find_dep_chain(packages, rev_deps, target)
        if chain:
            data["dependency_chain"] = [
                {"package": p, "version": v, "constraint": c, "direct": d} for p, v, c, d in chain
            ]
    return data


def cmd_why(args: argparse.Namespace):
    """Cmd why."""
    directory = Path(args.directory).resolve()
    lock_path = _resolve_lock_path(
        directory,
        workspace=args.workspace,
        lock_file=args.lock_file,
    ).resolve()
    if not lock_path.is_file():
        console.print(f"[red]Lock file not found:[/red] {lock_path}")
        sys.exit(1)

    lock_data = _read_lock_file(lock_path)
    packages = lock_data.get("packages", {})
    rev_deps = _build_reverse_deps(packages)

    all_flag = args.all
    target = args.package

    if all_flag:
        if args.json:
            results: list[dict] = []
            for pkg_name in sorted(packages):
                results.append(_explain_package_json(packages, rev_deps, pkg_name))
            json.dump(results, sys.stdout, indent=2, default=str)
            print()
            return

        for pkg_name in sorted(packages):
            info = packages[pkg_name]
            ver = info.get("resolved_version")
            eco = info.get("ecosystem", "?")
            direct = info.get("direct", False)
            constraint = info.get("original_constraint", "*")
            if not ver:
                continue
            if pkg_name != sorted(packages)[0]:
                console.print()
            _render_dep_table(packages, rev_deps, pkg_name, ver, eco, direct, constraint)
        return

    if not target:
        console.print("[red]Specify a package name or use --all to show all packages[/red]")
        sys.exit(1)

    if target not in packages:
        console.print(f"[red]Package '{target}' not found in lock file[/red]")
        console.print(f"  Available packages: {', '.join(sorted(packages)[:20])}")
        if len(packages) > 20:
            console.print(f"  ... and {len(packages) - 20} more")
        sys.exit(1)

    info = packages[target]
    ver = info.get("resolved_version")
    eco = info.get("ecosystem", "?")
    direct = info.get("direct", False)
    constraint = info.get("original_constraint", "*")

    if not ver:
        console.print(f"[yellow]{target} has no resolved version[/yellow]")
        return

    if args.json:
        data = _explain_package_json(packages, rev_deps, target)
        json.dump(data, sys.stdout, indent=2, default=str)
        print()
        return

    _render_dep_table(packages, rev_deps, target, ver, eco, direct, constraint)
