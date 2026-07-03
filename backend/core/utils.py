"""Module docstring."""

# utils.py
import asyncio
import logging
import re
from collections.abc import Coroutine
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
    """Run a coroutine synchronously.
    Uses asyncio.run() when no event loop is running;
    falls back to creating a new loop if called from a running loop.
    """
    try:
        asyncio.get_running_loop()
        # We're inside a running loop — create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except RuntimeError:
        # No running loop — use asyncio.run (cleanest)
        return asyncio.run(coro)


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
    import json

    system_str = json.dumps(system_info, sort_keys=True)
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
        "swift": "cocoapods",
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
    """Download a GitHub repo as zipball and extract to temp dir."""
    import io
    import re
    import tempfile
    import urllib.request
    import zipfile

    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if not match:
        raise ValueError(f"Invalid GitHub URL: {url}")
    owner, repo = match.group(1), match.group(2).rstrip(".git")
    api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
    req = urllib.request.Request(api_url, headers={"User-Agent": "UDR/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status != 200:
            raise RuntimeError(f"GitHub API returned {resp.status}")
        data = resp.read()
    tmp = Path(tempfile.mkdtemp(prefix="udr_scan_"))
    z = zipfile.ZipFile(io.BytesIO(data))
    z.extractall(path=str(tmp))
    contents = list(tmp.iterdir())
    if contents and contents[0].is_dir():
        return contents[0]
    return tmp


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
