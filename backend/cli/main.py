"""CLI entry point for Universal Dependency Resolver."""

import argparse
import logging
import os

from backend.core.shutdown import ShutdownFlag, register_signal_handlers
from backend.settings import ECOSYSTEMS
from backend.settings import reload as reload_settings

# Global shutdown flag for CLI commands
SHUTDOWN_FLAG = ShutdownFlag()

from .commands.auth import cmd_auth
from .commands.check import cmd_check
from .commands.completion import cmd_completion
from .commands.details import cmd_details
from .commands.diff import cmd_diff
from .commands.export import cmd_export
from .commands.graph import cmd_graph
from .commands.index import cmd_index
from .commands.init import add_init_parser, cmd_init
from .commands.install import cmd_install
from .commands.list_ecosystems import cmd_list_ecosystems
from .commands.lock import cmd_lock
from .commands.migrate import add_migrate_parser, cmd_migrate
from .commands.outdated import cmd_outdated
from .commands.resolve import cmd_resolve
from .commands.sbom import cmd_sbom
from .commands.scan import cmd_scan
from .commands.search import cmd_search
from .commands.serve import cmd_serve
from .commands.system_info import cmd_system_info
from .commands.tools import cmd_tools
from .commands.update import cmd_update
from .commands.verify import cmd_verify
from .commands.why import cmd_why
from .shared import VERSION


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

    serve_p = sub.add_parser(
        "serve",
        help="Start the API server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr serve                 # start API server on default port
  udr serve --port 9000     # custom port
  udr serve --reload        # auto-reload on code changes
""",
    )
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind address")
    serve_p.add_argument("--port", type=int, default=8000, help="Bind port")
    serve_p.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
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
    check_p.add_argument("-v", "--verbose", action="store_true", help="Show detailed info")
    check_p.add_argument("--deps", action="store_true", help="Show project core dependencies")
    check_p.add_argument("--json", action="store_true", help="Output as JSON")
    check_p.add_argument(
        "--cuda",
        help="Target CUDA version (e.g. 12.1) — simulate system check for a specific CUDA config",
    )
    check_p.add_argument("--cve", action="store_true", help="Check lock file for known CVEs")
    check_p.add_argument(
        "--license", action="store_true", help="Check lock file for license compliance"
    )
    check_p.add_argument(
        "--deprecated",
        action="store_true",
        help="Check lock file for deprecated or yanked packages",
    )
    check_p.add_argument(
        "--peer",
        action="store_true",
        help="Check lock file for peer dependency issues",
    )
    check_p.add_argument(
        "--device",
        choices=["cpu", "cuda", "mps", "rocm"],
        help="Simulate system check for a specific compute device",
    )
    check_p.add_argument("--directory", "-d", default=".", help="Project directory with lock file")
    check_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace name — lock file becomes udr-{workspace}.lock",
    )
    check_p.add_argument(
        "--lock-file",
        "-l",
        help="Explicit lock file path (overrides directory/workspace)",
    )
    check_p.add_argument(
        "--policy",
        "-p",
        nargs="?",
        const="udr-policy.yaml",
        default=None,
        help="Path to policy YAML file (default: ./udr-policy.yaml)",
    )

    resolve_p = sub.add_parser(
        "resolve",
        help="Resolve dependencies for one or more packages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr resolve flask express@npm
  udr resolve numpy --cuda 12.1 --json
""",
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
        "--json", action="store_true", help="Output as JSON (shorthand for --format json)"
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
        choices=["cpu", "cuda", "mps", "rocm"],
        default=None,
        help="Target compute device: cpu, cuda (NVIDIA GPU), mps (Apple Silicon), or rocm (AMD GPU)",
    )
    resolve_p.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Resolution timeout in seconds (default: 120, from SOLVER_TIMEOUT env var)",
    )
    resolve_p.add_argument(
        "--extras",
        type=lambda s: [x.strip() for x in s.split(",")],
        default=None,
        help="Comma-separated extras groups to activate (e.g. 'dotenv,speedups')",
    )
    resolve_p.add_argument(
        "--pin",
        action="append",
        default=None,
        help="Pin a package to an exact version (e.g. 'numpy==1.24'). Repeatable.",
    )
    resolve_p.add_argument(
        "--pin-mode",
        choices=["none", "patch", "minor", "exact"],
        default="none",
        help="Global pinning strategy (default: none)",
    )
    resolve_p.add_argument(
        "--block",
        action="append",
        default=None,
        help="Block a package from resolution (e.g. 'tensorflow'). Repeatable.",
    )
    resolve_p.add_argument(
        "--freeze",
        action="store_true",
        default=False,
        help="Freeze all packages at their lock-file versions",
    )
    resolve_p.add_argument(
        "--target",
        choices=["linux", "windows", "darwin"],
        default=None,
        help="Target OS for cross-compilation (overrides host OS)",
    )
    resolve_p.add_argument(
        "--platform",
        choices=["x86_64", "aarch64", "arm64", "i386", "amd64"],
        default=None,
        help="Target CPU architecture for cross-compilation (overrides host arch)",
    )
    resolve_p.add_argument(
        "--auto-sync",
        action="store_true",
        help="Auto-sync stale local indexes before resolution",
    )
    resolve_p.add_argument(
        "--with-dev",
        action="store_true",
        default=None,
        help="Include dev/optional dependency manifests in resolution",
    )
    resolve_p.add_argument(
        "--without-optional",
        action="store_true",
        default=None,
        help="Exclude optional dependencies from resolution",
    )

    lock_p = sub.add_parser(
        "lock",
        help="Auto-detect manifests, resolve all dependencies, write lock file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr lock                          # auto-detect, resolve, write udr.lock
  udr lock --dry-run --json         # preview without writing
  udr lock --cuda 12.1 --device cuda  # CUDA-aware resolution
  udr lock --check                  # CI mode: exit 1 if drift
""",
    )
    lock_p.add_argument("--directory", "-d", default=".", help="Project directory to scan")
    lock_p.add_argument("--manifest", "-m", help="Only process a specific manifest file")
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
        choices=["cpu", "cuda", "mps", "rocm"],
        default=None,
        help="Target compute device: cpu, cuda (NVIDIA GPU), mps (Apple Silicon), or rocm (AMD GPU)",
    )
    lock_p.add_argument("--json", action="store_true", help="Output lock data as JSON")
    lock_p.add_argument(
        "--report",
        "-r",
        action="store_true",
        help="Write readable report file (udr.report.txt) alongside lock file",
    )
    lock_p.add_argument(
        "--include-dev",
        action="store_true",
        help="Include manifests from examples, test, docs, and other excluded directories",
    )
    lock_p.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Resolution timeout in seconds (default: 120, from SOLVER_TIMEOUT env var)",
    )
    lock_p.add_argument(
        "--extras",
        type=lambda s: [x.strip() for x in s.split(",")],
        default=None,
        help="Comma-separated extras groups to activate (e.g. 'dotenv,speedups')",
    )
    lock_p.add_argument(
        "--pin",
        action="append",
        default=None,
        help="Pin a package to an exact version (e.g. 'numpy==1.24'). Repeatable.",
    )
    lock_p.add_argument(
        "--pin-mode",
        choices=["none", "patch", "minor", "exact"],
        default="none",
        help="Global pinning strategy (default: none)",
    )
    lock_p.add_argument(
        "--block",
        action="append",
        default=None,
        help="Block a package from resolution (e.g. 'tensorflow'). Repeatable.",
    )
    lock_p.add_argument(
        "--freeze",
        action="store_true",
        default=False,
        help="Freeze all packages at their lock-file versions",
    )
    lock_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace name for monorepo support — lock file becomes udr-{workspace}.lock",
    )
    lock_p.add_argument(
        "--prefix",
        default=None,
        help="Prefix package names in lock file with string (e.g. 'backend/' for monorepo scoping)",
    )
    lock_p.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force full re-resolution, ignoring existing lock file cache",
    )
    lock_p.add_argument(
        "--target",
        choices=["linux", "windows", "darwin"],
        default=None,
        help="Target OS for cross-compilation (overrides host OS)",
    )
    lock_p.add_argument(
        "--platform",
        choices=["x86_64", "aarch64", "arm64", "i386", "amd64"],
        default=None,
        help="Target CPU architecture for cross-compilation (overrides host arch)",
    )
    lock_p.add_argument(
        "--auto-sync",
        action="store_true",
        help="Auto-sync stale local indexes before resolution",
    )
    lock_p.add_argument("--sign", action="store_true", help="Sign the lock file with Ed25519 key")
    lock_p.add_argument(
        "--provenance", action="store_true", help="Add SLSA provenance section to lock file"
    )
    lock_p.add_argument(
        "--check",
        "-c",
        action="store_true",
        help="Check if lock file is up to date (CI mode). Exit code 1 if drift detected.",
    )
    lock_p.add_argument(
        "--with-dev",
        action="store_true",
        default=None,
        help="Include dev/optional dependency manifests in resolution",
    )
    lock_p.add_argument(
        "--without-optional",
        action="store_true",
        default=None,
        help="Exclude optional dependencies from resolution",
    )

    graph_p = sub.add_parser(
        "graph",
        help="Show dependency tree for one or more packages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr graph              # dependency graph for all packages
  udr graph --json       # JSON output
  udr graph --ecosystem pypi
""",
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
        choices=["cpu", "cuda", "mps", "rocm"],
        default=None,
        help="Target compute device: cpu, cuda (NVIDIA GPU), mps (Apple Silicon), or rocm (AMD GPU)",
    )

    verify_p = sub.add_parser(
        "verify",
        help="Validate lock file — check all versions still exist",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr verify              # validate udr.lock
  udr verify --json       # JSON output
  udr verify --signature  # verify Ed25519 signature
""",
    )
    verify_p.add_argument(
        "lock_file",
        nargs="?",
        default=None,
        help="Path to lock file (default: auto-detected from directory/workspace)",
    )
    verify_p.add_argument("--json", action="store_true", help="Output as JSON")
    verify_p.add_argument("--directory", "-d", default=".", help="Project directory with lock file")
    verify_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace name — lock file becomes udr-{workspace}.lock",
    )
    verify_p.add_argument(
        "--signature",
        "--sig",
        action="store_true",
        dest="signature",
        help="Verify Ed25519 signature on the lock file",
    )

    list_eco_p = sub.add_parser(
        "list-ecosystems",
        help="List all supported ecosystems",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr list-ecosystems --json
""",
    )
    list_eco_p.add_argument("--json", action="store_true", help="Output as JSON")

    update_p = sub.add_parser(
        "update",
        help="Re-resolve a package and update lock file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr update requests      # update a single package
  udr update --fix-cve     # fix all vulnerable packages
  udr update --dry-run     # preview changes
""",
    )
    update_p.add_argument(
        "package",
        nargs="?",
        default=None,
        help="Package name to re-resolve (optional with --fix-cve)",
    )
    update_p.add_argument("--directory", "-d", default=".", help="Project directory with lock file")
    update_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace name — lock file becomes udr-{workspace}.lock",
    )
    update_p.add_argument(
        "--lock-file",
        "-l",
        help="Explicit lock file path (overrides directory/workspace)",
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
        choices=["cpu", "cuda", "mps", "rocm"],
        default=None,
        help="Target compute device: cpu, cuda (NVIDIA GPU), mps (Apple Silicon), or rocm (AMD GPU)",
    )
    update_p.add_argument(
        "--target",
        choices=["linux", "windows", "darwin"],
        default=None,
        help="Target OS for cross-compilation (overrides host OS)",
    )
    update_p.add_argument(
        "--platform",
        choices=["x86_64", "aarch64", "arm64", "i386", "amd64"],
        default=None,
        help="Target CPU architecture for cross-compilation (overrides host arch)",
    )
    update_p.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Resolution timeout in seconds (default: 120, from SOLVER_TIMEOUT env var)",
    )
    update_p.add_argument(
        "--fix-cve",
        action="store_true",
        help="Update vulnerable packages to versions that fix known CVEs",
    )
    update_p.add_argument(
        "--with-dev",
        action="store_true",
        default=None,
        help="Include dev/optional dependency manifests in resolution",
    )
    update_p.add_argument(
        "--without-optional",
        action="store_true",
        default=None,
        help="Exclude optional dependencies from resolution",
    )

    install_p = sub.add_parser(
        "install",
        help="Install packages from udr.lock lock file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr install              # install all packages from udr.lock
  udr install --dry-run    # preview without installing
""",
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
        "--workspace",
        default=None,
        help="Workspace name — lock file becomes udr-{workspace}.lock",
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
    install_p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    install_p.add_argument(
        "--restore",
        action="store_true",
        help="Restore mode — alias for install (kept for compatibility)",
    )
    install_p.add_argument(
        "--production",
        action="store_true",
        help="Skip dev dependencies",
    )
    install_p.add_argument(
        "--cuda",
        "-c",
        help="CUDA version to target (e.g. 121 for cu121 wheels)",
    )
    install_p.add_argument(
        "--target",
        choices=["linux", "windows", "darwin"],
        default=None,
        help="Target OS for cross-compilation (overrides host OS)",
    )
    install_p.add_argument(
        "--platform",
        choices=["x86_64", "aarch64", "arm64", "i386", "amd64"],
        default=None,
        help="Target CPU architecture for cross-compilation (overrides host arch)",
    )

    completion_p = sub.add_parser(
        "completion",
        help="Generate shell completion script for bash, zsh, or fish",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr completion           # detect shell, print script
  udr completion bash      # bash completions
""",
    )
    completion_p.add_argument(
        "shell",
        nargs="?",
        choices=["bash", "zsh", "fish"],
        help="Shell to generate completions for (auto-detected if omitted)",
    )

    scan_p = sub.add_parser(
        "scan",
        help="Scan a GitHub repo or local path without manual clone/cd",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr scan --github https://github.com/user/repo
  udr scan --directory .
""",
    )
    scan_p.add_argument(
        "--github", help="GitHub repository URL (e.g. https://github.com/user/repo)"
    )
    scan_p.add_argument("--branch", default="main", help="Git branch to scan (default: main)")
    scan_p.add_argument("--directory", help="Local project directory to scan")
    scan_p.add_argument("--manifest", "-m", help="Only process a specific manifest file")
    scan_p.add_argument(
        "-y", "--yes", action="store_true", help="Update manifests without prompting"
    )
    scan_p.add_argument("--export", help="Export to a specific format")
    scan_p.add_argument("--json", action="store_true", help="Output lock data as JSON")
    scan_p.add_argument("--cuda", help="Target CUDA version (e.g. 12.1)")
    scan_p.add_argument(
        "--device",
        choices=["cpu", "cuda", "mps", "rocm"],
        default=None,
        help="Target compute device: cpu, cuda (NVIDIA GPU), mps (Apple Silicon), or rocm (AMD GPU)",
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr why flask           # why is flask a dependency
  udr why --all flask     # all transitive paths
  udr why --json
""",
    )
    why_p.add_argument("package", nargs="?", help="Package name to explain")
    why_p.add_argument("--all", "-a", action="store_true", help="Show info for all packages")
    why_p.add_argument("--directory", "-d", default=".", help="Project directory with lock file")
    why_p.add_argument("--json", action="store_true", help="Output as JSON")
    why_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace name — lock file becomes udr-{workspace}.lock",
    )
    why_p.add_argument(
        "--lock-file",
        "-l",
        help="Explicit lock file path (overrides directory/workspace)",
    )

    outdated_p = sub.add_parser(
        "outdated",
        help="List packages with newer versions available in registries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr outdated            # all outdated packages
  udr outdated --json
""",
    )
    outdated_p.add_argument(
        "--directory", "-d", default=".", help="Project directory with lock file"
    )
    outdated_p.add_argument("--json", action="store_true", help="Output as JSON")
    outdated_p.add_argument(
        "--ecosystem",
        "-e",
        choices=_eco_choices,
        help="Only check packages from this ecosystem",
    )
    outdated_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace name — lock file becomes udr-{workspace}.lock",
    )
    outdated_p.add_argument(
        "--lock-file",
        "-l",
        help="Explicit lock file path (overrides directory/workspace)",
    )

    diff_p = sub.add_parser(
        "diff",
        help="Compare two lock files and show version differences",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr diff                # diff vs previous lock
  udr diff --json         # JSON diff
""",
    )
    diff_p.add_argument("lock_file_a", nargs="?", default=None, help="First lock file path")
    diff_p.add_argument("lock_file_b", nargs="?", default=None, help="Second lock file path")
    diff_p.add_argument("--json", action="store_true", help="Output as JSON")
    diff_p.add_argument("--directory", "-d", default=".", help="Project directory with lock files")
    diff_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace name — compares current vs. udr-{workspace}.lock",
    )

    search_p = sub.add_parser(
        "search",
        help="Search for packages across ecosystems",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr search flask        # search all ecosystems
  udr search --ecosystem pypi flask
""",
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

    sbom_p = sub.add_parser(
        "sbom",
        help="Generate SPDX 2.3 or CycloneDX 1.5 SBOM from lock file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr sbom                # SPDX 2.3 JSON
  udr sbom --format cyclonedx  # CycloneDX 1.5
""",
    )
    sbom_p.add_argument("--directory", "-d", default=".", help="Project directory with lock file")
    sbom_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace name — lock file becomes udr-{workspace}.lock",
    )
    sbom_p.add_argument(
        "--lock-file",
        "-l",
        help="Explicit lock file path (overrides directory/workspace)",
    )
    sbom_p.add_argument(
        "--format", "-f", default="spdx", choices=["spdx", "cyclonedx"], help="SBOM format"
    )
    sbom_p.add_argument(
        "--output", "-o", default=None, help="Output file path (default: print to stdout)"
    )

    export_p = sub.add_parser(
        "export",
        help="Export lock file to a specific format (requirements.txt, Dockerfile, etc.)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr export --format requirements.txt
  udr export --format pip-compile
""",
    )
    export_p.add_argument("--directory", "-d", default=".", help="Project directory with lock file")
    export_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace name — lock file becomes udr-{workspace}.lock",
    )
    export_p.add_argument(
        "--lock-file",
        "-l",
        help="Explicit lock file path (overrides directory/workspace)",
    )
    export_p.add_argument(
        "--format",
        "-f",
        default="requirements.txt",
        help="Export format (e.g. requirements.txt, Dockerfile)",
    )
    export_p.add_argument(
        "--output", "-o", default=None, help="Output file path (default: print to stdout)"
    )

    details_p = sub.add_parser(
        "details",
        help="Show detailed package info — versions, dependencies, metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr details numpy
  udr details express --ecosystem npm --json
""",
    )
    details_p.add_argument("package", help="Package name")
    details_p.add_argument(
        "--ecosystem", "-e", default="pypi", choices=_eco_choices, help="Ecosystem"
    )
    details_p.add_argument("--json", action="store_true", help="Output as JSON")

    sysinfo_p = sub.add_parser(
        "system-info",
        help="Show detailed system information — OS, CPU, GPU, Python, runtimes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr system-info --json
""",
    )
    sysinfo_p.add_argument("--json", action="store_true", help="Output as JSON")

    auth_p = sub.add_parser(
        "auth",
        help="Manage API keys for the API server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr auth create --name my-key    # create API key
  udr auth list                    # list keys
  udr auth revoke 1                # revoke key
""",
    )
    auth_sub = auth_p.add_subparsers(dest="auth_action", required=True)

    auth_create = auth_sub.add_parser("create", help="Create a new API key")
    auth_create.add_argument("--name", help="Human-readable name for this key")
    auth_create.add_argument(
        "--role",
        choices=["read-only", "read-write", "admin"],
        default="read-only",
        help="Access role for the key (default: read-only)",
    )
    auth_create.add_argument("--description", help="Optional description")

    auth_revoke = auth_sub.add_parser("revoke", help="Revoke an API key")
    auth_revoke.add_argument("key_id", type=int, help="ID of the key to revoke")

    auth_sub.add_parser("list", help="List all API keys")

    auth_sub.add_parser("gen-key", help="Generate a new Ed25519 signing key for lock file signing")
    auth_sub.add_parser("show-key", help="Show the current Ed25519 public signing key")

    add_init_parser(sub)
    add_migrate_parser(sub)

    index_p = sub.add_parser(
        "index",
        help="Manage offline SQLite indexes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr index pull <url>          # download pre-built indexes
  udr index build                # build from udr.lock
  udr index build --ecosystem pypi
""",
    )
    index_sub = index_p.add_subparsers(dest="index_action", required=True)

    index_pull_p = index_sub.add_parser("pull", help="Download pre-built indexes")
    index_pull_p.add_argument("url", help="Base URL for index download")
    index_pull_p.add_argument("--ecosystem", "-e", help="Only pull index for this ecosystem")

    index_build_p = index_sub.add_parser(
        "build", help="Build index from resolved packages in udr.lock"
    )
    index_build_p.add_argument(
        "--packages",
        default="",
        help="Comma-separated package names to index (builds for --ecosystem)",
    )
    index_build_p.add_argument(
        "--ecosystem", "-e", default="pypi", choices=_eco_choices, help="Ecosystem for --packages"
    )
    index_build_p.add_argument(
        "--directory", "-d", help="Directory containing udr.lock (default: cwd)"
    )

    index_status_p = index_sub.add_parser("status", help="Show local offline index status")
    index_status_p.add_argument("--json", action="store_true", help="Output as JSON")

    index_sync_p = index_sub.add_parser("sync", help="Sync local indexes from remote registries")
    index_sync_p.add_argument("--ecosystem", "-e", choices=_eco_choices, help="Ecosystem to sync")
    index_sync_p.add_argument(
        "--all", "-a", action="store_true", help="Sync all supported ecosystems"
    )

    tools_p = sub.add_parser(
        "tools",
        help="Manage plugins and extensions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr tools register-plugin --path ./my-plugin
  udr tools register-plugin --name my-plugin
""",
    )
    tools_sub = tools_p.add_subparsers(dest="tools_command", required=True)

    reg_parser = tools_sub.add_parser(
        "register-plugin", help="Scan a directory for third-party plugins and register them"
    )
    reg_parser.add_argument(
        "--path",
        required=True,
        help="Directory path containing plugin Python files",
    )
    reg_parser.add_argument(
        "--name",
        default=None,
        help="Optional name tag for the plugin group",
    )

    return parser


def main():
    """Run the CLI entry point."""
    register_signal_handlers(SHUTDOWN_FLAG)
    parser = _build_parser()
    args = parser.parse_args()

    logging.getLogger().setLevel(logging.CRITICAL)
    import warnings

    warnings.filterwarnings("ignore")

    if getattr(args, "mode", None):
        os.environ["UDR_MODE"] = args.mode

    if getattr(args, "offline", None):
        os.environ["UDR_OFFLINE"] = "true"

    reload_settings()

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
        "init": cmd_init,
        "migrate": cmd_migrate,
        "completion": cmd_completion,
        "why": cmd_why,
        "outdated": cmd_outdated,
        "diff": cmd_diff,
        "search": cmd_search,
        "sbom": cmd_sbom,
        "export": cmd_export,
        "details": cmd_details,
        "system-info": cmd_system_info,
        "auth": cmd_auth,
        "index": cmd_index,
        "tools": cmd_tools,
    }
    try:
        dispatch[args.command](args)
    except Exception as exc:
        from backend.core.error_sanitizer import sanitize_for_user

        user_msg = sanitize_for_user(str(exc))
        is_json = getattr(args, "json", False) or getattr(args, "format", "") == "json"
        if is_json:
            import json as _json

            _json.dump({"error": user_msg, "type": type(exc).__name__}, sys.stdout)
            sys.stdout.write("\n")
        else:
            logger.error("Command failed: %s", exc, exc_info=True)
            print(f"Error: {user_msg}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
