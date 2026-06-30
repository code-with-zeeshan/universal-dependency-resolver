import json
import sys

from rich.table import Table
from rich import box

from backend.settings import ECOSYSTEMS, ECOSYSTEM_NAMES

from ..shared import console


def cmd_list_ecosystems(args):
    if getattr(args, "json", False):
        data = [
            {
                "name": eco,
                "display": ECOSYSTEM_NAMES.get(eco, eco.replace("_", " ").title()),
                "identifier": eco,
            }
            for eco in ECOSYSTEMS
        ]
        json.dump(data, sys.stdout, indent=2)
        print()
        return
    table = Table(title=f"Supported Ecosystems ({len(ECOSYSTEMS)})", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Identifier")

    for eco in ECOSYSTEMS:
        display = ECOSYSTEM_NAMES.get(eco, eco.replace("_", " ").title())
        table.add_row(eco, display, eco)

    console.print(table)
