"""Install packages from udr.lock.

Delegates to native installers per ecosystem:
  pypi      → pip install
  npm       → npm install
  crates    → cargo add
  gomodules → go get
  rubygems  → gem install
  packagist → composer require
  homebrew  → brew install
  hex       → mix deps.update
  swift     → swift package resolve
  ...
"""

import shlex
import subprocess
from pathlib import Path

from rich.prompt import Confirm

from ..shared import _generate_install_command, _read_lock_file, _resolve_lock_path, console


def cmd_install(args):
    """Install packages from a lock file."""
    directory = Path(args.directory).resolve()
    lock_path = _resolve_lock_path(
        directory,
        workspace=getattr(args, "workspace", None),
        lock_file=getattr(args, "lock_file", None),
    ).resolve()

    lock_data = _read_lock_file(lock_path)
    packages = lock_data.get("packages", {})
    if not packages:
        console.print("[red]No packages in lock file[/red]")
        return 1

    # Filter by production mode (skip dev dependencies)
    production = getattr(args, "production", False)

    # Group by ecosystem
    eco_groups: dict[str, list[tuple[str, str]]] = {}
    for pkg_name, pinfo in packages.items():
        if production and pinfo.get("direct") and pinfo.get("dev"):
            continue
        eco = pinfo.get("ecosystem", "pypi")
        ver = pinfo.get("resolved_version")
        if not ver:
            continue
        if eco not in eco_groups:
            eco_groups[eco] = []
        eco_groups[eco].append((pkg_name, ver))

    if not eco_groups:
        console.print("[red]No packages to install[/red]")
        return 1

    # Filter by ecosystem argument
    requested_eco = getattr(args, "ecosystem", None)
    if requested_eco:
        eco_groups = {k: v for k, v in eco_groups.items() if k == requested_eco}
        if not eco_groups:
            console.print(f"[red]No packages found for ecosystem '{requested_eco}'[/red]")
            return 1

    # Generate install commands
    cuda_version = getattr(args, "cuda", None)
    install_commands: list[tuple[str, str]] = []
    install_pkg_list: dict[str, list[tuple[str, str]]] = {}
    missing_tools: list[str] = []

    for eco, pkgs in eco_groups.items():
        cmd = _generate_install_command(eco, pkgs, cuda_version=cuda_version)
        if cmd:
            install_commands.append((eco, cmd))
            install_pkg_list[eco] = pkgs
        else:
            missing_tools.append(eco)

    if not install_commands:
        console.print("[yellow]No install commands could be generated[/yellow]")
        if missing_tools:
            console.print(f"[yellow]  Unknown installers for: {', '.join(missing_tools)}[/yellow]")
        return 1

    # Show plan
    label = "Restore" if getattr(args, "restore", False) else "Install"
    console.print(f"[bold]{label} Plan[/bold]")
    for eco, cmd in install_commands:
        console.print(f"  [cyan]{eco}[/cyan] ({len(install_pkg_list[eco])} pkgs): [dim]{cmd}[/dim]")
    if missing_tools:
        console.print(f"  [yellow]Skipped (no installer): {', '.join(missing_tools)}[/yellow]")

    if getattr(args, "dry_run", False):
        console.print("[yellow]── dry run — no installations performed ──[/yellow]")
        return 0

    if not getattr(args, "yes", False):
        proceed = Confirm.ask(f"\nProceed with {label.lower()}?", default=False)
        if not proceed:
            return 0

    # Execute
    success = True
    for eco, cmd in install_commands:
        console.print(f"\n[cyan]{label}ing {eco} packages...[/cyan]")
        parts = shlex.split(cmd)
        result = subprocess.call(parts, shell=False)
        if result != 0:
            console.print(f"[red]Failed to install {eco} packages (exit code {result})[/red]")
            success = False
        else:
            console.print(f"  [green]Done ({len(install_pkg_list[eco])} packages)[/green]")

    if success:
        console.print("\n[bold green]All packages installed successfully[/bold green]")
    return 0 if success else 1
