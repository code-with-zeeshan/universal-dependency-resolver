"""Shared CLI helpers for Universal Dependency Resolver."""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from backend.orchestrator import (
    _aggregator_to_resolver_input,
    _extract_cuda_variants,
    _extract_system_requirements,  # noqa: F401 — re-exported via __init__.py
    _normalize_cuda,  # noqa: F401 — re-exported via __init__.py
    _parse_package_spec,  # noqa: F401 — re-exported via __init__.py
    _resolve_transitive,
    _select_best_cuda_variant,
)
from backend.orchestrator import (
    _generate_install_command as _orchestrator_generate_install_command,
)

console = Console()
err_console = Console(stderr=True)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from importlib.metadata import version as _importlib_version

    VERSION = _importlib_version("ud-resolver")
except (ImportError, Exception):
    _ver_path = PROJECT_ROOT / "pyproject.toml"
    VERSION = (
        _ver_path.read_text().split('version = "')[1].split('"')[0]
        if _ver_path.is_file()
        else "unknown"
    )

LOCK_FILE_VERSION = "2.0"
LOCK_SUPPORTED_VERSIONS = {"1.0", "2.0"}


def _extract_severity(vuln: dict) -> str:
    """Extract severity."""
    sev = vuln.get("severity", [])
    if isinstance(sev, list) and sev:
        return sev[0].get("score", sev[0].get("type", "UNKNOWN"))
    if isinstance(sev, str):
        return sev
    return "UNKNOWN"


async def _run_resolution(
    aggregator,
    resolver,
    resolver_inputs,
    system_info,
    package_details,
    interactive: bool = False,
) -> dict:
    """Run resolution."""
    timeout = int(os.environ.get("SOLVER_TIMEOUT", 30))
    try:
        resolved = await asyncio.wait_for(
            _resolve_transitive(aggregator, resolver, resolver_inputs, system_info),
            timeout=timeout,
        )
    except (TimeoutError, Exception) as exc:
        logger.warning("Transitive resolution %s: falling back to alternatives", exc)
        resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)
        resolved["resolved_packages"] = resolved.pop("packages", {})

    if "packages" in resolved and "resolved_packages" not in resolved:
        resolved["resolved_packages"] = resolved.pop("packages")

    resolved = _apply_cuda_variants(resolved, package_details, system_info)

    if interactive and resolved.get("status") == "unsatisfiable":
        err_console.print(
            Panel(
                "[yellow]SAT solver found no valid combination.[/yellow]\n"
                "Resolving manually by selecting alternatives...",
                title="Conflict Detected",
            )
        )
        resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)
        resolved["resolved_packages"] = resolved.pop("packages", {})
        resolved = _apply_cuda_variants(resolved, package_details, system_info)

    return resolved


def _apply_cuda_variants(
    resolved: dict, package_details: dict[str, dict], system_info: dict
) -> dict:
    """Apply cuda variants."""
    resolved_pkgs = resolved.get("resolved_packages", {})
    system_cuda = None
    if system_info and "gpu" in system_info:
        system_cuda = system_info["gpu"].get("cuda")

    has_cuda_variants = False
    for pkg_name, pkg_info in resolved_pkgs.items():
        if pkg_info.get("ecosystem") != "pypi":
            continue
        base_version = pkg_info.get("version", "")
        if not base_version:
            continue

        details = package_details.get(pkg_name, {})
        raw_versions = details.get("versions", {}).get("pypi", [])
        if not raw_versions:
            raw_versions = details.get("versions", {}).get(pkg_info.get("ecosystem", ""), [])

        cuda_variants = _extract_cuda_variants(raw_versions, base_version)
        if cuda_variants:
            has_cuda_variants = True
            if not system_cuda:
                err_console.print(
                    f"  [yellow]⚠ CUDA variant available for {pkg_name} but no GPU detected[/yellow]"
                )
                err_console.print("     Use --cuda <version> to target a specific CUDA version")
                continue
            best = _select_best_cuda_variant(cuda_variants, system_cuda)
            if best and best != base_version:
                resolved_pkgs[pkg_name]["version"] = best
                resolved_pkgs[pkg_name]["cuda_variant"] = True
                resolved_pkgs[pkg_name]["cuda_version"] = next(
                    (v["cuda_version"] for v in cuda_variants if v["version"] == best),
                    None,
                )

    if has_cuda_variants and not system_cuda:
        err_console.print(
            "  [yellow]⚠ CUDA variants exist but were not selected — resolution is CPU-only[/yellow]"
        )

    if resolved_pkgs:
        resolved["resolved_packages"] = resolved_pkgs
    return resolved


def _fetch_package_data(
    aggregator, specs: list[tuple[str, str]]
) -> tuple[list[dict], dict[str, dict]]:
    """Fetch package data."""
    return asyncio.run(_fetch_package_data_async(aggregator, specs))


async def _fetch_package_data_async(
    aggregator, specs: list[tuple[str, str, str | None]]
) -> tuple[list[dict], dict[str, dict]]:
    """Fetch package data async."""
    resolver_inputs = []
    package_details = {}

    async def fetch_one(
        pkg_name: str, eco: str, constraint: str | None
    ) -> tuple[dict, dict] | None:
        """Fetch one."""
        try:
            data = await aggregator.get_package_info(
                pkg_name,
                ecosystem=eco,
                include_dependencies=True,
                include_versions=True,
            )
            if data:
                rinput = _aggregator_to_resolver_input(data, eco, constraint)
                return (rinput, data)
        except Exception as exc:
            err_console.print(f"  [red]Error fetching {pkg_name}:[/red] {exc}")
        return None

    results = await asyncio.gather(*[fetch_one(n, e, c) for n, e, c in specs])

    for spec, result in zip(specs, results):
        pkg_name = spec[0]
        if result:
            rinput, data = result
            resolver_inputs.append(rinput)
            package_details[pkg_name] = data
        else:
            err_console.print(f"  [yellow]Warning:[/yellow] {pkg_name} not found")

    return resolver_inputs, package_details


def _build_resolved_table(resolved: dict, title: str | None = None) -> Table | None:
    """Build resolved table."""
    rp = resolved.get("resolved_packages", {})
    if not rp:
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
    """Output json and exit."""
    json.dump(data, sys.stdout, indent=2, default=str)
    print()
    raise SystemExit(0)


def _read_lock_file(lock_path: Path) -> dict:
    """Read lock file."""
    if not lock_path.is_file():
        console.print(f"[red]Lock file not found:[/red] {lock_path}")
        sys.exit(1)
    try:
        data = json.loads(lock_path.read_text())
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid lock file:[/red] {exc}")
        sys.exit(1)
    ver = data.get("version", "0.0")
    if ver not in LOCK_SUPPORTED_VERSIONS:
        console.print(
            f"[red]Unsupported lock file version: {ver} (expected one of: {', '.join(sorted(LOCK_SUPPORTED_VERSIONS))})[/red]"
        )
        sys.exit(1)
    return data


def _validate_manifest_update_line(line: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Validate manifest update line."""
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "-")):
        return None

    quote = ""
    for q in ['"', "'"]:
        if stripped.startswith(q):
            quote = q
            break

    for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
        if op in stripped:
            before_op = stripped.split(op)[0].strip().strip("\"'")
            if before_op != pkg_name:
                continue
            after_op = stripped.split(op, 1)[1].strip()
            after_op = after_op.split("#")[0].split(" --")[0].strip()
            after_op = after_op.split(";")[0].strip().rstrip("\"'").rstrip(",")
            indent = line[: len(line) - len(line.lstrip())]
            trailing = ""
            raw = line.strip()
            after_version_pos = raw.rfind(after_op) + len(after_op) if after_op else -1
            if after_version_pos > 0:
                trailing = raw[after_version_pos:]
            if quote:
                return f"{indent}{quote}{pkg_name}=={resolved_ver}{quote}{trailing}"
            return f"{indent}{pkg_name}=={resolved_ver}{trailing}"
    if stripped.startswith(pkg_name + " "):
        indent = line[: len(line) - len(line.lstrip())]
        rest = stripped[len(pkg_name) :]
        after_comment = rest.split("#")[0].strip()
        if after_comment and not any(c in after_comment for c in "=<>~!"):
            return f"{indent}{pkg_name}=={resolved_ver}"
    return None


def _select_manifests_interactive(manifests: list[dict]) -> list[dict]:
    """Select manifests interactive."""
    console.print("\n[bold]Detected manifests:[/bold]")
    for i, m in enumerate(manifests, 1):
        console.print(f"  {i}. [{m['ecosystem']}] {m['filename']}")
    choice = input(
        "\nSelect manifests to include (enter numbers comma-separated, or 'all' for all, default: all): "
    ).strip()
    if not choice or choice.lower() == "all":
        return manifests
    try:
        indices = [int(x.strip()) for x in choice.split(",")]
        selected = [manifests[i - 1] for i in indices if 1 <= i <= len(manifests)]
        if not selected:
            console.print("[yellow]No valid selections — using all manifests[/yellow]")
            return manifests
        return selected
    except (ValueError, IndexError):
        console.print("[yellow]Invalid input — using all manifests[/yellow]")
        return manifests


def _update_package_json(
    content: str, pkg_name: str, resolved_ver: str
) -> str | None:
    """Update package.json content with pinned version.

    Replaces version in dependencies, devDependencies, and peerDependencies.
    Returns updated content or None if the package was not found.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    updated = False
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        if section in data and pkg_name in data[section]:
            data[section][pkg_name] = resolved_ver
            updated = True
    if not updated:
        return None
    return json.dumps(data, indent=2) + "\n"


def _update_pubspec_yaml(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update pubspec.yaml content with pinned version.

    Replaces version in dependencies and dev_dependencies sections.
    Returns updated content or None if the package was not found.
    """
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    in_deps = False
    in_dev_deps = False
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped == "dependencies:":
            in_deps = True
            in_dev_deps = False
        elif stripped == "dev_dependencies:":
            in_dev_deps = True
            in_deps = False
        elif stripped == "dependency_overrides:":
            in_deps = False
            in_dev_deps = False
        elif stripped and not stripped.startswith("#") and not indent:
            in_deps = False
            in_dev_deps = False
        if (in_deps or in_dev_deps) and stripped.startswith(pkg_name + ":"):
            new_lines.append(f"{indent}{pkg_name}: {resolved_ver}")
            updated = True
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _generate_install_command(ecosystem: str, packages: list[tuple[str, str]]) -> str | None:
    """Generate install command (delegates to orchestrator)."""
    return _orchestrator_generate_install_command(ecosystem, packages)
