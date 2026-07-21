"""List supported ecosystems with capability information."""

import argparse
import json
import sys

from rich import box
from rich.style import Style
from rich.table import Table

from backend.settings import ECOSYSTEM_CATEGORIES, ECOSYSTEM_NAMES, ECOSYSTEMS

from ..shared import console

_VALID_ECOSYSTEMS = [e for e in ECOSYSTEMS if ECOSYSTEM_CATEGORIES.get(e) != "internal"]


def cmd_list_ecosystems(args: argparse.Namespace) -> None:
    """List supported ecosystems with capability information."""
    ecosystems = _VALID_ECOSYSTEMS
    if args.json:
        data = [
            {
                "name": eco,
                "display": ECOSYSTEM_NAMES.get(eco, eco.replace("_", " ").title()),
                "identifier": eco,
                "capability": ECOSYSTEM_CATEGORIES.get(eco, "query"),
            }
            for eco in ecosystems
        ]
        json.dump(data, sys.stdout, indent=2)
        print()
        return
    resolved_count = sum(1 for e in ecosystems if ECOSYSTEM_CATEGORIES.get(e) == "resolvable")
    query_count = sum(1 for e in ecosystems if ECOSYSTEM_CATEGORIES.get(e) == "query")
    table = Table(
        title=f"Supported Ecosystems ({len(ecosystems)}: {resolved_count} resolvable, {query_count} query-only)",
        box=box.ROUNDED,
    )
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Identifier")
    table.add_column("Capability")

    for eco in ecosystems:
        display = ECOSYSTEM_NAMES.get(eco, eco.replace("_", " ").title())
        category = ECOSYSTEM_CATEGORIES.get(eco, "query")
        if category == "resolvable":
            cap_style = Style(color="green")
        elif category == "query":
            cap_style = Style(color="yellow")
        else:
            cap_style = Style(color="dim")
        table.add_row(eco, display, eco, category, style=cap_style)

    console.print(table)
