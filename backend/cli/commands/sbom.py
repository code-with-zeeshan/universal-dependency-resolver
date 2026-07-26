"""Generate SPDX 2.3 or CycloneDX 1.5 SBOM from udr.lock."""

import argparse
import json
import sys
from pathlib import Path

from backend.core.sbom import _build_cyclonedx, _build_spdx

from ..shared import _read_lock_file, _resolve_lock_path, console


def cmd_sbom(args: argparse.Namespace) -> None:
    """Generate SBOM from lock file."""
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
    fmt = args.format
    doc = (
        _build_cyclonedx(lock_data)
        if fmt == "cyclonedx"
        else _build_spdx(lock_data, document_name=f"udr-sbom-{lock_path.name}")
    )

    output = args.output
    json_str = json.dumps(doc, indent=2)

    if output:
        Path(output).write_text(json_str)
        console.print(f"[green]SBOM written:[/green] {output}")
    else:
        print(json_str)

    sys.exit(0)
