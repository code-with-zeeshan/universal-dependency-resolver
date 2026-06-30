import asyncio
import sys
from pathlib import Path

from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import box

from ..shared import console, err_console, _output_json, PROJECT_ROOT


def cmd_info(args):
    from backend.core import SystemScanner

    async def _info():
        with Progress(
            SpinnerColumn(),
            TextColumn("Scanning system..."),
            transient=True,
            console=err_console,
        ) as p:
            p.add_task("scan", total=None)
            scanner = SystemScanner()
            info = await scanner.scan_all()

        if getattr(args, "json", False):
            return _output_json(info, args)

        plat = info.get("platform", {})
        table = Table(
            title=f"System: {plat.get('system', '?')} {plat.get('release', '?')}",
            box=box.ROUNDED,
        )
        table.add_column("Property", style="cyan")
        table.add_column("Value")

        table.add_row("Architecture", plat.get("machine", "?"))
        cpu_cores = (
            info.get("cpu", {}).get("count_logical")
            or info.get("cpu", {}).get("count_physical")
            or info.get("cpu", {}).get("count", "?")
        )
        table.add_row(
            "CPU", f"{info.get('cpu', {}).get('brand', 'Unknown')} ({cpu_cores} cores)"
        )
        py_info = info.get("runtime_versions", {}).get("python", {})
        table.add_row("Python", py_info.get("version", "?"))
        table.add_row("Python path", py_info.get("path", py_info.get("location", "?")))

        mem = info.get("memory", {})
        if mem:
            total = mem.get("total", 0) / (1024**3)
            avail = mem.get("available", 0) / (1024**3)
            table.add_row("Memory", f"{total:.1f} GB total, {avail:.1f} GB free")

        gpu_info = info.get("gpu", {})
        if gpu_info.get("available"):
            gpu_devices = gpu_info.get("devices", [])
            if gpu_devices:
                gpu = gpu_devices[0]
                table.add_row(
                    "GPU", f"{gpu.get('name', '?')} ({gpu.get('memory_total', '?')} MB)"
                )
                cuda = gpu_info.get("cuda", "not found")
                if cuda and cuda != "not found":
                    table.add_row("CUDA", cuda)

        console.print(table)

        import tomllib

        pyproject = PROJECT_ROOT / "pyproject.toml"
        if pyproject.is_file():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            deps = data.get("project", {}).get("dependencies", [])
            dep_table = Table(
                title=f"Core Dependencies ({len(deps)} packages)", box=box.SIMPLE
            )
            dep_table.add_column("Dependency", style="cyan")
            for d in deps:
                dep_table.add_row(d)
            console.print(dep_table)

    try:
        asyncio.run(_info())
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Info Error"))
        sys.exit(1)
