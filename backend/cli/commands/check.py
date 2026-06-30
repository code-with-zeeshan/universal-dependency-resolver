import asyncio
import sys

from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import box

from ..shared import console, err_console, _output_json, PROJECT_ROOT


def cmd_check(args):
    from backend.core import SystemScanner

    async def _check():
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=err_console,
        ) as progress:
            progress.add_task("Scanning system...", total=None)
            scanner = SystemScanner()
            info = await scanner.scan_all()

        if getattr(args, "json", False):
            return _output_json(info, args)

        table = Table(title="System Compatibility", box=box.ROUNDED)
        table.add_column("Component", style="cyan")
        table.add_column("Value")
        table.add_column("Status", style="bold")

        plat = info.get("platform", {})
        table.add_row(
            "OS", f"{plat.get('system', '?')} {plat.get('release', '?')}", "✅"
        )
        arch = plat.get("machine", info.get("cpu", {}).get("arch", "unknown"))
        table.add_row("Architecture", arch, "✅")
        cpu_cores = (
            info.get("cpu", {}).get("count_logical")
            or info.get("cpu", {}).get("count_physical")
            or info.get("cpu", {}).get("count", "?")
        )
        table.add_row(
            "CPU",
            f"{info.get('cpu', {}).get('brand', 'Unknown')} ({cpu_cores} cores)",
            "✅",
        )

        mem = info.get("memory", {})
        if mem:
            total = mem.get("total", 0) / (1024**3)
            avail = mem.get("available", 0) / (1024**3)
            pct = mem.get("percent", 0)
            mem_status = "⚠" if pct > 90 else "✅"
            table.add_row(
                "Memory", f"{total:.1f} GB total, {avail:.1f} GB free", mem_status
            )

        gpu_info = info.get("gpu", {})
        if gpu_info.get("available"):
            gpu_devices = gpu_info.get("devices", [])
            if gpu_devices:
                gpu = gpu_devices[0]
                raw_cuda = gpu_info.get("cuda", {})
                cuda = raw_cuda.get("version", "not found") if isinstance(raw_cuda, dict) else str(raw_cuda)
                table.add_row(
                    "GPU",
                    f"{gpu.get('name', '?')} ({gpu.get('memory_total', '?')} MB)",
                    "✅",
                )
                table.add_row(
                    "CUDA", cuda, "✅" if cuda and cuda != "not found" else "⚠"
                )
            else:
                table.add_row("GPU", "No GPU devices", "ℹ")
        else:
            table.add_row("GPU", "None detected", "ℹ")

        py = info.get("runtime_versions", {}).get("python", {})
        table.add_row("Python", py.get("version", "?"), "✅")

        if args.verbose:
            table.add_row("Python path", py.get("path", py.get("location", "?")), "")
            table.add_row("CPU arch", info.get("cpu", {}).get("arch", "unknown"), "")

        console.print(table)

        if args.verbose:
            rt_table = Table(title="Runtime Versions", box=box.SIMPLE)
            rt_table.add_column("Runtime", style="cyan")
            rt_table.add_column("Version")
            for rt_name, rt_info in info.get("runtime_versions", {}).items():
                if isinstance(rt_info, dict) and rt_info.get("version"):
                    rt_table.add_row(rt_name, rt_info["version"])
            console.print(rt_table)

        if args.deps:
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

        return True

    try:
        asyncio.run(_check())
        sys.exit(0)
    except Exception as e:
        console.print(Panel(f"[red]Check failed:[/red] {e}", title="Error"))
        sys.exit(1)
