import sys

from rich.panel import Panel

from ..shared import console
from .lock import cmd_lock


def cmd_scan(args):
    if args.github:
        _cmd_scan_github(args)
    elif args.directory:
        args.directory = args.directory
        cmd_lock(args)
    else:
        console.print("[red]Specify --github <url> or --directory <path>[/red]")
        sys.exit(1)


def _cmd_scan_github(args):
    try:
        from backend.api.routes.scan import _download_github_repo

        console.print(f"[bold]Scanning GitHub repo:[/bold] [cyan]{args.github}[/cyan]")
        repo_path = _download_github_repo(args.github, args.branch)
        console.print(f"  Cloned to: [dim]{repo_path}[/dim]")

        args.directory = str(repo_path)
        cmd_lock(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Scan Error"))
        sys.exit(1)
