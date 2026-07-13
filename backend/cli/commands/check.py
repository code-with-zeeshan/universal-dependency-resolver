"""Module docstring."""

import asyncio
import sys
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from backend.core.policy_engine import check_policy, load_policy

from ..shared import (
    PROJECT_ROOT,
    _extract_severity,
    _output_json,
    _read_lock_file,
    _resolve_lock_path,
    console,
    err_console,
)


def cmd_check(args):
    """Cmd check."""
    from backend.core import SystemScanner

    async def _check():
        if getattr(args, "policy", None) is not None:
            return await _check_policy(args)
        if getattr(args, "cve", False):
            return await _check_cve(args)
        if getattr(args, "license", False):
            return await _check_license(args)
        if getattr(args, "deprecated", False):
            return await _check_deprecated(args)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=err_console,
        ) as progress:
            progress.add_task("Scanning system...", total=None)
            scanner = SystemScanner()
            info = await scanner.scan_all()

        if args.cuda is not None:
            if "gpu" not in info:
                info["gpu"] = {}
            info["gpu"]["available"] = True
            info["gpu"]["cuda"] = args.cuda
        if args.device is not None:
            if "gpu" not in info:
                info["gpu"] = {}
            if args.device == "cpu":
                info["gpu"]["available"] = False
                info["gpu"]["cuda"] = ""
            elif args.device == "cuda":
                info["gpu"]["available"] = True
                info["gpu"]["type"] = "cuda"
                if not info["gpu"].get("cuda"):
                    info["gpu"]["cuda"] = "12.1"
            elif args.device == "mps":
                info["gpu"]["available"] = True
                info["gpu"]["type"] = "mps"
                info["gpu"]["cuda"] = ""

        if getattr(args, "json", False):
            return _output_json(info, args)

        table = Table(title="System Compatibility", box=box.ROUNDED)
        table.add_column("Component", style="cyan")
        table.add_column("Value")
        table.add_column("Status", style="bold")

        plat = info.get("platform", {})
        table.add_row("OS", f"{plat.get('system', '?')} {plat.get('release', '?')}", "✅")
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
            table.add_row("Memory", f"{total:.1f} GB total, {avail:.1f} GB free", mem_status)

        gpu_info = info.get("gpu", {})
        if gpu_info.get("available"):
            gpu_devices = gpu_info.get("devices", [])
            if gpu_devices:
                gpu = gpu_devices[0]
                raw_cuda = gpu_info.get("cuda", {})
                cuda = (
                    raw_cuda.get("version", "not found")
                    if isinstance(raw_cuda, dict)
                    else str(raw_cuda)
                )
                table.add_row(
                    "GPU",
                    f"{gpu.get('name', '?')} ({gpu.get('memory_total', '?')} MB)",
                    "✅",
                )
                table.add_row("CUDA", cuda, "✅" if cuda and cuda != "not found" else "⚠")
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
                dep_table = Table(title=f"Core Dependencies ({len(deps)} packages)", box=box.SIMPLE)
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


async def _check_cve(args):
    """Check lock file packages against OSV vulnerability database."""
    from backend.core.data_aggregator import DataAggregator

    directory = Path(getattr(args, "directory", ".")).resolve()
    lock_path = _resolve_lock_path(
        directory,
        workspace=getattr(args, "workspace", None),
        lock_file=getattr(args, "lock_file", None),
    )
    if not lock_path.is_file():
        console.print(f"[red]No lock file found at {lock_path.name}[/red]")
        console.print("Run [bold]udr lock[/bold] first to generate one.")
        sys.exit(1)

    lock_data = _read_lock_file(lock_path)
    packages = lock_data.get("packages", {})
    if not packages:
        console.print("[yellow]Lock file has no packages to check.[/yellow]")
        return True

    aggregator = DataAggregator()
    vuln_results: list[tuple[str, str, dict]] = []

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=err_console,
    )
    with progress:
        check_task = progress.add_task(
            f"Checking {len(packages)} packages for CVEs...", total=len(packages)
        )

        async def _check_one(name: str, info: dict):
            eco = info.get("ecosystem", "")
            ver = info.get("resolved_version", "")
            try:
                vulns = await aggregator.check_vulnerabilities(name, eco, ver)
                for v in vulns:
                    vuln_results.append((name, ver, v))
            except Exception:
                err_console.print(f"[dim]Warning: CVE check failed for {name}[/dim]")
            progress.advance(check_task)

        await asyncio.gather(*[_check_one(n, i) for n, i in packages.items()])

    if not vuln_results:
        console.print("[green]✅ No known vulnerabilities found in lock file.[/green]")
        return True

    critical_high = [v for v in vuln_results if _extract_severity(v[2]) in ("CRITICAL", "HIGH")]
    others = len(vuln_results) - len(critical_high)

    title = f"[red]{len(vuln_results)} known vulnerabilities"
    if critical_high:
        title += f" ({len(critical_high)} critical/high)"
    title += "[/red]"

    vuln_table = Table(title=title, box=box.ROUNDED)
    vuln_table.add_column("Package", style="cyan")
    vuln_table.add_column("Version", style="dim")
    vuln_table.add_column("CVE ID", style="yellow")
    vuln_table.add_column("Severity")
    vuln_table.add_column("Summary")

    for pkg_name, pkg_ver, v in vuln_results:
        cve_id = v.get("id", "?")
        sev = _extract_severity(v)
        summary = v.get("summary", "")[:80]
        sev_style = {
            "CRITICAL": "bold red",
            "HIGH": "red",
            "MEDIUM": "yellow",
            "LOW": "dim",
            "UNKNOWN": "dim",
        }.get(sev, "dim")
        vuln_table.add_row(pkg_name, pkg_ver, cve_id, f"[{sev_style}]{sev}[/{sev_style}]", summary)

    console.print(vuln_table)

    if others > 0:
        console.print(f"[dim]... and {others} lower-severity vulnerabilities.[/dim]")

    return True


async def _check_license(args):
    """Check lock file packages for license compliance."""
    from backend.core.license_checker import check_license_compatibility

    directory = Path(getattr(args, "directory", ".")).resolve()
    lock_path = _resolve_lock_path(
        directory,
        workspace=getattr(args, "workspace", None),
        lock_file=getattr(args, "lock_file", None),
    )
    if not lock_path.is_file():
        console.print(f"[red]No lock file found at {lock_path.name}[/red]")
        console.print("Run [bold]udr lock[/bold] first to generate one.")
        sys.exit(1)

    lock_data = _read_lock_file(lock_path)
    packages = lock_data.get("packages", {})
    if not packages:
        console.print("[yellow]Lock file has no packages to check.[/yellow]")
        return True

    package_licenses: dict[str, str | list[str]] = {}
    missing_licenses: list[tuple[str, str]] = []
    for pname, pinfo in packages.items():
        raw_license = pinfo.get("license")
        if raw_license:
            package_licenses[pname] = raw_license
        else:
            eco = pinfo.get("ecosystem", "pypi")
            missing_licenses.append((pname, eco))

    if missing_licenses:
        from backend.core import DataAggregator

        aggregator = DataAggregator()
        for pname, eco in missing_licenses:
            try:
                data = await aggregator.get_package_info(
                    pname, ecosystem=eco, include_dependencies=False, include_versions=False
                )
                if data:
                    lic = data.get("license") or data.get("info", {}).get("license", "")
                    if lic:
                        package_licenses[pname] = lic
            except Exception:
                pass
        await aggregator.close()

    if not package_licenses:
        console.print("[yellow]No license information found in lock file or registries.[/yellow]")
        console.print(
            "Some registries (e.g., PyPI) include license data; others may require manual entry."
        )
        return True

    results = check_license_compatibility(package_licenses)

    denied = {n for n, r in results.items() if r["status"] == "denied"}
    warnings = {n for n, r in results.items() if r["status"] == "warning"}
    unknowns = {n for n, r in results.items() if r["status"] == "unknown"}

    title_parts = [f"{len(results)} packages checked"]
    if denied:
        title_parts.append(f"[red]{len(denied)} denied[/red]")
    if warnings:
        title_parts.append(f"[yellow]{len(warnings)} warnings[/yellow]")
    if unknowns:
        title_parts.append(f"[dim]{len(unknowns)} unknown[/dim]")

    lic_table = Table(
        title="License Compliance — " + ", ".join(title_parts),
        box=box.ROUNDED,
    )
    lic_table.add_column("Package", style="cyan")
    lic_table.add_column("License", style="yellow")
    lic_table.add_column("Category")
    lic_table.add_column("Status")
    lic_table.add_column("Reason")

    status_style = {
        "allowed": "bold green",
        "warning": "yellow",
        "denied": "bold red",
        "unknown": "dim",
    }

    for pname in sorted(results):
        r = results[pname]
        normalized = r["normalized"]
        lic_display = normalized if isinstance(normalized, str) else ", ".join(normalized)
        cat_display = r["category"].replace("_", " ")
        stat = r["status"]
        styl = status_style.get(stat, "dim")
        lic_table.add_row(
            pname,
            lic_display,
            cat_display,
            f"[{styl}]{stat}[/{styl}]",
            r["reason"],
        )

    console.print(lic_table)

    if denied:
        console.print(
            "\n[red]✗ Some packages have licenses incompatible with the default policy.[/red]"
        )
        console.print(
            "  Review licenses or adjust policy via `check_license_compatibility(policy=...)`."
        )
        return False

    if warnings or unknowns:
        console.print("\n[yellow]⚠ Review warnings before production use.[/yellow]")

    console.print("\n[green]✅ All packages meet the license policy.[/green]")
    return True


async def _check_deprecated(args):
    """Check lock file packages for deprecated/yanked versions."""
    directory = Path(getattr(args, "directory", ".")).resolve()
    lock_path = _resolve_lock_path(
        directory,
        workspace=getattr(args, "workspace", None),
        lock_file=getattr(args, "lock_file", None),
    )
    if not lock_path.is_file():
        console.print(f"[red]No lock file found at {lock_path.name}[/red]")
        console.print("Run [bold]udr lock[/bold] first to generate one.")
        sys.exit(1)

    lock_data = _read_lock_file(lock_path)
    packages = lock_data.get("packages", {})
    if not packages:
        console.print("[yellow]Lock file has no packages to check.[/yellow]")
        return True

    deprecated: list[tuple[str, str, str]] = []  # name, version, label (deprecated/yanked)

    for pname, pinfo in packages.items():
        ver = pinfo.get("resolved_version", "")
        if pinfo.get("yanked"):
            deprecated.append((pname, ver, "yanked"))
        elif pinfo.get("deprecated"):
            deprecated.append((pname, ver, "deprecated"))

    if not deprecated:
        console.print("[green]✅ No deprecated or yanked packages found.[/green]")
        return True

    table = Table(
        title=f"[yellow]{len(deprecated)} deprecated/yanked package(s)[/yellow]",
        box=box.ROUNDED,
    )
    table.add_column("Package", style="cyan")
    table.add_column("Version", style="dim")
    table.add_column("Status")

    for pname, ver, label in deprecated:
        styl = "bold red" if label == "yanked" else "yellow"
        table.add_row(pname, ver, f"[{styl}]{label}[/{styl}]")

    console.print(table)

    if any(label == "yanked" for _, _, label in deprecated):
        console.print("\n[red]✗ Some packages are yanked — they may be unsafe to use.[/red]")
        return False

    console.print("\n[yellow]⚠ Some packages are deprecated — consider upgrading.[/yellow]")
    return True


async def _check_policy(args):
    """Check lock file packages against project policy file."""
    directory = Path(getattr(args, "directory", ".")).resolve()
    policy_path = getattr(args, "policy", None)
    if not policy_path or policy_path == "udr-policy.yaml":
        candidate = directory / "udr-policy.yaml"
        if not candidate.is_file():
            console.print("[red]Policy file not found:[/red] expected ./udr-policy.yaml")
            console.print("Create one or pass an explicit path via --policy ./custom.yaml")
            sys.exit(1)
        policy_path = candidate
    else:
        policy_path = Path(policy_path)
        if not policy_path.is_absolute():
            policy_path = directory / policy_path

    try:
        policy = load_policy(str(policy_path))
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Policy load failed:[/red] {exc}")
        sys.exit(1)

    lock_path = _resolve_lock_path(
        directory,
        workspace=getattr(args, "workspace", None),
        lock_file=getattr(args, "lock_file", None),
    )
    if not lock_path.is_file():
        console.print(f"[red]No lock file found at {lock_path.name}[/red]")
        console.print("Run [bold]udr lock[/bold] first to generate one.")
        sys.exit(1)

    lock_data = _read_lock_file(lock_path)
    violations = check_policy(lock_data, policy)

    if getattr(args, "json", False):
        return _output_json({"policy": str(policy_path), "violations": violations}, args)

    if not violations:
        console.print("[green]✅ All policy checks passed.[/green]")
        return True

    title = f"[red]{len(violations)} policy violation(s)[/red]"
    has_error = any(v.get("severity") == "error" for v in violations)

    table = Table(title=title, box=box.ROUNDED)
    table.add_column("Rule", style="cyan")
    table.add_column("Package", style="yellow")
    table.add_column("Severity")
    table.add_column("Message")

    for v in violations:
        rule = v.get("rule", "?")
        pkg = v.get("package", "?")
        sev = v.get("severity", "error")
        msg = v.get("message", "")
        sev_style = "bold red" if sev == "error" else "yellow"
        table.add_row(rule, pkg, f"[{sev_style}]{sev}[/{sev_style}]", msg)

    console.print(table)

    if has_error:
        console.print("\n[red]✗ Policy violations with 'error' severity found.[/red]")
        sys.exit(1)

    console.print("\n[yellow]⚠ Policy violations found (warnings only).[/yellow]")
    return True
