"""Module docstring."""

import asyncio
import json
import os
import sys
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.table import Table

from ..shared import (
    _aggregator_to_resolver_input,
    _build_pinning_policy,
    _build_target_system_info,
    _extract_severity,
    _get_manifest_updater,
    _output_json,
    _run_resolution,
    _select_manifests_interactive,
    _validate_manifest_update_line,
    console,
    err_console,
)


def _extract_integrity(pkg_detail: dict, version: str, ecosystem: str) -> str | None:
    """Extract integrity hash from fetched package data by ecosystem."""
    versions = pkg_detail.get("versions") or []
    for v_entry in versions:
        if isinstance(v_entry, dict) and v_entry.get("version") == version:
            dist = v_entry.get("dist", {})
            if isinstance(dist, dict) and dist.get("integrity"):
                return dist["integrity"]
            if isinstance(dist, dict) and dist.get("shasum"):
                return f"sha1:{dist['shasum']}"
            return None
    return None


def _build_lock_tree(manifests: list[dict], directory: Path) -> dict[str, dict[str, dict]]:
    """Parse ecosystem lock files (package-lock.json, yarn.lock) and return lock tree.

    Returns {ecosystem: {package_name: {version, dependencies: {dep_name: constraint}}}}
    """
    from backend.manifest_detector import ManifestDetector

    tree: dict[str, dict[str, dict]] = {}
    for m in manifests:
        fname = m["filename"]
        eco = m["ecosystem"]
        mpath = directory / m["path"] if m["path"].startswith(str(directory)) else Path(m["path"])
        if not mpath.is_file():
            continue
        if fname == "package-lock.json" and eco == "npm":
            parsed = ManifestDetector.parse_package_lock_tree(str(mpath))
            if parsed:
                tree[eco] = parsed
    return tree


def cmd_lock(args):
    """Cmd lock."""
    from backend.core import DataAggregator, SystemScanner
    from backend.core.conflict_resolver import ConflictResolver
    from backend.core.export_generator import ExportGenerator
    from backend.manifest_detector import ManifestDetector
    from backend.orchestrator.resolve import create_solver

    from ..shared import _read_lock_file

    async def _lock():
        """Lock."""
        directory = Path(args.directory).resolve()
        if not directory.is_dir():
            console.print(f"[red]Directory not found:[/red] {directory}")
            return 1

        detector = ManifestDetector(str(directory))
        aggregator = DataAggregator()
        resolver = create_solver()
        scanner = SystemScanner()
        exporter = ExportGenerator()

        workspace = getattr(args, "workspace", None)
        prefix = getattr(args, "prefix", None)
        lock_filename = f"udr-{workspace}.lock" if workspace else "udr.lock"
        lock_path = directory / lock_filename
        existing_lock = None
        if lock_path.is_file() and not getattr(args, "force", False):
            try:
                existing_lock = _read_lock_file(lock_path)
            except SystemExit:
                existing_lock = None

        with Progress(
            SpinnerColumn(),
            TextColumn("Scanning for manifests..."),
            transient=True,
            console=err_console,
        ) as p:
            p.add_task("detect", total=None)
            manifests = detector.detect(include_dev=getattr(args, "include_dev", False))

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
        pinned_ecosystems: set[str] = {"gomodules"}
        lock_source_patterns = (
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "Cargo.lock",
            "composer.lock",
            "Gemfile.lock",
            "poetry.lock",
            "uv.lock",
            "mix.lock",
            "go.sum",
            "Brewfile.lock.json",
        )

        def _is_lock_source(source: str) -> bool:
            return any(source.endswith(p) for p in lock_source_patterns)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[green]{task.completed}/{task.total}[/green]"),
            console=err_console,
        ) as progress:
            fetch_task = progress.add_task("Fetching package metadata...", total=len(packages))
            fetch_semaphore = asyncio.Semaphore(10)

            async def fetch_one(pkg):
                """Fetch one."""
                async with fetch_semaphore:
                    key = (pkg["name"], pkg["ecosystem"])
                    if key in seen:
                        return None
                    seen.add(key)
                    eco = pkg["ecosystem"]
                    constraint = pkg.get("constraint")
                    source = pkg.get("source", "")

                    if _is_lock_source(source) and constraint and constraint != "*":
                        progress.update(
                            fetch_task, description=f"Locked [cyan]{pkg['name']}[/cyan]..."
                        )
                        return (
                            pkg,
                            {
                                "name": pkg["name"],
                                "version": constraint,
                                "versions": [constraint],
                                "dependencies": {},
                                "ecosystem": eco,
                            },
                        )

                    progress.update(
                        fetch_task, description=f"Fetching [cyan]{pkg['name']}[/cyan]..."
                    )
                    try:
                        data = await aggregator.get_package_info(
                            pkg["name"],
                            ecosystem=eco,
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
                    eco = pkg["ecosystem"]
                    constraint = pkg.get("constraint")
                    source = pkg.get("source", "")
                    is_pinned = eco in pinned_ecosystems or _is_lock_source(source)
                    if is_pinned and constraint and constraint != "*":
                        rinput = {
                            "name": pkg["name"],
                            "ecosystem": eco,
                            "version_constraint": constraint,
                            "dependencies": data.get("dependencies", {}),
                            "pinned_version": constraint,
                        }
                    else:
                        pkg_extras = pkg.get("extras")
                        if args.extras and pkg_extras is not None:
                            combined = list(set(pkg_extras + args.extras))
                        elif args.extras:
                            combined = args.extras
                        elif pkg_extras is not None:
                            combined = pkg_extras
                        else:
                            combined = None
                        rinput = _aggregator_to_resolver_input(
                            data, eco, constraint=constraint, extras=combined
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

        # Override system_info with cross-compilation target info (if --target/--platform/--cuda)
        target_info = _build_target_system_info(args, system_info)
        if target_info:
            system_info["target"] = target_info

        # Separate pinned (Go) from SAT-solved packages
        sat_inputs = [r for r in resolver_inputs if "pinned_version" not in r]
        pinned_inputs = [r for r in resolver_inputs if "pinned_version" in r]

        resolved_pkgs: dict = {}
        dep_tree: dict = {}

        if pinned_inputs:
            if not getattr(args, "json", False):
                console.print(
                    f"[cyan]Pinned packages:[/cyan] {len(pinned_inputs)} (recorded directly)"
                )
            for r in pinned_inputs:
                resolved_pkgs[r["name"]] = {
                    "version": r["pinned_version"],
                    "ecosystem": r["ecosystem"],
                    "cuda_variant": False,
                    "cuda_version": None,
                }
                dep_tree[r["name"]] = {"dependencies": r.get("dependencies", {})}

        if not sat_inputs:
            resolved = {"resolved_packages": resolved_pkgs, "dependency_tree": dep_tree}
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("Resolving dependencies..."),
                transient=True,
                console=err_console,
            ) as p:
                p.add_task("SAT solver", total=None)
                lock_tree = _build_lock_tree(manifests, directory)
                resolved = await _run_resolution(
                    aggregator,
                    resolver,
                    sat_inputs,
                    system_info,
                    package_details,
                    interactive=args.interactive,
                    lock_data=existing_lock,
                    timeout=getattr(args, "timeout", None)
                    or int(os.environ.get("SOLVER_TIMEOUT", 120)),
                    lock_tree_data=lock_tree if lock_tree else None,
                    pinning_policy=_build_pinning_policy(args),
                )

            sat_pkgs = resolved.get("resolved_packages", {})
            for name, info in sat_pkgs.items():
                if name not in resolved_pkgs:
                    resolved_pkgs[name] = info
            sat_tree = resolved.get("dependency_tree", {})
            for name, tree_info in sat_tree.items():
                if name not in dep_tree:
                    dep_tree[name] = tree_info
            resolved["resolved_packages"] = resolved_pkgs
            resolved["dependency_tree"] = dep_tree
        plat = system_info.get("platform", {})
        gpu_info = system_info.get("gpu", {})
        gpu_name = None
        if gpu_info.get("available"):
            gpu_devices = gpu_info.get("devices", [])
            if gpu_devices:
                gpu_name = gpu_devices[0].get("name")
        lock_data = {
            "version": "2.1",
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
        if system_info.get("target"):
            lock_data["target"] = system_info["target"]
        if workspace:
            lock_data["workspace"] = workspace

        pp = _build_pinning_policy(args)
        if pp:
            from dataclasses import asdict

            lock_data["pinning_policy"] = {k: v for k, v in asdict(pp).items() if v}

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
            dep_info = pkg_detail.get("_version_metadata", {}).get(rp.get("version", ""), {})
            eco = rp.get("ecosystem", "?")
            ver = rp.get("version", "")
            integrity_val = _extract_integrity(pkg_detail, ver, eco)
            lock_data["packages"][pkg_name] = {
                "name": pkg_name,
                "ecosystem": eco,
                "resolved_version": ver,
                "direct": is_direct,
                "cuda_variant": rp.get("cuda_variant", False),
                "cuda_version": rp.get("cuda_version"),
                "original_constraint": manifest_info.get("constraint", "*"),
                "source": manifest_info.get("source", "transitive"),
                "license": pkg_detail.get("unified_data", {}).get("license"),
                "deprecated": dep_info.get("deprecated", False),
                "yanked": dep_info.get("yanked", False),
                "integrity": integrity_val,
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

        dep_tree = resolved.get("dependency_tree", {})
        for pkg_name in lock_data["packages"]:
            tree_entry = dep_tree.get(pkg_name)
            if not tree_entry:
                lock_data["packages"][pkg_name]["depends_on"] = {}
                continue
            deps = tree_entry.get("dependencies", {})
            dep_names = {}
            for dep_eco, dep_map in deps.items():
                if isinstance(dep_map, dict):
                    for dep_name, dep_constraint in dep_map.items():
                        if dep_name in lock_data["packages"]:
                            dep_names[dep_name] = dep_constraint
            lock_data["packages"][pkg_name]["depends_on"] = dep_names

        # Compute resolution_hash for EVERY package (roots + transitive deps)
        # for full incremental re-resolution. Non-roots derive deps from depends_on.
        for pkg_name, pkg_info in lock_data["packages"].items():
            rinput = next(
                (r for r in resolver_inputs if r["name"] == pkg_name),
                None,
            )
            if rinput:
                pkg_info["resolution_hash"] = ConflictResolver.compute_resolution_hash(
                    rinput["name"],
                    rinput["ecosystem"],
                    rinput.get("version_constraint", "*"),
                    rinput.get("dependencies", {}),
                    system_info,
                )
            else:
                deps_by_eco: dict[str, dict[str, str]] = {}
                for d_name, d_constraint in pkg_info.get("depends_on", {}).items():
                    d_entry = lock_data["packages"].get(d_name, {})
                    d_eco = d_entry.get("ecosystem")
                    if d_eco:
                        deps_by_eco.setdefault(d_eco, {})[d_name] = d_constraint
                pkg_info["resolution_hash"] = ConflictResolver.compute_resolution_hash(
                    pkg_name,
                    pkg_info.get("ecosystem", "?"),
                    pkg_info.get("original_constraint", "*"),
                    deps_by_eco,
                    system_info,
                )

        if prefix:
            prefixed_packages = {}
            for pkg_name, pkg_info in lock_data["packages"].items():
                prefixed_name = f"{prefix}{pkg_name}"
                pkg_info["name"] = prefixed_name
                prefixed_packages[prefixed_name] = pkg_info
                if "depends_on" in pkg_info:
                    pkg_info["depends_on"] = {
                        f"{prefix}{d}" if d in lock_data["packages"] else d: c
                        for d, c in pkg_info["depends_on"].items()
                    }
            lock_data["packages"] = prefixed_packages
            lock_data["package_prefix"] = prefix

        lock_path.write_text(json.dumps(lock_data, indent=2, default=str))

        if not getattr(args, "json", False):
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

        if not getattr(args, "json", False):
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
                        vuln_table.add_row(
                            pname, v.get("id", "?"), sev_tag, v.get("summary", "")[:80]
                        )
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
        elif not getattr(args, "yes", False) and not getattr(args, "json", False):
            err_console.print(
                "[yellow]Non-interactive mode detected — skipping manifest update.[/yellow]"
            )
            err_console.print("[yellow]Use --yes to update manifests without prompting.[/yellow]")

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
            constraint = pkg["constraint"]
            if constraint == resolved_ver or constraint.startswith("=="):
                continue
            filename = manifest_path.name
            content = manifest_path.read_text(encoding="utf-8", errors="replace")
            updater = _get_manifest_updater(filename)
            if updater:
                new_content = updater(content, pkg["name"], resolved_ver)
                if new_content and new_content != content:
                    manifest_path.write_text(new_content)
                    updated_count += 1
                    updated_manifests.setdefault(str(manifest_path), []).append(
                        f"{pkg['name']} → {resolved_ver}"
                    )
            else:
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

        if updated_count and not getattr(args, "json", False):
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

        if getattr(args, "json", False):
            _output_json(lock_data, args)

        await aggregator.close()
        return 0

    try:
        ret = asyncio.run(_lock())
        if ret is not None:
            sys.exit(ret)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Lock Error"))
        sys.exit(1)
