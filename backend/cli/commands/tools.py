"""Manage plugins and extensions — register third-party plugins."""

import argparse
import sys

from backend.core.plugin import scan_plugin_directory

from ..shared import console


def cmd_tools(args: argparse.Namespace) -> None:
    """Dispatch to the tools subcommand handler."""
    if args.tools_command == "register-plugin":
        _register_plugin(args)


def _register_plugin(args: argparse.Namespace) -> None:
    """Scan a directory and register any plugins found."""
    path = args.path
    try:
        discovered = scan_plugin_directory(path)
    except NotADirectoryError:
        console.print(f"[red]Error:[/] plugin directory not found: {path}")
        sys.exit(1)
    except Exception as exc:
        console.print(f"[red]Error scanning plugins:[/] {exc}")
        sys.exit(1)

    if not discovered:
        console.print(f"[yellow]No new plugins discovered in[/] {path}")
        return

    console.print(f"[green]Discovered {len(discovered)} plugin(s):[/]")
    for eco, mod in sorted(discovered.items()):
        console.print(f"  [bold]{eco}[/] → {mod}")

    if args.name:
        console.print(f"\nPlugin name tag: [bold]{args.name}[/]")
