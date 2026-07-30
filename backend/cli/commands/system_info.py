"""Show detailed system information — OS, CPU, GPU, Python, runtime versions."""

import argparse
import json
import sys

from rich import box
from rich.table import Table

from ..shared import console


def cmd_system_info(args: argparse.Namespace) -> None:
    """Show detailed system information."""
    import asyncio

    from backend.core import SystemScanner

    scanner = SystemScanner()
    try:
        info = asyncio.run(scanner.scan_all())
    except Exception as e:
        console.print(f"[red]System scan failed:[/red] {e}")
        sys.exit(1)

    if args.json:
        json.dump(info, sys.stdout, indent=2, default=str)
        print()
        return

    platform = info.get("platform", {})
    cpu = info.get("cpu", {})
    gpu = info.get("gpu", {})
    runtime = info.get("runtime_versions", {})
    memory = info.get("memory", {})
    disk = info.get("disk", {})

    console.print("\n[bold]System Information[/bold]\n")

    table = Table(box=box.SIMPLE)
    table.add_column("Category", style="cyan")
    table.add_column("Property", style="yellow")
    table.add_column("Value")

    table.add_row("OS", "System", platform.get("system", "unknown"))
    table.add_row("OS", "Release", platform.get("release", ""))
    table.add_row("OS", "Machine", platform.get("machine", "unknown"))
    table.add_row("CPU", "Model", cpu.get("brand", "Unknown"))
    table.add_row("CPU", "Cores", str(cpu.get("cores", "?")))
    table.add_row(
        "Memory",
        "Total",
        f"{memory.get('total_gb', '?'):.1f} GB"
        if isinstance(memory.get("total_gb"), (int, float))
        else str(memory.get("total_gb", "?")),
    )
    table.add_row(
        "Memory",
        "Available",
        f"{memory.get('available_gb', '?'):.1f} GB"
        if isinstance(memory.get("available_gb"), (int, float))
        else str(memory.get("available_gb", "?")),
    )
    table.add_row(
        "Disk",
        "Total",
        f"{disk.get('total_gb', '?'):.1f} GB"
        if isinstance(disk.get("total_gb"), (int, float))
        else str(disk.get("total_gb", "?")),
    )
    table.add_row(
        "Disk",
        "Free",
        f"{disk.get('free_gb', '?'):.1f} GB"
        if isinstance(disk.get("free_gb"), (int, float))
        else str(disk.get("free_gb", "?")),
    )

    if gpu.get("available"):
        devices = gpu.get("devices", [])
        for i, dev in enumerate(devices):
            table.add_row(f"GPU #{i}", "Name", dev.get("name", "unknown"))
            table.add_row(
                f"GPU #{i}",
                "Memory",
                f"{dev.get('memory_gb', '?'):.1f} GB"
                if isinstance(dev.get("memory_gb"), (int, float))
                else str(dev.get("memory_gb", "?")),
            )
        if gpu.get("cuda"):
            table.add_row("GPU", "CUDA Version", gpu["cuda"])
        if gpu.get("rocm"):
            table.add_row("GPU", "ROCm Version", gpu["rocm"])

    for eco_name in ("python", "node", "go", "rust", "java", "ruby", "php"):
        ver_info = runtime.get(eco_name, {})
        ver = ver_info.get("version") if isinstance(ver_info, dict) else None
        if ver:
            table.add_row("Runtime", eco_name.title(), ver)

    console.print(table)

    accelerators = info.get("accelerators", {})
    if accelerators.get("available"):
        acc_table = Table(title="Accelerators", box=box.SIMPLE)
        acc_table.add_column("Type", style="cyan")
        acc_table.add_column("Name")
        acc_table.add_column("Details")
        for acc_type, acc_list in accelerators.items():
            if acc_type == "available":
                continue
            if isinstance(acc_list, list):
                for acc in acc_list:
                    if isinstance(acc, dict):
                        acc_table.add_row(acc_type, acc.get("name", ""), acc.get("details", ""))
        if acc_table.row_count:
            console.print(acc_table)
