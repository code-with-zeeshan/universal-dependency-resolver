import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from rich.prompt import Confirm

from ..shared import console, _read_lock_file, _generate_install_command


def cmd_install(args):
    directory = Path(args.directory).resolve()
    lock_path = directory / "udr-lock.json"
    if args.lock_file:
        lock_path = Path(args.lock_file).resolve()

    lock_data = _read_lock_file(lock_path)
    packages = lock_data.get("packages", {})
    if not packages:
        console.print("[red]No packages in lock file[/red]")
        return 1

    eco_groups: Dict[str, List[Tuple[str, str]]] = {}
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

    install_commands: List[Tuple[str, str]] = []
    for eco, pkgs in eco_groups.items():
        if args.ecosystem and eco != args.ecosystem:
            continue
        cmd = _generate_install_command(eco, pkgs)
        if cmd:
            install_commands.append((eco, cmd))

    if not install_commands:
        console.print(
            "[yellow]No install commands could be generated — no installer known for these ecosystems[/yellow]"
        )
        return 1

    console.print("[bold]Install Plan[/bold]")
    for eco, cmd in install_commands:
        console.print(
            f"  [cyan]{eco}[/cyan] ({len(eco_groups[eco])} pkgs): [dim]{cmd}[/dim]"
        )

    if args.dry_run:
        console.print("[yellow]── dry run — no installations performed ──[/yellow]")
        return 0

    if not args.yes:
        proceed = Confirm.ask("\nProceed with installation?", default=False)
        if not proceed:
            return 0

    success = True
    for eco, cmd in install_commands:
        console.print(f"\n[cyan]Installing {eco} packages...[/cyan]")
        result = subprocess.call(cmd, shell=True)
        if result != 0:
            console.print(
                f"[red]Failed to install {eco} packages (exit code {result})[/red]"
            )
            success = False

    if success:
        console.print("\n[bold green]All packages installed successfully[/bold green]")
    return 0 if success else 1


def cmd_restore(args):
    return cmd_install(args)
