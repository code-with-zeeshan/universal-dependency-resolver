"""Module docstring."""

import asyncio
import json
import sys
from pathlib import Path

from packaging.version import parse as parse_version
from rich import box
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..shared import _read_lock_file, console, err_console


async def _cmd_verify_async(args):
    """Cmd verify async."""
    from backend.core import DataAggregator

    lock_path = Path(args.lock_file)
    lock_data = _read_lock_file(lock_path)
    aggregator = DataAggregator()

    packages = lock_data.get("packages", {})
    if not packages:
        console.print("[yellow]No packages in lock file[/yellow]")
        return 0

    issues = []
    ok_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[green]{task.completed}/{task.total}[/green]"),
        console=err_console,
    ) as progress:
        verify_task = progress.add_task("Verifying packages...", total=len(packages))

        async def check_pkg(name: str, info: dict) -> dict | None:
            """Check pkg."""
            eco = info.get("ecosystem", "pypi")
            ver = info.get("resolved_version")
            if not ver:
                return {
                    "name": name,
                    "issue": "No resolved version",
                    "severity": "warning",
                }
            try:
                data = await aggregator.get_package_info(
                    name,
                    ecosystem=eco,
                    include_versions=True,
                )
                if data:
                    versions = data.get("versions", {}).get(eco, [])
                    version_strings = [
                        v.get("version", "") if isinstance(v, dict) else str(v) for v in versions
                    ]
                    try:
                        target_ver = parse_version(ver)
                        found = any(parse_version(vs) == target_ver for vs in version_strings if vs)
                        if not found and ver not in version_strings:
                            return {
                                "name": name,
                                "issue": f"Version {ver} no longer available",
                                "severity": "error",
                            }
                    except Exception:
                        if ver not in version_strings:
                            return {
                                "name": name,
                                "issue": f"Version {ver} no longer available",
                                "severity": "error",
                            }
                else:
                    return {
                        "name": name,
                        "issue": "Package not found on registry",
                        "severity": "error",
                    }
            except Exception as exc:
                return {"name": name, "issue": str(exc), "severity": "error"}
            return None

        results = await asyncio.gather(*[check_pkg(n, i) for n, i in packages.items()])

        for result in results:
            if result:
                issues.append(result)
                progress.update(verify_task, description=f"[red]Issue: {result['name']}[/red]")
            else:
                ok_count += 1
            progress.advance(verify_task)

    if getattr(args, "json", False):
        data = {
            "lock_file": str(lock_path),
            "ok_count": ok_count,
            "issue_count": len(issues),
            "issues": issues,
        }
        json.dump(data, sys.stdout, indent=2, default=str)
        print()
        await aggregator.close()
        return 1 if issues and any(i["severity"] == "error" for i in issues) else 0

    summary = Table(title=f"Lock File Verification — {lock_path.name}", box=box.ROUNDED)
    summary.add_column("Status", style="bold")
    summary.add_column("Count")
    summary.add_row("✅ OK", str(ok_count))
    summary.add_row("⚠ Issues", str(len(issues)))
    console.print(summary)

    if issues:
        issue_table = Table(box=box.SIMPLE)
        issue_table.add_column("Severity", style="bold")
        issue_table.add_column("Package")
        issue_table.add_column("Issue")
        for iss in issues:
            sev_icon = "[red]ERROR[/red]" if iss["severity"] == "error" else "[yellow]WARN[/yellow]"
            issue_table.add_row(sev_icon, iss["name"], iss["issue"])
        console.print(issue_table)

    await aggregator.close()
    if issues and any(i["severity"] == "error" for i in issues):
        return 1
    return 0


def cmd_verify(args):
    """Cmd verify."""
    try:
        sys.exit(asyncio.run(_cmd_verify_async(args)))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Verify Error"))
        sys.exit(1)
