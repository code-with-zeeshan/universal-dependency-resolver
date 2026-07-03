"""Module docstring."""

import asyncio
import json
import sys
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.table import Table

from ..shared import (
    _aggregator_to_resolver_input,
    _extract_severity,
    _output_json,
    _run_resolution,
    _select_manifests_interactive,
    _validate_manifest_update_line,
    console,
    err_console,
)


def cmd_lock(args):
    """Cmd lock."""
    from backend.core import ConflictResolver, DataAggregator, SystemScanner
    from backend.core.export_generator import ExportGenerator
    from backend.manifest_detector import ManifestDetector

    async def _lock():
        """Lock."""
        directory = Path(args.directory).resolve()
        if not directory.is_dir():
            console.print(f"[red]Directory not found:[/red] {directory}")
            return 1

        detector = ManifestDetector(str(directory))
        aggregator = DataAggregator()
        resolver = ConflictResolver()
        scanner = SystemScanner()
        exporter = ExportGenerator()

        with Progress(
            SpinnerColumn(),
            TextColumn("Scanning for manifests..."),
            transient=True,
            console=err_console,
        ) as p:
            p.add_task("detect", total=None)
            manifests = detector.detect()

        if not manifests:
            console.print(f"[red]No dependency manifests found in {directory}[/red]")
            console.print(
                "Checked for: requirements.txt, package.json, Cargo.toml, pyproject.toml,"
            )
            console.print("             Pipfile, environment.yml, Gemfile, go.mod, composer.json")
            return 1

        if args.manifest:
            target = args.manifest.replace("\\", "/")
            manifests = [
                m
                for m in manifests
                if m["filename"] == target or m["path"].replace("\\", "/").endswith("/" + target)
            ]
            if not manifests:
                console.print(f"[red]Manifest '{args.manifest}' not found in {directory}[/red]")
                return 1

        if args.interactive:
            manifests = _select_manifests_interactive(manifests)

        if not getattr(args, "json", False):
            manifest_table = Table(title=f"Selected {len(manifests)} manifest(s)", box=box.SIMPLE)
            manifest_table.add_column("Ecosystem", style="cyan")
            manifest_table.add_column("Filename")
            for m in manifests:
                manifest_table.add_row(m["ecosystem"], m["filename"])
            console.print(manifest_table)

        packages = detector.normalize(detector.parse_all(manifests))
        if not packages:
            console.print("[red]No packages found in manifests[/red]")
            return 1

        if not getattr(args, "json", False):
            pkg_table = Table(title=f"Found {len(packages)} package(s)", box=box.SIMPLE)
            pkg_table.add_column("Ecosystem", style="cyan")
            pkg_table.add_column("Package")
            pkg_table.add_column("Constraint")
            pkg_table.add_column("Source")
            for pkg in packages:
                pkg_table.add_row(pkg["ecosystem"], pkg["name"], pkg["constraint"], pkg["source"])
            console.print(pkg_table)

        seen = set()
        resolver_inputs = []
        package_details = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[green]{task.completed}/{task.total}[/green]"),
            console=err_console,
        ) as progress:
            fetch_task = progress.add_task("Fetching package metadata...", total=len(packages))

            async def fetch_one(pkg):
                """Fetch one."""
                key = (pkg["name"], pkg["ecosystem"])
                if key in seen:
                    return None
                seen.add(key)
                progress.update(fetch_task, description=f"Fetching [cyan]{pkg['name']}[/cyan]...")
                try:
                    data = await aggregator.get_package_info(
                        pkg["name"],
                        ecosystem=pkg["ecosystem"],
                        include_dependencies=True,
                        include_versions=True,
                    )
                    if data:
                        return (pkg, data)
                except Exception as exc:
                    err_console.print(f"  [red]Error fetching {pkg['name']}:[/red] {exc}")
                return None

            results = await asyncio.gather(*[fetch_one(p) for p in packages])

            for pkg, result in zip(packages, results):
                if result:
                    _, data = result
                    package_details[pkg["name"]] = data
                    rinput = _aggregator_to_resolver_input(
                        data, pkg["ecosystem"], constraint=pkg.get("constraint")
                    )
                    resolver_inputs.append(rinput)
                progress.advance(fetch_task)

        if not resolver_inputs:
            console.print("[red]No package data could be fetched[/red]")
            return 1

        with Progress(
            SpinnerColumn(),
            TextColumn("Scanning system..."),
            transient=True,
            console=err_console,
        ) as p:
            p.add_task("system", total=None)
            system_info = await scanner.scan_all()

        if args.cuda is not None:
            if "gpu" not in system_info:
                system_info["gpu"] = {}
            system_info["gpu"]["available"] = True
            system_info["gpu"]["cuda"] = args.cuda

        if args.device is not None:
            if args.device == "cpu":
                if "gpu" not in system_info:
                    system_info["gpu"] = {}
                system_info["gpu"]["available"] = False
                system_info["gpu"]["cuda"] = ""
            elif args.device == "mps":
                if "gpu" not in system_info:
                    system_info["gpu"] = {}
                system_info["gpu"]["available"] = True
                system_info["gpu"]["type"] = "mps"
                system_info["gpu"]["cuda"] = ""
            elif args.device == "cuda":
                if "gpu" not in system_info:
                    system_info["gpu"] = {"available": True, "type": "cuda"}
                system_info["gpu"]["available"] = True
                system_info["gpu"]["type"] = "cuda"

        with Progress(
            SpinnerColumn(),
            TextColumn("Resolving dependencies..."),
            transient=True,
            console=err_console,
        ) as p:
            p.add_task("SAT solver", total=None)
            resolved = await _run_resolution(
                aggregator,
                resolver,
                resolver_inputs,
                system_info,
                package_details,
                interactive=args.interactive,
            )

        resolved_pkgs = resolved.get("resolved_packages", {})
        plat = system_info.get("platform", {})
        gpu_info = system_info.get("gpu", {})
        gpu_name = None
        if gpu_info.get("available"):
            gpu_devices = gpu_info.get("devices", [])
            if gpu_devices:
                gpu_name = gpu_devices[0].get("name")
        lock_data = {
            "version": "2.0",
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "resolver": "sat",
            "system": {
                "os": f"{plat.get('system', '?')} {plat.get('release', '?')}",
                "python": system_info.get("runtime_versions", {})
                .get("python", {})
                .get("version", "?"),
                "cpu": system_info.get("cpu", {}).get("brand", "Unknown"),
                "gpu": gpu_name,
                "cuda": gpu_info.get("cuda") if gpu_info.get("available") else None,
            },
            "manifests": [m["filename"] for m in manifests],
            "packages": {},
            "warnings": resolved.get("warnings", []),
        }

        manifest_pkg_info = {}
        for p in packages:
            manifest_pkg_info[p["name"]] = {
                "constraint": p.get("constraint", "*"),
                "source": p.get("source", "unknown"),
            }

        for pkg_name, rp in resolved_pkgs.items():
            manifest_info = manifest_pkg_info.get(pkg_name, {})
            is_direct = pkg_name in manifest_pkg_info
            pkg_detail = package_details.get(pkg_name, {})
            vulns = pkg_detail.get("security", {}).get("vulnerabilities", [])
            lock_data["packages"][pkg_name] = {
                "name": pkg_name,
                "ecosystem": rp.get("ecosystem", "?"),
                "resolved_version": rp.get("version"),
                "direct": is_direct,
                "cuda_variant": rp.get("cuda_variant", False),
                "cuda_version": rp.get("cuda_version"),
                "original_constraint": manifest_info.get("constraint", "*"),
                "source": manifest_info.get("source", "transitive"),
                "vulnerabilities": [
                    {
                        "id": v.get("id", ""),
                        "summary": v.get("summary", ""),
                        "severity": _extract_severity(v),
                        "fixed_version": v.get("fixed_version"),
                    }
                    for v in vulns
                    if v.get("id")
                ],
            }

        if getattr(args, "json", False):
            return _output_json(lock_data, args)

        lock_path = directory / "udr.lock"
        lock_path.write_text(json.dumps(lock_data, indent=2, default=str))
        console.print(f"[green]Lock file saved:[/green] {lock_path}")

        rp_count = len([p for p in lock_data["packages"].values() if p["resolved_version"]])
        total_pkgs = len(lock_data["packages"])
        summary_table = Table(
            title=f"Resolved {rp_count}/{total_pkgs} packages — {lock_path.name}",
            box=box.ROUNDED,
        )
        summary_table.add_column("Package", style="cyan")
        summary_table.add_column("Ecosystem")
        summary_table.add_column("Resolved Version", style="bold green")
        summary_table.add_column("Type")
        summary_table.add_column("Notes")

        total_vulns = 0
        for pname, pinfo in lock_data["packages"].items():
            if pinfo["resolved_version"]:
                cuda_str = f"(+cu{pinfo['cuda_version']})" if pinfo.get("cuda_variant") else ""
                ptype = "direct" if pinfo.get("direct") else "transitive"
                vuln_count = len(pinfo.get("vulnerabilities", []))
                vuln_str = f"[red]{vuln_count} CVE[/red]" if vuln_count else ""
                total_vulns += vuln_count
                notes = f"{cuda_str} {vuln_str}".strip()
                summary_table.add_row(
                    pname, pinfo["ecosystem"], pinfo["resolved_version"], ptype, notes
                )
            else:
                summary_table.add_row(pname, pinfo["ecosystem"], "[red]unresolved[/red]", "", "")

        if total_vulns > 0:
            vuln_table = Table(
                title=f"[red]{total_vulns} known vulnerabilities[/red]", box=box.SIMPLE
            )
            vuln_table.add_column("Package", style="cyan")
            vuln_table.add_column("CVE ID", style="yellow")
            vuln_table.add_column("Severity")
            vuln_table.add_column("Summary")
            for pname, pinfo in lock_data["packages"].items():
                for v in pinfo.get("vulnerabilities", []):
                    sev = v.get("severity", "UNKNOWN")
                    sev_tag = (
                        f"[red]{sev}[/red]"
                        if sev in ("CRITICAL", "HIGH")
                        else f"[yellow]{sev}[/yellow]"
                    )
                    vuln_table.add_row(pname, v.get("id", "?"), sev_tag, v.get("summary", "")[:80])
            console.print(vuln_table)

        console.print(summary_table)

        if getattr(args, "report", False):
            try:
                report_lines = [
                    f"UDR Lock Report — {lock_path.name}",
                    f"Generated: {lock_data['generated_at']}",
                    f"Resolved: {rp_count}/{total_pkgs} packages",
                    "",
                ]
                for pname, pinfo in lock_data["packages"].items():
                    ver = pinfo.get("resolved_version") or "unresolved"
                    ptype = "direct" if pinfo.get("direct") else "transitive"
                    vuln_count = len(pinfo.get("vulnerabilities", []))
                    vuln_str = f" ({vuln_count} CVE)" if vuln_count else ""
                    report_lines.append(f"  {pname:40s} {ver:20s} {ptype}{vuln_str}")
                report_path = lock_path.with_suffix(".report.txt")
                report_path.write_text("\n".join(report_lines) + "\n")
                console.print(f"[green]Report saved:[/green] {report_path}")
            except Exception as exc:
                console.print(f"[yellow]Warning: could not write report:[/yellow] {exc}")

        if getattr(args, "export", None):
            export_format = args.export
            with Progress(
                SpinnerColumn(),
                TextColumn(f"Exporting as {export_format}..."),
                transient=True,
                console=err_console,
            ) as p:
                p.add_task("export", total=None)
                try:
                    export_content = exporter.generate(
                        {
                            pname: {
                                "version": pinfo["resolved_version"],
                                "ecosystem": pinfo["ecosystem"],
                            }
                            for pname, pinfo in lock_data["packages"].items()
                            if pinfo["resolved_version"]
                        },
                        format=export_format,
                        system_info=system_info,
                    )
                    export_path = directory / f"udr-output.{export_format.replace('.', '-')}"
                    export_path.write_text(export_content)
                    console.print(f"[green]Exported:[/green] {export_path}")
                except Exception as e:
                    console.print(f"[red]Export failed:[/red] {e}")

        if getattr(args, "dry_run", False):
            console.print("[yellow]── dry run — no files modified ──[/yellow]")
            return 0

        if not getattr(args, "yes", False) and sys.stdin.isatty():
            proceed = Confirm.ask(
                "\nUpdate manifests in-place with pinned versions?", default=False
            )
            if not proceed:
                return 0
        elif not getattr(args, "yes", False):
            console.print(
                "[yellow]Non-interactive mode detected — skipping manifest update.[/yellow]"
            )
            console.print("[yellow]Use --yes to update manifests without prompting.[/yellow]")

        updated_count = 0
        updated_manifests = {}
        for pkg in packages:
            manifest_path = directory / pkg["source"]
            if not manifest_path.is_file():
                continue
            pkg_info = lock_data["packages"].get(pkg["name"])
            if not pkg_info:
                continue
            resolved_ver = pkg_info.get("resolved_version")
            if not resolved_ver:
                continue
            content = manifest_path.read_text(encoding="utf-8", errors="replace")
            constraint = pkg["constraint"]
            if constraint != resolved_ver and not constraint.startswith("=="):
                new_lines = []
                replaced = False
                for line in content.split("\n"):
                    result = _validate_manifest_update_line(line, pkg["name"], resolved_ver)
                    if result is not None and not replaced:
                        new_lines.append(result)
                        replaced = True
                    else:
                        new_lines.append(line)
                if replaced:
                    manifest_path.write_text("\n".join(new_lines) + "\n")
                    updated_count += 1
                    updated_manifests.setdefault(str(manifest_path), []).append(
                        f"{pkg['name']} → {resolved_ver}"
                    )

        if updated_count:
            update_table = Table(
                title=f"[green]Updated {updated_count} packages across {len(updated_manifests)} manifest(s)[/green]",
                box=box.SIMPLE,
            )
            update_table.add_column("Manifest", style="cyan")
            update_table.add_column("Updates")
            for mpath, updates in sorted(updated_manifests.items()):
                rel = Path(mpath).relative_to(directory)
                update_table.add_row(str(rel), "\n".join(updates))
            console.print(update_table)

        await aggregator.close()
        return 0

    try:
        ret = asyncio.run(_lock())
        sys.exit(ret if ret is not None else 0)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Lock Error"))
        sys.exit(1)
