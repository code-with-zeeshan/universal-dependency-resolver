"""CLI entry point for Universal Dependency Resolver."""

import argparse
import logging
import os

from backend.settings import ECOSYSTEMS

from .shared import VERSION
from .commands.serve import cmd_serve
from .commands.check import cmd_check
from .commands.resolve import cmd_resolve
from .commands.lock import cmd_lock
from .commands.scan import cmd_scan
from .commands.graph import cmd_graph
from .commands.verify import cmd_verify
from .commands.list_ecosystems import cmd_list_ecosystems
from .commands.update import cmd_update
from .commands.install import cmd_install
from .commands.completion import cmd_completion
from .commands.why import cmd_why
from .commands.outdated import cmd_outdated
from .commands.diff import cmd_diff
from .commands.search import cmd_search
from .commands.details import cmd_details


def _build_parser() -> argparse.ArgumentParser:
    """Build parser."""
    parser = argparse.ArgumentParser(
        prog="udr",
        description="Universal Dependency Resolver — resolve dependencies across ecosystems",
    )
    parser.add_argument("--version", action="version", version=f"udr {VERSION}")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Offline mode: use cached data only, no network requests",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    _eco_choices = [e for e in ECOSYSTEMS if e not in ("docs", "custom_db")]

    serve_p = sub.add_parser("serve", help="Start the API server")
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind address")
    serve_p.add_argument("--port", type=int, default=8000, help="Bind port")
    serve_p.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development"
    )
    serve_p.add_argument(
        "--mode",
        choices=["local", "saas"],
        default="local",
        help="Run mode: local (no auth, default) or saas (full auth stack)",
    )
    serve_p.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Uvicorn log level (default: info)",
    )
    serve_p.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of worker processes (default: 1, auto if not set)",
    )
    serve_p.add_argument(
        "--ssl-keyfile",
        default=None,
        help="SSL key file path for HTTPS",
    )
    serve_p.add_argument(
        "--ssl-certfile",
        default=None,
        help="SSL certificate file path for HTTPS",
    )

    check_p = sub.add_parser("check", help="Check system compatibility")
    check_p.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed info"
    )
    check_p.add_argument(
        "--deps", action="store_true", help="Show project core dependencies"
    )
    check_p.add_argument("--json", action="store_true", help="Output as JSON")
    check_p.add_argument(
        "--cuda",
        help="Target CUDA version (e.g. 12.1) — simulate system check for a specific CUDA config",
    )
    check_p.add_argument(
        "--device",
        choices=["cpu", "cuda", "mps"],
        default=None,
        help="Simulate system check for a specific compute device",
    )

    resolve_p = sub.add_parser(
        "resolve", help="Resolve dependencies for one or more packages"
    )
    resolve_p.add_argument(
        "packages",
        nargs="+",
        help="Package names (use pkg@ecosystem syntax, e.g. numpy@pypi express@npm)",
    )
    resolve_p.add_argument(
        "--ecosystem",
        "-e",
        default="pypi",
        choices=_eco_choices,
        help="Default ecosystem (used for packages without @ecosystem suffix)",
    )
    resolve_p.add_argument(
        "--format", "-f", default="text", choices=["text", "json"], help="Output format"
    )
    resolve_p.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Interactive mode for resolving conflicts manually",
    )
    resolve_p.add_argument(
        "--cuda",
        help="Target CUDA version (e.g. 12.1) — overrides auto-detection for GPU packages",
    )
    resolve_p.add_argument(
        "--device",
        choices=["cpu", "cuda", "mps"],
        default=None,
        help="Target compute device: cpu, cuda (NVIDIA GPU), or mps (Apple Silicon)",
    )

    lock_p = sub.add_parser(
        "lock", help="Auto-detect manifests, resolve all dependencies, write lock file"
    )
    lock_p.add_argument(
        "--directory", "-d", default=".", help="Project directory to scan"
    )
    lock_p.add_argument(
        "--manifest", "-m", help="Only process a specific manifest file"
    )
    lock_p.add_argument(
        "--export",
        help="Export to a specific format (e.g. requirements.txt, Dockerfile)",
    )
    lock_p.add_argument(
        "--yes", "-y", action="store_true", help="Update manifests without prompting"
    )
    lock_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing files",
    )
    lock_p.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Interactive mode: select manifests + resolve conflicts manually",
    )
    lock_p.add_argument(
        "--cuda",
        help="Target CUDA version (e.g. 12.1) — overrides auto-detection for GPU packages",
    )
    lock_p.add_argument(
        "--device",
        choices=["cpu", "cuda", "mps"],
        default=None,
        help="Target compute device: cpu, cuda (NVIDIA GPU), or mps (Apple Silicon)",
    )
    lock_p.add_argument("--json", action="store_true", help="Output lock data as JSON")
    lock_p.add_argument(
        "--report",
        "-r",
        action="store_true",
        help="Write readable report file (udr-lock-report.txt) alongside lock file",
    )

    graph_p = sub.add_parser(
        "graph", help="Show dependency tree for one or more packages"
    )
    graph_p.add_argument(
        "packages",
        nargs="+",
        help="Package names (use pkg@ecosystem syntax)",
    )
    graph_p.add_argument(
        "--ecosystem",
        "-e",
        default="pypi",
        choices=_eco_choices,
        help="Default ecosystem",
    )
    graph_p.add_argument("--json", action="store_true", help="Output as JSON")
    graph_p.add_argument(
        "--cuda",
        help="Target CUDA version (e.g. 12.1) — overrides auto-detection for GPU packages",
    )
    graph_p.add_argument(
        "--device",
        choices=["cpu", "cuda", "mps"],
        default=None,
        help="Target compute device: cpu, cuda (NVIDIA GPU), or mps (Apple Silicon)",
    )

    verify_p = sub.add_parser(
        "verify", help="Validate lock file — check all versions still exist"
    )
    verify_p.add_argument(
        "lock_file",
        nargs="?",
        default="udr.lock",
        help="Path to lock file (default: udr.lock)",
    )
    verify_p.add_argument("--json", action="store_true", help="Output as JSON")

    list_eco_p = sub.add_parser("list-ecosystems", help="List all supported ecosystems")
    list_eco_p.add_argument("--json", action="store_true", help="Output as JSON")

    update_p = sub.add_parser(
        "update", help="Re-resolve a package and update lock file"
    )
    update_p.add_argument("package", help="Package name to re-resolve")
    update_p.add_argument(
        "--directory", "-d", default=".", help="Project directory with lock file"
    )
    update_p.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Interactive mode for resolving conflicts manually",
    )
    update_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without modifying the lock file",
    )
    update_p.add_argument(
        "--cuda",
        help="Target CUDA version (e.g. 12.1) — overrides auto-detection for GPU packages",
    )
    update_p.add_argument(
        "--device",
        choices=["cpu", "cuda", "mps"],
        default=None,
        help="Target compute device: cpu, cuda (NVIDIA GPU), or mps (Apple Silicon)",
    )

    install_p = sub.add_parser(
        "install", help="Install packages from udr.lock lock file"
    )
    install_p.add_argument(
        "--directory", "-d", default=".", help="Project directory with lock file"
    )
    install_p.add_argument(
        "--lock-file",
        "-l",
        help="Path to lock file (default: <directory>/udr.lock)",
    )
    install_p.add_argument(
        "--ecosystem",
        "-e",
        choices=_eco_choices,
        help="Only install packages from this ecosystem",
    )
    install_p.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show install commands without executing",
    )
    install_p.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompt"
    )
    install_p.add_argument(
        "--restore",
        action="store_true",
        help="Restore mode — alias for install (kept for compatibility)",
    )

    completion_p = sub.add_parser(
        "completion",
        help="Generate shell completion script for bash, zsh, or fish",
    )
    completion_p.add_argument(
        "shell",
        nargs="?",
        choices=["bash", "zsh", "fish"],
        help="Shell to generate completions for (auto-detected if omitted)",
    )

    scan_p = sub.add_parser(
        "scan", help="Scan a GitHub repo or local path without manual clone/cd"
    )
    scan_p.add_argument(
        "--github", help="GitHub repository URL (e.g. https://github.com/user/repo)"
    )
    scan_p.add_argument(
        "--branch", default="main", help="Git branch to scan (default: main)"
    )
    scan_p.add_argument("--directory", help="Local project directory to scan")
    scan_p.add_argument(
        "--manifest", "-m", help="Only process a specific manifest file"
    )
    scan_p.add_argument(
        "-y", "--yes", action="store_true", help="Update manifests without prompting"
    )
    scan_p.add_argument("--export", help="Export to a specific format")
    scan_p.add_argument("--json", action="store_true", help="Output lock data as JSON")
    scan_p.add_argument("--cuda", help="Target CUDA version (e.g. 12.1)")
    scan_p.add_argument(
        "--device",
        choices=["cpu", "cuda", "mps"],
        default=None,
        help="Target compute device: cpu, cuda (NVIDIA GPU), or mps (Apple Silicon)",
    )
    scan_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing files",
    )
    scan_p.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Interactive mode for selecting manifests and resolving conflicts",
    )

    why_p = sub.add_parser(
        "why",
        help="Explain why a package version was selected — show dependency chain",
    )
    why_p.add_argument("package", help="Package name to explain")
    why_p.add_argument(
        "--directory", "-d", default=".", help="Project directory with lock file"
    )
    why_p.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )

    outdated_p = sub.add_parser(
        "outdated",
        help="List packages with newer versions available in registries",
    )
    outdated_p.add_argument(
        "--directory", "-d", default=".", help="Project directory with lock file"
    )
    outdated_p.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    outdated_p.add_argument(
        "--ecosystem",
        "-e",
        choices=_eco_choices,
        help="Only check packages from this ecosystem",
    )

    diff_p = sub.add_parser(
        "diff",
        help="Compare two lock files and show version differences",
    )
    diff_p.add_argument("lock_file_a", help="First lock file path")
    diff_p.add_argument("lock_file_b", help="Second lock file path")
    diff_p.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )

    search_p = sub.add_parser(
        "search",
        help="Search for packages across ecosystems",
    )
    search_p.add_argument("query", help="Search query")
    search_p.add_argument(
        "--ecosystems",
        help="Comma-separated ecosystems to search (default: all)",
    )
    search_p.add_argument(
        "--limit", type=int, default=20, help="Max results per ecosystem (default: 20)"
    )
    search_p.add_argument("--json", action="store_true", help="Output as JSON")

    details_p = sub.add_parser(
        "details",
        help="Show detailed package info — versions, dependencies, metadata",
    )
    details_p.add_argument("package", help="Package name")
    details_p.add_argument(
        "--ecosystem", "-e", default="pypi", choices=_eco_choices, help="Ecosystem"
    )
    details_p.add_argument("--json", action="store_true", help="Output as JSON")

    return parser


def main():
    """Main."""
    parser = _build_parser()
    args = parser.parse_args()

    logging.getLogger().setLevel(logging.CRITICAL)
    import warnings

    warnings.filterwarnings("ignore")

    if getattr(args, "mode", None):
        os.environ["UDR_MODE"] = args.mode

    if getattr(args, "offline", None):
        os.environ["UDR_OFFLINE"] = "true"

    dispatch = {
        "serve": cmd_serve,
        "check": cmd_check,
        "resolve": cmd_resolve,
        "lock": cmd_lock,
        "scan": cmd_scan,
        "graph": cmd_graph,
        "verify": cmd_verify,
        "list-ecosystems": cmd_list_ecosystems,
        "update": cmd_update,
        "install": cmd_install,
        "completion": cmd_completion,
        "why": cmd_why,
        "outdated": cmd_outdated,
        "diff": cmd_diff,
        "search": cmd_search,
        "details": cmd_details,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
