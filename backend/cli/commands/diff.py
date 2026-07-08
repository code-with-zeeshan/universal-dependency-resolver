"""Compare two lock files and show version differences."""

import json
import sys
from pathlib import Path

from rich import box
from rich.table import Table

from ..shared import _resolve_lock_path, console


def _read_lock(path: str) -> dict:
    """Read and validate a lock file."""
    p = Path(path)
    if not p.is_file():
        console.print(f"[red]Lock file not found:[/red] {p}")
        sys.exit(1)
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid lock file {path}:[/red] {e}")
        sys.exit(1)
    ver = data.get("version", "0.0")
    if ver not in ("1.0", "2.0"):
        console.print(f"[red]Unsupported lock file version: {ver} in {path}[/red]")
        sys.exit(1)
    return data


def cmd_diff(args):
    """Cmd diff."""
    directory = Path(getattr(args, "directory", ".")).resolve()
    workspace = getattr(args, "workspace", None)

    if workspace and not args.lock_file_a and not args.lock_file_b:
        # Compare udr.lock vs udr-{workspace}.lock
        path_a = str(_resolve_lock_path(directory, workspace=None))
        path_b = str(_resolve_lock_path(directory, workspace=workspace))
    elif args.lock_file_a and args.lock_file_b:
        path_a = args.lock_file_a
        path_b = args.lock_file_b
    else:
        console.print(
            "[red]Specify two lock file paths, or use --workspace for a diff with the base lock file.[/red]"
        )
        sys.exit(1)

    data_a = _read_lock(path_a)
    data_b = _read_lock(path_b)

    pkgs_a = data_a.get("packages", {})
    pkgs_b = data_b.get("packages", {})

    all_names = sorted(set(list(pkgs_a.keys()) + list(pkgs_b.keys())))

    added = []
    removed = []
    changed = []
    unchanged = []

    for name in all_names:
        info_a = pkgs_a.get(name, {})
        info_b = pkgs_b.get(name, {})
        ver_a = info_a.get("resolved_version")
        ver_b = info_b.get("resolved_version")

        if not ver_a and ver_b:
            added.append((name, info_b.get("ecosystem", "?"), ver_b))
        elif ver_a and not ver_b:
            removed.append((name, info_a.get("ecosystem", "?"), ver_a))
        elif ver_a != ver_b:
            changed.append(
                (
                    name,
                    info_a.get("ecosystem", info_b.get("ecosystem", "?")),
                    ver_a or "?",
                    ver_b or "?",
                )
            )
        elif ver_a == ver_b:
            unchanged.append(name)

    if getattr(args, "json", False):
        data = {
            "file_a": path_a,
            "file_b": path_b,
            "added": [{"name": n, "ecosystem": e, "version": v} for n, e, v in added],
            "removed": [{"name": n, "ecosystem": e, "version": v} for n, e, v in removed],
            "changed": [
                {"name": n, "ecosystem": e, "from": o, "to": nv} for n, e, o, nv in changed
            ],
            "unchanged_count": len(unchanged),
        }
        json.dump(data, sys.stdout, indent=2, default=str)
        print()
        return

    console.print(f"[bold]Diff:[/bold] {path_a} ↔ {path_b}")
    console.print()

    if not added and not removed and not changed:
        console.print("[green]Lock files are identical.[/green]")
        return

    if added:
        table = Table(title=f"Added ({len(added)})", box=box.SIMPLE)
        table.add_column("Package", style="cyan")
        table.add_column("Ecosystem")
        table.add_column("Version", style="green")
        for n, e, v in added:
            table.add_row(n, e, v)
        console.print(table)

    if removed:
        table = Table(title=f"Removed ({len(removed)})", box=box.SIMPLE)
        table.add_column("Package", style="cyan")
        table.add_column("Ecosystem")
        table.add_column("Version", style="red")
        for n, e, v in removed:
            table.add_row(n, e, v)
        console.print(table)

    if changed:
        table = Table(title=f"Changed ({len(changed)})", box=box.ROUNDED)
        table.add_column("Package", style="cyan")
        table.add_column("Ecosystem")
        table.add_column("From", style="red")
        table.add_column("To", style="green")
        for n, e, o, nv in changed:
            table.add_row(n, e, o, nv)
        console.print(table)

    if unchanged:
        console.print(f"\n[dim]{len(unchanged)} packages unchanged[/dim]")
