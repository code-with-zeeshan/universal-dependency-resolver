"""Shared CLI helpers for Universal Dependency Resolver."""

import asyncio
import json
import logging
import os
import re
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
)
from backend.orchestrator import (
    _apply_cuda_variants as _orchestrator_apply_cuda_variants,
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
LOCK_SUPPORTED_VERSIONS = {"1.0", "2.0", "2.1"}


def _extract_severity(vuln: dict) -> str:
    """Extract severity."""
    sev = vuln.get("severity", [])
    if isinstance(sev, list) and sev:
        return sev[0].get("score", sev[0].get("type", "UNKNOWN"))
    if isinstance(sev, str):
        return sev
    return "UNKNOWN"


async def _check_and_sync_indexes(
    ecosystem_hints: set[str] | None = None,
    auto_sync: bool = False,
) -> int:
    """Check local index freshness and auto-sync stale indexes.

    When ``INDEX_AUTO_SYNC`` is set or ``auto_sync`` is True, checks each
    ecosystem that has a local index.  If the index is older than
    ``INDEX_SYNC_AGE_HOURS``, triggers a sync.

    Returns the total number of packages synced.
    """
    from backend.settings import ENABLE_LOCAL_INDEX as _ENABLE_LOCAL_INDEX
    from backend.settings import INDEX_AUTO_SYNC as _INDEX_AUTO_SYNC
    from backend.settings import INDEX_SYNC_AGE_HOURS as _INDEX_SYNC_AGE_HOURS

    if not _ENABLE_LOCAL_INDEX and not auto_sync:
        return 0
    if not _INDEX_AUTO_SYNC and not auto_sync:
        return 0

    from backend.core.local_index import LocalIndexManager
    from backend.core.offline_index import list_indexes

    mgr = LocalIndexManager(update_interval=_INDEX_SYNC_AGE_HOURS * 3600)
    indexes = list_indexes()
    if ecosystem_hints:
        indexes = [e for e in indexes if e in ecosystem_hints]

    stale = [eco for eco in indexes if mgr.needs_sync(eco)]
    if not stale:
        return 0

    err_console.print(f"\n[dim]Auto-syncing {len(stale)} stale local index(es)...[/dim]")
    from backend.core import DataAggregator

    aggregator = DataAggregator()
    total = 0
    for eco in stale:
        try:
            n = await aggregator.sync_local_index(eco)
            if n > 0:
                err_console.print(f"  [green]Synced {n} packages for {eco}[/green]")
            else:
                err_console.print(f"  [yellow]{eco}: up to date[/yellow]")
            total += n
        except Exception as e:
            err_console.print(f"  [red]{eco}: sync failed — {e}[/red]")
    await aggregator.close()
    if total > 0:
        err_console.print(f"[dim]Auto-sync complete: {total} packages updated[/dim]\n")
    return total


async def _run_resolution(
    aggregator,
    resolver,
    resolver_inputs,
    system_info,
    package_details,
    interactive: bool = False,
    lock_data: dict | None = None,
    timeout: int | None = None,
    lock_tree_data: dict[str, dict[str, dict]] | None = None,
    pinning_policy: Any = None,
    incremental: bool = True,
) -> dict:
    """Run resolution."""
    from backend.core.pinning import PinningPolicy, apply_pinning_policy, freeze_from_lock

    if pinning_policy is not None and not isinstance(pinning_policy, PinningPolicy):
        pinning_policy = (
            PinningPolicy(**pinning_policy) if isinstance(pinning_policy, dict) else None
        )

    if pinning_policy and pinning_policy.freeze and lock_data:
        resolver_inputs = freeze_from_lock(resolver_inputs, lock_data)
    resolver_inputs = apply_pinning_policy(resolver_inputs, pinning_policy)

    if timeout is None:
        timeout = int(os.environ.get("SOLVER_TIMEOUT", 120))
    bfs_budget = min(240, int(timeout * 0.75))
    solver_timeout = max(10000, int((timeout - bfs_budget) * 1000))
    try:
        resolved = await asyncio.wait_for(
            _resolve_transitive(
                aggregator,
                resolver,
                resolver_inputs,
                system_info,
                lock_data=lock_data,
                solver_timeout=solver_timeout,
                lock_tree_data=lock_tree_data,
                bfs_timeout=bfs_budget,
                incremental=incremental,
            ),
            timeout=timeout,
        )
    except (TimeoutError, Exception) as exc:
        logger.warning("Transitive resolution %s: falling back to alternatives", exc)
        if hasattr(resolver, "_resolve_with_alternatives"):
            resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)
            resolved["resolved_packages"] = resolved.pop("packages", {})
        else:
            resolved = {}

    if "packages" in resolved and "resolved_packages" not in resolved:
        resolved["resolved_packages"] = resolved.pop("packages")

    resolved = _orchestrator_apply_cuda_variants(resolved, package_details, system_info)

    if resolved.get("resolved_packages"):
        _emit_cuda_notifications(resolved, package_details, system_info)

    if interactive and resolved.get("status") == "unsatisfiable":
        err_console.print(
            Panel(
                "[yellow]SAT solver found no valid combination.[/yellow]\n"
                "Resolving manually by selecting alternatives...",
                title="Conflict Detected",
            )
        )
        if hasattr(resolver, "_resolve_with_alternatives"):
            resolved = resolver._resolve_with_alternatives(resolver_inputs, system_info)
            resolved["resolved_packages"] = resolved.pop("packages", {})
        resolved = _orchestrator_apply_cuda_variants(resolved, package_details, system_info)
        _emit_cuda_notifications(resolved, package_details, system_info)

    return resolved


def _build_pinning_policy(args) -> Any:
    """Convert CLI args to a PinningPolicy (or None if no pinning flags set)."""
    from backend.core.pinning import PinningPolicy

    pinned: dict[str, str] = {}
    if getattr(args, "pin", None):
        for entry in args.pin:
            if "==" in entry:
                name, ver = entry.split("==", 1)
                pinned[name.strip()] = ver.strip()
            else:
                logger.warning("Invalid --pin format '%s' — expected name==version", entry)

    blocked = getattr(args, "block", None) or []
    pin_mode = getattr(args, "pin_mode", "none")
    freeze = getattr(args, "freeze", False)

    if not pinned and pin_mode == "none" and not blocked and not freeze:
        return None

    return PinningPolicy(
        pin_mode=pin_mode,
        pinned=pinned,
        blocked=blocked,
        freeze=freeze,
    )


def _emit_cuda_notifications(
    resolved: dict, package_details: dict[str, dict], system_info: dict
) -> None:
    """Print CLI-specific CUDA notifications to stderr."""
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
        if pkg_info.get("cuda_variant"):
            has_cuda_variants = True

    if has_cuda_variants and not system_cuda:
        err_console.print(
            "  [yellow]⚠ CUDA variants exist but were not selected — resolution is CPU-only[/yellow]"
        )

    for pkg_name, pkg_info in resolved_pkgs.items():
        if pkg_info.get("ecosystem") != "pypi":
            continue
        details = package_details.get(pkg_name, {})
        raw_versions = _get_raw_versions(details, pkg_info)
        if not raw_versions:
            continue
        cuda_variants = _extract_cuda_variants(raw_versions, pkg_info.get("version", ""))
        if cuda_variants and not system_cuda:
            err_console.print(
                f"  [yellow]⚠ CUDA variant available for {pkg_name} but no GPU detected[/yellow]"
            )
            err_console.print("     Use --cuda <version> to target a specific CUDA version")


def _get_raw_versions(details: dict, pkg_info: dict) -> list:
    versions_data = details.get("versions", {})
    if isinstance(versions_data, list):
        return versions_data
    raw = versions_data.get("pypi", [])
    if not raw:
        raw = versions_data.get(pkg_info.get("ecosystem", ""), [])
    return raw


def _fetch_package_data(
    aggregator, specs: list[tuple[str, str]]
) -> tuple[list[dict], dict[str, dict]]:
    """Fetch package data."""
    return asyncio.run(_fetch_package_data_async(aggregator, specs))


async def _fetch_package_data_async(
    aggregator, specs: list[tuple[str, str, str | None]], extras: list[str] | None = None
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
                rinput = _aggregator_to_resolver_input(data, eco, constraint, extras=extras)
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


def _resolve_lock_path(
    directory: Path,
    workspace: str | None = None,
    lock_file: str | None = None,
) -> Path:
    """Resolve lock file path from directory, optional workspace, and optional explicit path.

    Priority:
      1. Explicit lock_file path (resolved relative to cwd if not absolute)
      2. directory / udr-{workspace}.lock  (if workspace is set)
      3. directory / udr.lock
    """
    if lock_file:
        p = Path(lock_file)
        return p if p.is_absolute() else Path.cwd() / p
    filename = f"udr-{workspace}.lock" if workspace else "udr.lock"
    return directory / filename


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


def _update_package_json(content: str, pkg_name: str, resolved_ver: str) -> str | None:
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
        elif stripped == "dependency_overrides:" or (
            stripped and not stripped.startswith("#") and not indent
        ):
            in_deps = False
            in_dev_deps = False
        if (in_deps or in_dev_deps) and stripped.startswith(pkg_name + ":"):
            new_lines.append(f"{indent}{pkg_name}: {resolved_ver}")
            updated = True
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_go_mod(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    in_require_block = False
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped.startswith("require (") and stripped.endswith(")"):
            parts = stripped[len("require (") : -len(")")].strip().split()
            if len(parts) >= 2 and parts[0] == pkg_name:
                new_lines.append(f"{indent}require ({pkg_name} {resolved_ver})")
                updated = True
                continue
            new_lines.append(line)
        elif stripped == "require (":
            in_require_block = True
            new_lines.append(line)
        elif in_require_block and stripped == ")":
            in_require_block = False
            new_lines.append(line)
        elif in_require_block:
            parts = stripped.split()
            if len(parts) >= 2 and parts[0] == pkg_name:
                trail = " ".join(parts[2:]) if len(parts) > 2 else ""
                comment = " " + trail if trail else ""
                new_lines.append(f"{indent}{pkg_name} {resolved_ver}{comment}")
                updated = True
            else:
                new_lines.append(line)
        elif stripped.startswith("require " + pkg_name + " "):
            trail = stripped[len("require " + pkg_name + " ") :]
            comment = ""
            if "//" in trail:
                comment = " //" + trail.split("//", 1)[1]
            new_lines.append(f"{indent}require {pkg_name} {resolved_ver}{comment}")
            updated = True
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_cargo_toml(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    in_deps = False
    in_sub_dep = False
    sub_dep_name = ""
    dep_sections = {
        "[dependencies]",
        "[build-dependencies]",
        "[dev-dependencies]",
        "[workspace.dependencies]",
    }
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        # Check for [dependencies.pkg_name] sub-table format
        sub_match = re.match(
            r"^\[(dependencies|build-dependencies|dev-dependencies|workspace\.dependencies)\.(.+)\]$",
            stripped,
        )
        if stripped in dep_sections:
            in_deps = True
            in_sub_dep = False
            sub_dep_name = ""
            new_lines.append(line)
        elif sub_match:
            in_deps = False
            in_sub_dep = True
            sub_dep_name = sub_match.group(2)
            new_lines.append(line)
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_deps = False
            in_sub_dep = False
            sub_dep_name = ""
            new_lines.append(line)
        elif in_sub_dep and sub_dep_name == pkg_name and stripped.startswith("version"):
            eq_pos = stripped.find("=")
            if eq_pos > 0:
                comment = ""
                after = stripped[eq_pos + 1 :].strip()
                if "#" in after:
                    comment = " #" + after.split("#", 1)[1]
                new_lines.append(f'{indent}version = "{resolved_ver}"{comment}')
                updated = True
                continue
            new_lines.append(line)
        elif in_deps and stripped.startswith(pkg_name):
            eq_pos = stripped.find("=")
            if eq_pos > 0:
                before = stripped[:eq_pos].strip()
                if before == pkg_name:
                    after = stripped[eq_pos + 1 :].strip()
                    after_no_comment = after.split("#")[0].strip() if "#" in after else after
                    has_braces = after_no_comment.startswith("{")
                    comment = ""
                    if "#" in after:
                        comment = " #" + after.split("#", 1)[1]
                    if has_braces:
                        new_lines.append(
                            f'{indent}{pkg_name} = {{ version = "{resolved_ver}" }}{comment}'
                        )
                    else:
                        outer_q = ""
                        for q in ['"', "'"]:
                            if after_no_comment.startswith(q):
                                outer_q = q
                                break
                        if outer_q:
                            new_lines.append(
                                f"{indent}{pkg_name} = {outer_q}{resolved_ver}{outer_q}{comment}"
                            )
                        else:
                            new_lines.append(f'{indent}{pkg_name} = "{resolved_ver}"{comment}')
                    updated = True
                    continue
            new_lines.append(line)
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_gemfile(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped.startswith("gem "):
            for q in ['"', "'"]:
                gem_prefix = f"gem {q}{pkg_name}{q}"
                if stripped.startswith(gem_prefix):
                    rest = stripped[len(gem_prefix) :].strip()
                    if rest.startswith(","):
                        rest = rest[1:].strip()
                    if rest.startswith(","):
                        rest = rest[1:].strip()
                    comment = ""
                    if "#" in rest:
                        comment = " #" + rest.split("#", 1)[1]
                    new_lines.append(f'{indent}gem {q}{pkg_name}{q}, "{resolved_ver}"{comment}')
                    updated = True
                    break
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_composer_json(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    updated = False
    for section in ("require", "require-dev"):
        if section in data and pkg_name in data[section]:
            data[section][pkg_name] = resolved_ver
            updated = True
    if not updated:
        return None
    return json.dumps(data, indent=2) + "\n"


def _update_pyproject_toml(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    try:
        import tomllib

        data = tomllib.loads(content)
    except Exception:
        return None

    # Check if pkg_name exists in either [tool.poetry.dependencies] or [project] dependencies
    found_poetry = False
    found_project = False

    if "tool" in data and "poetry" in data["tool"]:
        for section in ("dependencies", "dev-dependencies"):
            if section in data["tool"]["poetry"] and pkg_name in data["tool"]["poetry"][section]:
                found_poetry = True
                break

    if "project" in data and "dependencies" in data["project"]:
        for dep_str in data["project"]["dependencies"]:
            try:
                from packaging.requirements import Requirement

                req = Requirement(dep_str)
                if req.name == pkg_name:
                    found_project = True
                    break
            except Exception:
                if dep_str.startswith(pkg_name) and any(c in dep_str for c in "=<>~!"):
                    found_project = True
                    break

    if not found_poetry and not found_project:
        return None

    # Now do string-level replacement
    lines = content.split("\n")
    new_lines: list[str] = []
    in_poetry_deps = False
    in_poetry_dev = False
    in_project_deps = False
    updated = False

    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]

        if stripped == "[tool.poetry.dependencies]":
            in_poetry_deps = True
            in_poetry_dev = False
            in_project_deps = False
            new_lines.append(line)
        elif stripped == "[tool.poetry.dev-dependencies]":
            in_poetry_deps = False
            in_poetry_dev = True
            in_project_deps = False
            new_lines.append(line)
        elif stripped.startswith("[tool.poetry") or stripped in ("[project]",):
            in_poetry_deps = False
            in_poetry_dev = False
            in_project_deps = False
            new_lines.append(line)
        elif stripped == "dependencies = [":
            in_project_deps = True
            in_poetry_deps = False
            in_poetry_dev = False
            new_lines.append(line)
        elif stripped.startswith("dependencies = "):
            new_lines.append(line)
        elif stripped == "]":
            in_project_deps = False
            new_lines.append(line)
        elif in_poetry_deps or in_poetry_dev:
            eq_pos = stripped.find("=")
            if eq_pos > 0 and stripped[:eq_pos].strip() == pkg_name:
                comment = ""
                after = stripped[eq_pos + 1 :].strip()
                if "#" in after:
                    comment = " #" + after.split("#", 1)[1]
                for q in ['"', "'"]:
                    if after.startswith(q):
                        outer_q = q
                        break
                else:
                    outer_q = '"'
                new_lines.append(f"{indent}{pkg_name} = {outer_q}{resolved_ver}{outer_q}{comment}")
                updated = True
            else:
                new_lines.append(line)
        elif in_project_deps:
            str_stripped = stripped.strip(",").strip()
            if str_stripped.startswith(('"', "'")):
                raw = str_stripped.strip(",").strip("\"'")
                try:
                    from packaging.requirements import Requirement

                    req = Requirement(raw)
                    match_name = req.name == pkg_name
                except Exception:
                    match_name = raw.startswith(pkg_name) and any(c in raw for c in "=<>~!")
                if match_name:
                    comment = ""
                    if "#" in stripped:
                        comment = " #" + stripped.split("#", 1)[1]
                    trailing_comma = "," if stripped.rstrip().endswith(",") else ""
                    new_lines.append(
                        f'{indent}"{pkg_name}=={resolved_ver}"{trailing_comma}{comment}'
                    )
                    updated = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    return "\n".join(new_lines) + "\n" if updated else None


def _update_build_gradle(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped.startswith(("//", "*", "/*")):
            new_lines.append(line)
            continue
        for prefix in (
            "implementation",
            "api",
            "compile",
            "runtimeOnly",
            "compileOnly",
            "testImplementation",
            "androidTestImplementation",
            "kapt",
            "annotationProcessor",
        ):
            pattern = re.escape(prefix) + r"\s+['\"]" + re.escape(pkg_name) + r"['\"]"
            if re.match(pattern, stripped):
                new_lines.append(f"{indent}{prefix} '{pkg_name}:{resolved_ver}'")
                updated = True
                break
            pattern_full = re.escape(prefix) + r"\s+['\"]" + re.escape(pkg_name) + r":\S+['\"]"
            if re.match(pattern_full, stripped):
                new_lines.append(f"{indent}{prefix} '{pkg_name}:{resolved_ver}'")
                updated = True
                break
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_mix_exs(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        m = re.match(r"\{:\s*" + re.escape(pkg_name) + r'\s*,\s*"[^"]*"\s*\}', stripped)
        if m:
            new_lines.append(f'{indent}{{:{pkg_name}, "{resolved_ver}"}}')
            updated = True
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_package_swift(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        m = re.search(
            r'\.package\(url:\s*"[^"]*'
            + re.escape(pkg_name)
            + r'[^"]*"\s*,\s*from\s*:\s*"([^"]+)"\s*\)',
            stripped,
        )
        if m:
            before = m.group(1)
            new_line = stripped.replace(f'from: "{before}"', f'from: "{resolved_ver}"')
            new_lines.append(f"{indent}{new_line}")
            updated = True
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_podfile(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        for q in ['"', "'"]:
            pattern = f"pod {q}{pkg_name}{q}"
            if stripped.startswith(pattern):
                rest = stripped[len(pattern) :].strip().strip(",").strip()
                comment = ""
                if "#" in rest:
                    comment = " #" + rest.split("#", 1)[1]
                new_lines.append(f'{indent}pod {q}{pkg_name}{q}, "{resolved_ver}"{comment}')
                updated = True
                break
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_gemspec_dependency(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        for prefix in (
            "s.add_dependency",
            "s.add_runtime_dependency",
            "s.add_development_dependency",
            "add_dependency",
            "add_runtime_dependency",
            "add_development_dependency",
        ):
            for q in ['"', "'"]:
                pattern = (
                    re.escape(prefix)
                    + r"\s*\(\s*"
                    + re.escape(q)
                    + re.escape(pkg_name)
                    + re.escape(q)
                )
                if re.match(pattern, stripped):
                    before_rest = stripped[
                        stripped.find(q + pkg_name + q) + len(q + pkg_name + q) :
                    ].strip()
                    comment = ""
                    if "#" in before_rest:
                        comment = " #" + before_rest.split("#", 1)[1]
                    new_lines.append(
                        f'{indent}{prefix} {q}{pkg_name}{q}, "{resolved_ver}"{comment}'
                    )
                    updated = True
                    break
                pattern2 = (
                    re.escape(prefix) + r"\s+" + re.escape(q) + re.escape(pkg_name) + re.escape(q)
                )
                if re.match(pattern2, stripped):
                    before_rest = stripped[
                        stripped.find(q + pkg_name + q) + len(q + pkg_name + q) :
                    ].strip()
                    comment = ""
                    if "#" in before_rest:
                        comment = " #" + before_rest.split("#", 1)[1]
                    new_lines.append(
                        f'{indent}{prefix} {q}{pkg_name}{q}, "{resolved_ver}"{comment}'
                    )
                    updated = True
                    break
            else:
                continue
            break
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_brewfile(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update Brewfile content with pinned version.

    Handles both gem and cask entries.
    """
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        for q in ['"', "'"]:
            for kind in ("brew", "cask", "gem"):
                prefix = f"{kind} {q}{pkg_name}{q}"
                if stripped.startswith(prefix):
                    rest = stripped[len(prefix) :].strip().strip(",").strip()
                    comment = ""
                    if "#" in rest:
                        comment = " #" + rest.split("#", 1)[1]
                    new_lines.append(f'{indent}{kind} {q}{pkg_name}{q}, "{resolved_ver}"{comment}')
                    updated = True
                    break
            else:
                continue
            break
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_pipfile(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update Pipfile content with pinned version.

    Handles both simple (pkg = ">=1.0") and extended (pkg = {version = ">=1.0"}) formats.
    """
    updated = False
    in_packages = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped in ("[packages]", "[dev-packages]"):
            in_packages = True
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_packages = False
        if in_packages and "=" in stripped:
            key = stripped.split("=", 1)[0].strip().strip('"').strip("'")
            if key == pkg_name:
                value_part = stripped.split("=", 1)[1].strip()
                if value_part.startswith("{"):
                    new_lines.append(f'{indent}{pkg_name} = "=={resolved_ver}"')
                else:
                    new_lines.append(f'{indent}{pkg_name} = "=={resolved_ver}"')
                updated = True
                continue
        new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_packages_config(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update packages.config content with pinned version."""
    try:
        import xml.etree.ElementTree as ET
    except Exception:
        return None
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    updated = False
    for pkg_elem in root.findall("package"):
        pid = pkg_elem.get("id", "")
        if pid == pkg_name:
            pkg_elem.set("version", resolved_ver)
            updated = True
    if not updated:
        return None
    result = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    return result + "\n"


def _update_environment_yml(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update environment.yml content with pinned version.

    Handles both conda and pip dependency formats with any operator (=, >=, <=, !=, ~=, ==).
    """
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    in_deps = False
    pip_indent: str | None = None
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped.startswith("dependencies:"):
            in_deps = True
            pip_indent = None
        elif in_deps and stripped == "":
            in_deps = False
            pip_indent = None
        if in_deps and stripped.startswith("- "):
            if stripped == "- pip:":
                pip_indent = indent
                new_lines.append(line)
                continue
            is_pip = pip_indent is not None and len(indent) > len(pip_indent)
            dep = stripped[2:].strip()
            found_op = None
            for op in ["==", ">=", "<=", "!=", "~=", "=", ">", "<"]:
                if op in dep:
                    name = dep.split(op, 1)[0].strip()
                    if name == pkg_name:
                        found_op = op
                        break
            if (found_op is None and dep == pkg_name) or found_op is not None:
                sep = "==" if is_pip else "="
                new_lines.append(f"{indent}- {pkg_name}{sep}{resolved_ver}")
                updated = True
                continue
        new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_cabal(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update .cabal file content with pinned version.

    Handles build-depends entries across continuation lines.
    """
    updated = False
    in_build_depends = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]

        if stripped.startswith("build-depends:"):
            in_build_depends = True
        elif (
            in_build_depends
            and not stripped.startswith(",")
            and not stripped.startswith("build-depends:")
        ):
            in_build_depends = False

        if in_build_depends:
            entry = stripped
            if entry.startswith("build-depends:"):
                entry = entry[len("build-depends:") :].strip()
            elif entry.startswith(","):
                entry = entry[1:].strip()
            parts = entry.split()
            if parts and parts[0] == pkg_name:
                comment = ""
                if "--" in entry:
                    comment = "  --" + entry.split("--", 1)[1]
                if entry.startswith("build-depends:"):
                    new_lines.append(
                        f"{indent}build-depends:    {pkg_name} =={resolved_ver},{comment}"
                    )
                else:
                    new_lines.append(f"{indent}, {pkg_name} =={resolved_ver}{comment}")
                updated = True
                continue

        new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_simple(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update apt-packages.txt / apk-packages.txt content with pinned version."""
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        comment = ""
        if "#" in stripped and not stripped.startswith("#"):
            comment = " #" + stripped.split("#", 1)[1]
            stripped = stripped.split("#", 1)[0].strip()
        matched = False
        for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
            if op in stripped:
                n, _ = stripped.split(op, 1)
                if n.strip() == pkg_name:
                    new_lines.append(f"{indent}{pkg_name}=={resolved_ver}{comment}")
                    updated = True
                    matched = True
                    break
                break
        if not matched:
            if stripped == pkg_name:
                new_lines.append(f"{indent}{pkg_name}=={resolved_ver}{comment}")
                updated = True
            else:
                new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_pom_xml(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update Maven pom.xml with pinned version using namespace-aware XML parsing."""
    try:
        import xml.etree.ElementTree as ET
    except ImportError:
        return None
    try:
        root = ET.fromstring(content)
    except Exception:
        return None
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    updated = False
    for dep in root.findall(".//m:dependencies/m:dependency", ns):
        group = dep.find("m:groupId", ns)
        artifact = dep.find("m:artifactId", ns)
        version = dep.find("m:version", ns)
        if group is not None and artifact is not None:
            name = f"{group.text}:{artifact.text}"
            if name == pkg_name and version is not None:
                version.text = resolved_ver
                updated = True
    if not updated:
        return None
    ET.register_namespace("", ns["m"])
    result = ET.tostring(root, encoding="unicode", xml_declaration=True)
    return result + "\n"


def _build_target_system_info(args: Any, system_info: dict) -> dict | None:
    """Build target system info from --target/--platform/--cuda flags (cross-compilation)."""
    target_os = getattr(args, "target", None)
    target_arch = getattr(args, "platform", None)
    target_cuda = getattr(args, "cuda", None)
    if not any([target_os, target_arch, target_cuda]):
        return None
    result: dict = {}
    if target_os:
        result["os"] = target_os
    if target_arch:
        arch = target_arch
        if arch in ("amd64",):
            arch = "x86_64"
        elif arch in ("arm64",):
            arch = "aarch64"
        result["architecture"] = arch
    if target_cuda:
        result["cuda"] = target_cuda
    return result


def _get_manifest_updater(filename: str):
    _updaters = {
        "package.json": _update_package_json,
        "pubspec.yaml": _update_pubspec_yaml,
        "go.mod": _update_go_mod,
        "Cargo.toml": _update_cargo_toml,
        "Gemfile": _update_gemfile,
        "composer.json": _update_composer_json,
        "pyproject.toml": _update_pyproject_toml,
        "build.gradle": _update_build_gradle,
        "build.gradle.kts": _update_build_gradle,
        "Package.swift": _update_package_swift,
        "mix.exs": _update_mix_exs,
        "Podfile": _update_podfile,
        "Brewfile": _update_brewfile,
        "Pipfile": _update_pipfile,
        "packages.config": _update_packages_config,
        "environment.yml": _update_environment_yml,
        "apt-packages.txt": _update_simple,
        "apk-packages.txt": _update_simple,
        "pom.xml": _update_pom_xml,
    }
    if filename in _updaters:
        return _updaters[filename]
    if filename.endswith(".gemspec"):
        return _update_gemspec_dependency
    if filename.endswith(".cabal"):
        return _update_cabal
    # Check plugin registry for ecosystem-specific updaters
    try:
        from backend.core.plugin import get_all_plugins

        for eco, cls in get_all_plugins().items():
            for mf in cls.manifests:
                if mf.glob == filename:
                    update_method = getattr(cls, f"update_{mf.parser}", None)
                    if update_method is not None:
                        return update_method
    except ImportError:
        pass
    return None


def _generate_install_command(
    ecosystem: str,
    packages: list[tuple[str, str]],
    cuda_version: str | None = None,
) -> str | None:
    """Generate install command (delegates to orchestrator)."""
    return _orchestrator_generate_install_command(ecosystem, packages, cuda_version=cuda_version)
