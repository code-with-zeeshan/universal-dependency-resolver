"""Module docstring."""

import argparse
import asyncio
import sys

from rich.panel import Panel

from ..shared import console
from .lock import cmd_lock


def cmd_scan(args: argparse.Namespace) -> None:
    """Cmd scan."""
    if args.github:
        _cmd_scan_github(args)
    elif args.directory:
        cmd_lock(args)
    else:
        console.print("[red]Specify --github <url> or --directory <path>[/red]")
        sys.exit(1)


async def _async_download(url: str, branch: str) -> str:
    from backend.orchestrator import _download_github_repo

    return await _download_github_repo(url, branch)


def _cmd_scan_github(args: argparse.Namespace) -> None:
    """Cmd scan github."""
    try:
        console.print(f"[bold]Scanning GitHub repo:[/bold] [cyan]{args.github}[/cyan]")
        repo_path = asyncio.run(_async_download(args.github, args.branch))
        console.print(f"  Cloned to: [dim]{repo_path}[/dim]")

        args.directory = str(repo_path)
        cmd_lock(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Scan Error"))
        sys.exit(1)
