"""Module docstring."""

import shlex
import subprocess
from pathlib import Path

from rich.prompt import Confirm

from ..shared import _generate_install_command, _read_lock_file, console


def cmd_install(args):
    """Cmd install."""
    directory = Path(args.directory).resolve()
    lock_path = directory / "udr.lock"
    if getattr(args, "lock_file", None):
        lock_path = Path(args.lock_file).resolve()

    lock_data = _read_lock_file(lock_path)
    packages = lock_data.get("packages", {})
    if not packages:
        console.print("[red]No packages in lock file[/red]")
        return 1

    eco_groups: dict[str, list[tuple[str, str]]] = {}
    for pkg_name, pinfo in packages.items():
        eco = pinfo.get("ecosystem", "pypi")
        ver = pinfo.get("resolved_version")
        if not ver:
            continue
        if eco not in eco_groups:
            eco_groups[eco] = []
        eco_groups[eco].append((pkg_name, ver))

    if not eco_groups:
        console.print("[red]No resolved packages to install[/red]")
        return 1

    install_commands: list[tuple[str, str]] = []
    install_pkg_list: dict[str, list[tuple[str, str]]] = {}
    for eco, pkgs in eco_groups.items():
        if getattr(args, "ecosystem", None) and eco != args.ecosystem:
            continue
        cmd = _generate_install_command(eco, pkgs)
        if cmd:
            install_commands.append((eco, cmd))
            install_pkg_list[eco] = pkgs

    if not install_commands:
        console.print(
            "[yellow]No install commands could be generated — no installer known for these ecosystems[/yellow]"
        )
        return 1

    label = "Restore" if getattr(args, "restore", False) else "Install"
    console.print(f"[bold]{label} Plan[/bold]")
    for eco, cmd in install_commands:
        console.print(f"  [cyan]{eco}[/cyan] ({len(install_pkg_list[eco])} pkgs): [dim]{cmd}[/dim]")

    if getattr(args, "dry_run", False):
        console.print("[yellow]── dry run — no installations performed ──[/yellow]")
        return 0

    if not getattr(args, "yes", False):
        proceed = Confirm.ask(f"\nProceed with {label.lower()}?", default=False)
        if not proceed:
            return 0

    success = True
    for eco, cmd in install_commands:
        console.print(f"\n[cyan]{label}ing {eco} packages...[/cyan]")
        parts = shlex.split(cmd)
        result = subprocess.call(parts, shell=False)
        if result != 0:
            console.print(
                f"[red]Failed to {label.lower()} {eco} packages (exit code {result})[/red]"
            )
            success = False

    if success:
        console.print(f"\n[bold green]All packages {label.lower()}ed successfully[/bold green]")
    return 0 if success else 1
