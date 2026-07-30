"""Migrate existing lock files to udr.lock format without re-resolving."""

import argparse
import json
import sys
from pathlib import Path

from ..shared import console, err_console

SUPPORTED_SOURCES: dict[str, str] = {
    "package-lock.json": "package_lock",
    "Cargo.lock": "cargo_lock",
    "poetry.lock": "poetry_lock",
    "uv.lock": "uv_lock",
    "go.sum": "go_sum",
    "Gemfile.lock": "gemfile_lock",
    "composer.lock": "composer_lock",
    "mix.lock": "mix_lock",
    "Package.resolved": "package_resolved",
    "yarn.lock": "yarn_lock",
    "pnpm-lock.yaml": "pnpm_lock",
    "Brewfile.lock.json": "homebrew",
    "Podfile.lock": "cocoapods",
    "Pipfile.lock": "pipfile_lock",
}


def _detect_lock_files(directory: Path) -> list[tuple[str, Path]]:
    """Detect known lock files in the given directory."""
    detected: list[tuple[str, Path]] = []
    for fname in SUPPORTED_SOURCES:
        fp = directory / fname
        if fp.exists():
            detected.append((fname, fp))
    return detected


def cmd_migrate(args: argparse.Namespace) -> None:
    """Migrate existing lock files to udr.lock format."""
    from backend.manifest_detector import ManifestDetector

    directory = Path(args.directory).resolve()
    if not directory.exists():
        err_console.print(f"[red]Directory not found:[/red] {directory}")
        sys.exit(1)

    detected = _detect_lock_files(directory)

    if not detected:
        console.print("[yellow]No supported lock files found.[/yellow]")
        supported_list = "\n  ".join(sorted(SUPPORTED_SOURCES.keys()))
        console.print(f"Supported lock files:\n  {supported_list}")
        sys.exit(0)

    console.print(f"[bold]Found {len(detected)} lock file(s):[/bold]")
    for fname, fp in detected:
        console.print(f"  [cyan]{fname}[/cyan] ({fp.stat().st_size} bytes)")

    if not args.yes:
        from ..shared import prompt_yes_no

        proceed = prompt_yes_no("\nProceed with migration?")
        if not proceed:
            console.print("[yellow]Migration cancelled.[/yellow]")
            sys.exit(0)

    detector = ManifestDetector()
    all_packages: dict[str, dict[str, object]] = {}
    ecosystem_map: dict[str, str] = {}
    system_info: dict[str, object] = {}

    for fname, fp in detected:
        content = fp.read_text(encoding="utf-8", errors="replace")
        SUPPORTED_SOURCES[fname]
        try:
            parsed = detector.parse_source(content, filename=fname)
        except Exception:
            err_console.print(f"[red]Failed to parse {fname}:[/red] {sys.exc_info()[1]}")
            continue

        eco = args.ecosystem or _detect_ecosystem(fname, parsed)
        pkg_count = 0
        for pkg in parsed:
            name = pkg.get("name", "")
            version = pkg.get("version") or pkg.get("resolved_version", "")
            if not name or not version:
                continue
            if name not in all_packages:
                all_packages[name] = {
                    "resolved_version": version,
                    "ecosystem": pkg.get("_ecosystem") or eco,
                    "source": fname,
                }
                pkg_count += 1
            ecosystem_map[name] = pkg.get("_ecosystem") or eco

        console.print(f"  [green]→[/green] {pkg_count} packages from [cyan]{fname}[/cyan]")

    if not all_packages:
        console.print("[red]No packages extracted from any lock file.[/red]")
        sys.exit(1)

    if args.display:
        console.print(f"\n[bold]{len(all_packages)} packages ready for migration:[/bold]")
        for i, (name, info) in enumerate(sorted(all_packages.items())[:20], 1):
            eco_display = ecosystem_map.get(name, "?")
            console.print(
                f"  {i:>3}. {name} [yellow]{info['resolved_version']}[/yellow] ({eco_display})"
            )
        if len(all_packages) > 20:
            console.print(f"  ... and {len(all_packages) - 20} more")
        return

    lock_data: dict[str, object] = {
        "version": "2.1",
        "created_at": __import__("datetime").datetime.now().isoformat(),
        "tools": [
            {
                "name": "universal-dependency-resolver",
                "action": "migrate",
                "version": __import__("backend.cli.shared", fromlist=["VERSION"]).VERSION,
            }
        ],
        "system_info": system_info or {"target": {}, "host": {}},
        "packages": {
            name: {
                "resolved_version": info["resolved_version"],
                "ecosystem": ecosystem_map[name],
                "source": info["source"],
            }
            for name, info in all_packages.items()
        },
        "resolved_packages": list(all_packages.keys()),
    }

    output_path = directory / "udr.lock"
    if output_path.exists() and not args.force:
        err_console.print("[red]udr.lock already exists. Use --force to overwrite.[/red]")
        sys.exit(1)

    output_path.write_text(json.dumps(lock_data, indent=2) + "\n")
    console.print(
        f"\n[green]✓[/green] Migrated {len(all_packages)} packages to [bold]{output_path}[/bold]"
    )

    console.print("\n[bold]Next steps:[/bold]")
    console.print("  udr verify            # validate the migrated lock file")
    console.print("  udr check --cve       # check for vulnerabilities")
    console.print("  udr outdated          # check for newer versions")


def _detect_ecosystem(fname: str, parsed: list[dict]) -> str:
    """Detect primary ecosystem from parsed packages."""
    if parsed:
        first_eco = parsed[0].get("_ecosystem") or parsed[0].get("ecosystem", "")
        if first_eco:
            return first_eco
    eco_map = {
        "package-lock.json": "npm",
        "Cargo.lock": "crates",
        "poetry.lock": "pypi",
        "uv.lock": "pypi",
        "go.sum": "gomodules",
        "Gemfile.lock": "rubygems",
        "composer.lock": "packagist",
        "mix.lock": "hex",
        "Package.resolved": "swift",
        "yarn.lock": "npm",
        "pnpm-lock.yaml": "npm",
        "Brewfile.lock.json": "homebrew",
        "Podfile.lock": "cocoapods",
        "Pipfile.lock": "pypi",
    }
    return eco_map.get(fname, "pypi")


def add_migrate_parser(sub: argparse._SubParsersAction) -> None:
    """Add the migrate subparser."""
    migrate_p = sub.add_parser(
        "migrate",
        help="Migrate existing lock files (package-lock.json, Cargo.lock, etc.) to udr.lock",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr migrate                   # auto-detect, migrate
  udr migrate --display          # preview only
  udr migrate --force
""",
    )
    migrate_p.add_argument(
        "--directory",
        "-d",
        default=".",
        help="Project directory (default: current directory)",
    )
    migrate_p.add_argument(
        "--ecosystem",
        "-e",
        default=None,
        help="Override detected ecosystem for all packages",
    )
    migrate_p.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite existing udr.lock",
    )
    migrate_p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    migrate_p.add_argument(
        "--display",
        action="store_true",
        help="Display what would be migrated without writing",
    )
