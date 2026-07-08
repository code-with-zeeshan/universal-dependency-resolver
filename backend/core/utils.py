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

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


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
    except Exception as e:
        logger.error(f"Version compatibility check failed for {version_str} against {spec}: {e}")
        return False


@lru_cache(maxsize=4096)
def normalize_package_name(name: str) -> str:
    """Normalize package name (e.g., convert to lowercase, replace underscores)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def extract_requirements(content: str, file_type: str) -> list[dict[str, Any]]:
    """Extract package requirements from various file formats."""
    requirements = []
    if file_type == "requirements.txt":
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                match = re.match(r"^([a-zA-Z0-9][a-zA-Z0-9._-]*)(?:[>=<]=.*)?$", line)
                if match:
                    requirements.append({"name": match.group(1), "version_spec": line})
    elif file_type == "environment.yml":
        try:
            import yaml  # type: ignore[import-untyped]

            data = yaml.safe_load(content)
            for dep in data.get("dependencies", []):
                if isinstance(dep, str):
                    match = re.match(r"^([a-zA-Z0-9][a-zA-Z0-9._-]*)(?:[>=<]=.*)?$", dep)
                    if match:
                        requirements.append({"name": match.group(1), "version_spec": dep})
        except Exception as e:
            logger.error(f"Failed to parse environment.yml: {e}")
    return requirements


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
        "exlixir": "hex",
        # Haskell / Cabal
        "cabal": "haskell",
        "haskell": "haskell",
        "stack": "haskell",
        # Dart / Flutter
        "dart": "pub",
        "flutter": "pub",
        "pub.dev": "pub",
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
