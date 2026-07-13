"""UDR project configuration (``udr.json``).

Supports cross-ecosystem dependency declarations and profile
definitions used by the resolver and CLI.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default config file name
CONFIG_FILE = "udr.json"

# Regex for inline manifest annotations:  # udr:ecosystem=pypi or udr:extras=dev
ANNOTATION_RE = re.compile(r"(?:^|\s|#\s*)udr:(?P<key>\w[\w.-]*)=(?P<value>\S+)")


class ProjectConfig:
    """Project-level configuration loaded from ``udr.json``.

    Attributes:
        cross_deps: List of cross-ecosystem dependency declarations.
        profiles: Dict of named dependency profiles.
        workspaces: Dict of workspace definitions (name → config).
    """

    def __init__(self, directory: str | Path = "."):
        self.directory = Path(directory)
        self.cross_deps: list[dict[str, str]] = []
        self.profiles: dict[str, list[str]] = {}
        self.workspaces: dict[str, str] = {}
        self._loaded = False

    def load(self):
        """Load config from ``udr.json`` in the project directory."""
        self._loaded = True
        path = self.directory / CONFIG_FILE
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse %s: %s", path, exc)
            return

        self.cross_deps = data.get("cross_deps", [])
        self.profiles = data.get("profiles", {})
        self.workspaces = data.get("workspaces", {})

    def ensure_loaded(self):
        if not self._loaded:
            self.load()

    @property
    def active_profile(self) -> str | None:
        """Return the currently active profile name (from env or config)."""
        from backend.settings import UDR_PROFILE as _UDR_PROFILE

        return _UDR_PROFILE or None

    def profile_includes(self, eco: str, package: str, profile: str | None = None) -> bool:
        """Check if *package* in *eco* is included in the given profile."""
        self.ensure_loaded()
        p = profile or self.active_profile
        if p is None or p not in self.profiles:
            return True  # No profile restriction → include everything
        includes = self.profiles[p]
        # A package is included if it or its ecosystem matches
        for entry in includes:
            if "/" in entry:
                eco_part, pkg_part = entry.split("/", 1)
                if eco_part == eco and (pkg_part == "*" or pkg_part == package):
                    return True
            elif entry == eco or entry == package:
                return True
        return False


# ---------------------------------------------------------------------------
# Manifest annotation parsing
# ---------------------------------------------------------------------------


def extract_annotations(line: str) -> dict[str, str]:
    """Extract UDR annotations from a manifest line.

    Returns a dict of key → value, e.g. ``{"ecosystem": "pypi"}``.
    """
    results: dict[str, str] = {}
    for m in ANNOTATION_RE.finditer(line):
        results[m.group("key")] = m.group("value")
    return results


def apply_annotation_overrides(
    packages: list[dict[str, Any]],
    manifest_content: str,
) -> list[dict[str, Any]]:
    """Apply inline annotation overrides to parsed package entries.

    For each package, if the original manifest line contains a ``# udr:...``
    annotation, the parsed data is updated accordingly.
    """
    lines = manifest_content.split("\n")
    result: list[dict[str, Any]] = []
    for pkg in packages:
        # Find the line that likely generated this package
        pkg_name = pkg.get("name", "")
        matched_line = None
        for line in lines:
            if pkg_name in line and "#" in line:
                matched_line = line
                break
        if matched_line:
            annotations = extract_annotations(matched_line)
            if "ecosystem" in annotations:
                pkg["_ecosystem"] = annotations["ecosystem"]
            if "extras" in annotations:
                pkg.setdefault("extras", []).append(annotations["extras"])
        result.append(pkg)
    return result
