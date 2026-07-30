"""Export resolved lock file to various formats (requirements.txt, Dockerfile, etc.)."""

import argparse
import sys
from pathlib import Path

from backend.core.export_generator import ExportGenerator

from ..shared import _read_lock_file, _resolve_lock_path, console, err_console


def cmd_export(args: argparse.Namespace) -> None:
    """Export lock file to a specific format."""
    directory = Path(args.directory).resolve()
    lock_path = _resolve_lock_path(
        directory,
        workspace=args.workspace,
        lock_file=args.lock_file,
    )
    if not lock_path.is_file():
        console.print(f"[red]No lock file found at {lock_path}[/red]")
        console.print("Run [bold]udr lock[/bold] first to generate one.")
        sys.exit(1)

    lock_data = _read_lock_file(lock_path)
    packages = lock_data.get("packages") or lock_data.get("resolved_packages", {})

    if not packages:
        console.print("[yellow]Lock file contains no packages to export.[/yellow]")
        sys.exit(1)

    err_console.print(
        f"[dim]Exporting {len(packages)} packages as [bold]{args.format}[/bold]...[/dim]"
    )

    system_info = lock_data.get("system_info") or lock_data.get("host", {}).get("system_info", {})
    if not system_info:
        import asyncio

        from backend.core.system_scanner import SystemScanner

        try:
            scanner = SystemScanner()
            system_info = asyncio.run(scanner.scan_all())
        except Exception:
            system_info = {}
    generator = ExportGenerator()

    try:
        content = generator.generate(
            packages,
            args.format,
            system_info=system_info or {},
            options={},
        )
    except ValueError as e:
        console.print(f"[red]Export failed:[/red] {e}")
        sys.exit(1)

    if args.output:
        Path(args.output).write_text(content)
        console.print(f"[green]Export written:[/green] {args.output}")
    else:
        print(content)

    sys.exit(0)
