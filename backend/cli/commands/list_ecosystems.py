"""Module docstring."""

import argparse
import json
import sys

from rich import box
from rich.table import Table

from backend.settings import ECOSYSTEM_NAMES, ECOSYSTEMS

from ..shared import console

_VALID_ECOSYSTEMS = [e for e in ECOSYSTEMS if e not in ("docs", "custom_db")]


def cmd_list_ecosystems(args: argparse.Namespace) -> None:
    """Cmd list ecosystems."""
    ecosystems = _VALID_ECOSYSTEMS
    if args.json:
        data = [
            {
                "name": eco,
                "display": ECOSYSTEM_NAMES.get(eco, eco.replace("_", " ").title()),
                "identifier": eco,
            }
            for eco in ecosystems
        ]
        json.dump(data, sys.stdout, indent=2)
        print()
        return
    table = Table(title=f"Supported Ecosystems ({len(ecosystems)})", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Identifier")

    for eco in ecosystems:
        display = ECOSYSTEM_NAMES.get(eco, eco.replace("_", " ").title())
        table.add_row(eco, display, eco)

    console.print(table)
