"""Module docstring."""

# utils.py
import asyncio
import logging
import re
from collections.abc import Coroutine
from functools import lru_cache
from pathlib import Path
from typing import Any

from packaging import version
from packaging.version import Version

logger = logging.getLogger(__name__)


CLI_COMMANDS = (
    "auth",
    "check",
    "completion",
    "details",
    "diff",
    "graph",
    "index",
    "install",
    "list-ecosystems",
    "lock",
    "outdated",
    "resolve",
    "sbom",
    "scan",
    "search",
    "serve",
    "tools",
    "update",
    "verify",
    "why",
)

# ---------------------------------------------------------------------------
# Package URL (purl) — purl-spec 1.0
# ---------------------------------------------------------------------------

ECOSYSTEM_PURL_TYPE: dict[str, str] = {
    "pypi": "pypi",
    "npm": "npm",
    "crates": "cargo",
    "gomodules": "golang",
    "maven": "maven",
    "nuget": "nuget",
    "rubygems": "gem",
    "packagist": "composer",
    "cocoapods": "cocoapods",
    "pub": "pub",
    "homebrew": "brew",
    "conda": "conda",
    "hex": "hex",
    "haskell": "hackage",
    "apt": "deb",
    "apk": "alpine",
    "gradle": "maven",
    "swift": "swift",
    "nix": "nix",
    "guix": "guix",
    "docker": "docker",
    "vcpkg": "vcpkg",
    "conan": "conan",
    "helm": "helm",
    "terraform": "terraform",
}


def make_purl(name: str, version: str, ecosystem: str) -> str:
    """Build a Package URL (purl) string from name, version, and ecosystem."""
    ptype = ECOSYSTEM_PURL_TYPE.get(ecosystem, ecosystem)
    purl = f"pkg:{ptype}/{_purl_encode(name)}"
    if version:
        purl += f"@{_purl_encode(version)}"
    return purl


def _purl_encode(value: str) -> str:
    return value.replace("%", "%25").replace("@", "%40").replace("/", "%2F")


def run_async(coro: Coroutine) -> Any:
    """Run a coroutine synchronously from a non-async context.

    Use ``await run_async_await(coro)`` from async contexts instead.

    Raises ``RuntimeError`` if called from within a running event loop.
    """
    return asyncio.run(coro)


async def run_async_await(coro: Coroutine) -> Any:
    """Run a coroutine from an async context (just awaits it).

    For use in API handlers and other async code that calls
    methods originally designed for sync contexts.
    """
    return await coro


def parse_version(version_str: str) -> version.Version | None:
    """Parse a version string into a packaging.version.Version object."""
    try:
        return version.parse(version_str)
    except Exception as e:
        logger.warning(f"Failed to parse version {version_str}: {e}")
        return None


def parse_version_key(version_str: str) -> Version:
    """Parse a version string for use as a sort key.
    Returns ``Version("0.0.0")`` for unparseable versions (never None).
    """
    parsed = parse_version(version_str)
    return parsed if parsed is not None else Version("0.0.0")


def is_compatible_version(version_str: str, spec: str) -> bool:
    """Check if a version satisfies a version specification."""
    try:
        from packaging.specifiers import SpecifierSet

        return version.parse(version_str) in SpecifierSet(spec)
    except Exception:
        logger.warning(
            "Version compatibility check failed for %s against %s", version_str, spec, exc_info=True
        )
        return False


@lru_cache(maxsize=4096)
def normalize_package_name(name: str) -> str:
    """Normalize package name (e.g., convert to lowercase, replace underscores)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def hash_system_info(system_info: dict[str, Any]) -> str:
    """Generate a hash of system info for caching."""
    import hashlib

    from ._json import dumps

    system_str = dumps(system_info, sort_keys=True)
    return hashlib.sha256(system_str.encode()).hexdigest()


def sanitize_ecosystem_name(ecosystem: str) -> str:
    """Sanitize and standardize ecosystem names."""
    ecosystem_aliases = {
        # Python
        "pip": "pypi",
        "python": "pypi",
        "py": "pypi",
        # JavaScript/Node
        "node": "npm",
        "nodejs": "npm",
        "js": "npm",
        # Rust
        "cargo": "crates",
        "rust": "crates",
        "crates.io": "crates",
        # Java
        "java": "maven",
        "mvn": "maven",
        # Conda
        "anaconda": "conda",
        "miniconda": "conda",
        # Go
        "go": "gomodules",
        "golang": "gomodules",
        "gomod": "gomodules",
        # System Package Managers
        "debian": "apt",
        "ubuntu": "apt",
        "deb": "apt",
        "alpine": "apk",
        # iOS/macOS
        "pods": "cocoapods",
        "cocoa": "cocoapods",
        "ios": "cocoapods",
        # Ruby
        "ruby": "rubygems",
        "gem": "rubygems",
        "gems": "rubygems",
        # PHP
        "php": "packagist",
        "composer": "packagist",
        # .NET
        "dotnet": "nuget",
        ".net": "nuget",
        "csharp": "nuget",
        "c#": "nuget",
        # macOS
        "brew": "homebrew",
        "osx": "homebrew",
        "macos": "homebrew",
        # Gradle
        "gradle": "gradle",
        "groovy": "gradle",
        "kotlin": "gradle",
        # Swift
        "swift": "swift",
        "spm": "swift",
        # Hex / Elixir
        "elixir": "hex",
        # Haskell / Cabal
        "cabal": "haskell",
        "haskell": "haskell",
        "stack": "haskell",
        # Dart / Flutter
        "dart": "pub",
        "flutter": "pub",
        "pub.dev": "pub",
        # Nix
        "nixos": "nix",
        "nixpkgs": "nix",
        # Guix
        "guix": "guix",
        "guixsd": "guix",
        # Docker
        "docker": "docker",
        "container": "docker",
        # Terraform
        "terraform": "terraform",
        "tf": "terraform",
        # Helm
        "helm": "helm",
        "chart": "helm",
        # Vcpkg
        "vcpkg": "vcpkg",
        "cpp": "vcpkg",
        "c++": "vcpkg",
        # Conan
        "conan": "conan",
        "conan.io": "conan",
        # Haskell (hackage alias)
        "hackage": "haskell",
    }
    ecosystem_lower = ecosystem.lower().strip()
    return ecosystem_aliases.get(ecosystem_lower, ecosystem_lower)


def download_github_repo(url: str, branch: str) -> Path:
    """Download a GitHub repo as zipball and extract to temp dir.

    Deprecated: use backend.orchestrator.scanner._download_github_repo (async) instead.
    """
    import asyncio

    from backend.orchestrator.scanner import _download_github_repo as _async_download

    return asyncio.run(_async_download(url, branch))


def compare_versions(v1: str, v2: str) -> int:
    """Compare two version strings. Returns -1 if v1 < v2, 0 if equal, 1 if v1 > v2.

    Note: Python 3 users should prefer ``key=lambda v: packaging.version.Version(v)`` in ``sorted()``.
    """
    try:
        ver1 = version.parse(v1)
        ver2 = version.parse(v2)
        if ver1 < ver2:
            return -1
        if ver1 > ver2:
            return 1
        return 0
    except Exception as e:
        logger.error(f"Failed to compare versions {v1} and {v2}: {e}")
        return 0
