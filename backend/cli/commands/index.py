"""Manage offline SQLite indexes for package resolution.

Subcommands
-----------
pull    Download pre-built indexes from a remote URL.
build   Build index locally from resolved packages in a lock file.
status  Show which ecosystems have local indexes available.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from rich import box
from rich.table import Table

from ..shared import _read_lock_file, console, err_console

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------


async def _pull_index_async(url: str, ecosystem: str | None = None) -> int:
    """Download a pre-built SQLite index from *url*."""
    import aiohttp

    from backend.core.offline_index import INDEX_DIR, list_indexes

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    existing = set(list_indexes())

    async with aiohttp.ClientSession() as session:
        if ecosystem:
            urls = [url.rstrip("/") + f"/{ecosystem}.db"]
        else:
            meta_url = url.rstrip("/") + "/index.json"
            err_console.print(f"[dim]Fetching index manifest from {meta_url}...[/dim]")
            try:
                async with session.get(meta_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        err_console.print(
                            f"[red]Failed to fetch manifest: HTTP {resp.status}[/red]"
                        )
                        return 1
                    manifest = await resp.json()
            except Exception as e:
                err_console.print(f"[red]Failed to fetch manifest: {e}[/red]")
                return 1

            ecosystems = manifest.get("ecosystems", [])
            if not ecosystems:
                err_console.print("[red]Manifest contains no ecosystems[/red]")
                return 1
            urls = [url.rstrip("/") + f"/{eco}.db" for eco in ecosystems]

    downloaded = 0
    skipped = 0
    for eco_url in urls:
        eco_name = eco_url.rsplit("/", 1)[-1].replace(".db", "")
        idx_path = INDEX_DIR / f"{eco_name}.db"

        if eco_name in existing:
            err_console.print(f"  [dim]{eco_name}[/dim] — already exists, skipping")
            skipped += 1
            continue

        err_console.print(f"  [dim]Downloading {eco_name}...[/dim]")
        try:
            async with session.get(eco_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status == 404:
                    err_console.print(f"  [yellow]{eco_name} — not found (404)[/yellow]")
                    continue
                if resp.status != 200:
                    err_console.print(
                        f"  [yellow]{eco_name} — HTTP {resp.status}, skipping[/yellow]"
                    )
                    continue
                content = await resp.read()
                idx_path.write_bytes(content)
                downloaded += 1
                err_console.print(f"  [green]OK[/green] ({len(content) / 1024:.0f} KB)")
        except Exception as e:
            err_console.print(f"  [red]{eco_name} — {e}[/red]")

    console.print(
        f"\nDownloaded [green]{downloaded}[/green] index(es), [dim]{skipped} skipped[/dim]"
    )
    return 0


def cmd_index_pull(args):
    """Download pre-built indexes."""
    url = args.url
    ecosystem = getattr(args, "ecosystem", None)
    try:
        sys.exit(asyncio.run(_pull_index_async(url, ecosystem)))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Pull failed: {e}[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# build  — builds index from a lock file's resolved packages
# ---------------------------------------------------------------------------


async def _fetch_and_store_package(
    aggregator,
    eco: str,
    name: str,
    sem: asyncio.Semaphore,
) -> dict | None:
    """Fetch one package's info and return it as an index-ready dict."""
    async with sem:
        try:
            info = await aggregator.get_package_info(
                name,
                ecosystem=eco,
                include_versions=True,
                include_dependencies=True,
            )
            if not info:
                return None
            versions = info.get("versions", {}).get(eco, [])
            deps_data = info.get("dependencies", {}).get(eco, {})
            return {
                "name": name,
                "versions": [
                    {
                        "version": v.get("version", ""),
                        "release_date": v.get("release_date"),
                        "requires_python": v.get("requires_python"),
                        "dependencies": deps_data,
                    }
                    for v in versions
                ],
            }
        except Exception as e:
            logger.debug("Failed to fetch %s/%s: %s", eco, name, e)
            return None


def _resolve_lock_path(args_dir: str | None) -> Path:
    """Return path to udr.lock, defaulting to cwd."""
    base = Path(args_dir).resolve() if args_dir else Path.cwd().resolve()
    return base / "udr.lock"


async def _build_from_lock_async(args) -> int:
    """Build offline indexes from packages listed in ``udr.lock``."""
    from backend.core import DataAggregator
    from backend.core.offline_index import create_or_update_index

    lock_path = _resolve_lock_path(getattr(args, "directory", None))
    if not lock_path.is_file():
        err_console.print(f"[red]Lock file not found: {lock_path}[/red]")
        return 1

    err_console.print(f"[dim]Reading {lock_path}...[/dim]")
    lock_data = _read_lock_file(lock_path)
    packages = lock_data.get("packages", {})
    if not packages:
        err_console.print("[yellow]Lock file contains no packages[/yellow]")
        return 1

    err_console.print(f"[dim]Found {len(packages)} packages in lock file[/dim]")

    aggregator = DataAggregator()
    sem = asyncio.Semaphore(10)

    eco_batches: dict[str, list[dict]] = {}
    errors = 0

    total = len(packages)
    for idx, (pkg_name, pinfo) in enumerate(packages.items(), 1):
        eco = pinfo.get("ecosystem", "pypi")
        err_console.print(f"  [dim][{idx}/{total}] Fetching {pkg_name} ({eco})...[/dim]", end="\r")
        result = await _fetch_and_store_package(aggregator, eco, pkg_name, sem)
        if result:
            eco_batches.setdefault(eco, []).append(result)
        else:
            errors += 1

    err_console.print()

    inserted = 0
    for eco, batch in eco_batches.items():
        try:
            n = create_or_update_index(eco, batch)
            inserted += n
            console.print(f"  [green]Indexed {n} packages for {eco}[/green]")
        except Exception as e:
            err_console.print(f"  [red]Failed to index {eco}: {e}[/red]")

    await aggregator.close()

    console.print(
        f"\n[green]Done:[/green] {inserted} packages indexed, [dim]{errors} fetch errors[/dim]"
    )
    return 0


async def _build_from_names_async(args) -> int:
    """Build index for explicitly named packages."""
    from backend.core import DataAggregator
    from backend.core.offline_index import create_or_update_index

    names = getattr(args, "packages", "").split(",")
    ecosystem = getattr(args, "ecosystem", "pypi")

    aggregator = DataAggregator()
    sem = asyncio.Semaphore(10)

    batch: list[dict] = []
    errors = 0

    for idx, pkg_name in enumerate(names, 1):
        pkg_name = pkg_name.strip()
        if not pkg_name:
            continue
        err_console.print(
            f"  [dim][{idx}/{len(names)}] Fetching {pkg_name} ({ecosystem})...[/dim]",
            end="\r",
        )
        result = await _fetch_and_store_package(aggregator, ecosystem, pkg_name, sem)
        if result:
            batch.append(result)
        else:
            errors += 1

    err_console.print()
    inserted = 0
    if batch:
        try:
            inserted = create_or_update_index(ecosystem, batch)
            console.print(f"  [green]Indexed {inserted} packages for {ecosystem}[/green]")
        except Exception as e:
            err_console.print(f"  [red]Failed to index {ecosystem}: {e}[/red]")

    await aggregator.close()
    console.print(
        f"\n[green]Done:[/green] {inserted} packages indexed, [dim]{errors} fetch errors[/dim]"
    )
    return 0


def cmd_index_build(args):
    """Build offline SQLite index from a lock file or explicit package list."""
    if getattr(args, "packages", None):
        try:
            sys.exit(asyncio.run(_build_from_names_async(args)))
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled by user[/yellow]")
            sys.exit(130)
        except Exception as e:
            console.print(f"[red]Index build failed: {e}[/red]")
            sys.exit(1)
    else:
        try:
            sys.exit(asyncio.run(_build_from_lock_async(args)))
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled by user[/yellow]")
            sys.exit(130)
        except Exception as e:
            console.print(f"[red]Index build failed: {e}[/red]")
            sys.exit(1)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def cmd_index_status(args):
    """Show which ecosystems have local indexes available."""
    from backend.core.offline_index import index_status, list_indexes

    ecosystems = list_indexes()
    if not ecosystems:
        console.print("[yellow]No offline indexes found[/yellow]")
        console.print(
            "  Use [cyan]udr index pull <url>[/cyan] or [cyan]udr index build[/cyan] to create one."
        )
        return

    table = Table(box=box.ROUNDED)
    table.add_column("Ecosystem", style="cyan")
    table.add_column("Packages")
    table.add_column("Versions")
    table.add_column("Size")
    table.add_column("Updated")

    total_pkgs = 0
    total_vers = 0
    total_size = 0

    for eco in ecosystems:
        info = index_status(eco)
        if info is None:
            continue
        meta = info.get("metadata", {})
        updated = meta.get("updated_at", "?")
        total_pkgs += info["packages"]
        total_vers += info["versions"]
        total_size += info["size_bytes"]
        table.add_row(
            eco,
            str(info["packages"]),
            str(info["versions"]),
            _fmt_size(info["size_bytes"]),
            updated,
        )

    if getattr(args, "json", False):
        data = {
            "ecosystems": [
                {
                    "name": eco,
                    "packages": index_status(eco).get("packages", 0) if index_status(eco) else 0,
                    "versions": index_status(eco).get("versions", 0) if index_status(eco) else 0,
                    "size_bytes": index_status(eco).get("size_bytes", 0)
                    if index_status(eco)
                    else 0,
                }
                for eco in ecosystems
                if index_status(eco)
            ],
        }
        json.dump(data, sys.stdout, indent=2)
        print()
        return

    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        str(total_pkgs),
        str(total_vers),
        _fmt_size(total_size),
        "",
    )
    console.print(table)


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024**2:.1f} MB"


# ---------------------------------------------------------------------------
# top-level dispatch
# ---------------------------------------------------------------------------


def cmd_index(args):
    """Dispatch to index subcommands."""
    dispatch = {
        "pull": cmd_index_pull,
        "build": cmd_index_build,
        "status": cmd_index_status,
    }
    action = getattr(args, "index_action", None)
    if action is None:
        console.print("[red]Specify an action: pull, build, or status[/red]")
        sys.exit(1)
    dispatch[action](args)
