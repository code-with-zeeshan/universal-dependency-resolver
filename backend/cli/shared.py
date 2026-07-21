"""Shared CLI helpers for Universal Dependency Resolver."""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from backend.orchestrator import (  # noqa: F401
    _aggregator_to_resolver_input,
    _extract_cuda_variants,
    _extract_system_requirements,
    _normalize_cuda,
    _parse_package_spec,
    _resolve_transitive,
)
from backend.orchestrator import (
    _apply_cuda_variants as _orchestrator_apply_cuda_variants,
)
from backend.settings import MAX_MANIFEST_SIZE as _MAX_MANIFEST_SIZE

from ._cuda import _extract_severity  # noqa: F401 — re-exported via __init__.py
from ._display import (  # noqa: F401 — re-exported via __init__.py
    _build_resolved_table,
    _generate_install_command,
    _output_json,
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

LOCK_FILE_VERSION = "2.1"
LOCK_SUPPORTED_VERSIONS = {"1.0", "2.0", "2.1"}


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
    cross_deps: list[dict] | None = None,
    include_optional: bool = False,
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
        from backend.settings import SOLVER_TIMEOUT

        timeout = SOLVER_TIMEOUT
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
                cross_deps=cross_deps,
                include_optional=include_optional,
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


def _build_pinning_policy(args: argparse.Namespace) -> Any:
    """Convert CLI args to a PinningPolicy (or None if no pinning flags set)."""
    from backend.core.pinning import PinningPolicy

    pinned: dict[str, str] = {}
    if args.pin:
        for entry in args.pin:
            if "==" in entry:
                name, ver = entry.split("==", 1)
                pinned[name.strip()] = ver.strip()
            else:
                logger.warning("Invalid --pin format '%s' — expected name==version", entry)

    blocked = args.block or []
    pin_mode = args.pin_mode
    freeze = args.freeze

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
    aggregator,
    specs: list[tuple[str, str, str | None]],
    extras: list[str] | None = None,
    include_optional: bool = False,
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
                rinput = _aggregator_to_resolver_input(
                    data, eco, constraint, extras=extras, include_optional=include_optional
                )
                return (rinput, data)
        except Exception as exc:
            err_console.print(f"  [red]Error fetching {pkg_name}:[/red] {exc}")
        return None

    results = await asyncio.gather(
        *[fetch_one(n, e, c) for n, e, c in specs], return_exceptions=True
    )

    for spec, result in zip(specs, results):
        pkg_name = spec[0]
        if isinstance(result, tuple) and result[0]:
            rinput, data = result
            resolver_inputs.append(rinput)
            package_details[pkg_name] = data
        elif result is None:
            err_console.print(f"  [yellow]Warning:[/yellow] {pkg_name} not found")

    return resolver_inputs, package_details


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
    file_size = lock_path.stat().st_size
    if file_size > _MAX_MANIFEST_SIZE:
        console.print(
            f"[red]Lock file too large ({file_size} bytes, "
            f"max {_MAX_MANIFEST_SIZE} bytes):[/red] {lock_path}"
        )
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


# Re-exports for test compatibility
from ._manifest_updaters import (  # noqa: F401
    _get_manifest_updater,
    _update_brewfile,
    _update_build_gradle,
    _update_cabal,
    _update_cargo_toml,
    _update_composer_json,
    _update_environment_yml,
    _update_gemfile,
    _update_gemspec_dependency,
    _update_go_mod,
    _update_mix_exs,
    _update_package_json,
    _update_package_swift,
    _update_packages_config,
    _update_pipfile,
    _update_podfile,
    _update_pom_xml,
    _update_pubspec_yaml,
    _update_pyproject_toml,
    _update_simple,
)


def _build_target_system_info(args: argparse.Namespace, system_info: dict) -> dict | None:
    """Build target system info from --target/--platform/--cuda flags (cross-compilation)."""
    target_os = args.target
    target_arch = args.platform
    target_cuda = args.cuda
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
