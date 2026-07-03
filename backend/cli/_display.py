"""Output and display utilities."""

import json
import sys
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


def _build_resolved_table(
    resolved: dict,
    title: str | None = None,
) -> Table | None:
    rp = resolved.get("resolved_packages", {})
    if not rp:
        """ Build Resolved Table."""
        return None
    table = Table(title=title or f"Resolved {len(rp)} packages", box=box.ROUNDED)
    table.add_column("Package", style="cyan")
    table.add_column("Ecosystem")
    table.add_column("Version", style="bold green")
    table.add_column("Notes")
    for name, info in rp.items():
        ver = info.get("version", "?")
        eco = info.get("ecosystem", "?")
        cuda = info.get("cuda_version")
        notes = f"CUDA {cuda}" if cuda else ""
        table.add_row(name, eco, ver, notes)
    return table


def _output_json(data: Any, args) -> None:
    """Output JSON."""
    json.dump(data, sys.stdout, indent=2, default=str)
    print()
    sys.exit(0)


def _generate_install_command(
    ecosystem: str,
    packages: list[tuple[str, str]],
) -> str | None:
    """Generate Install Command."""
    if not packages:
        return None
    installers = {
        "pypi": ("pip", "install"),
        "npm": ("npm", "install"),
        "crates": ("cargo", "add"),
        "gomodules": ("go", "get"),
        "conda": ("conda", "install"),
        "rubygems": ("gem", "install"),
        "packagist": ("composer", "require"),
        "pub": ("dart", "pub", "add"),
        "nuget": ("dotnet", "add", "package"),
        "cocoapods": ("pod", "install"),
        "maven": ("mvn", "dependency:copy-dependencies"),
    }
    installer = installers.get(ecosystem)
    if not installer:
        return None
    if ecosystem == "npm":
        specs = [f"{name}@{ver}" for name, ver in packages]
    elif ecosystem == "pub":
        specs = [f"{name}:{ver}" for name, ver in packages]
    elif ecosystem in ("gomodules", "cocoapods"):
        specs = [f"{name}@{ver}" for name, ver in packages]
    else:
        specs = [f"{name}=={ver}" for name, ver in packages]
    return " ".join(list(installer) + specs)
