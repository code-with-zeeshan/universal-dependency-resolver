"""Shared ``Package.swift`` parser for Swift dependency extraction.

Used by both ``swift_client.py`` (registry/GitHub API) and
``manifest_detector.py`` (local filesystem).
"""

import re
from typing import Any


def parse_package_swift(content: str) -> dict[str, Any]:
    """Parse a ``Package.swift`` manifest and return dependency info.

    Returns
    -------
    dict with:
      - ``dependencies``: dict of ``{name: version_constraint}``
      - ``targets``: list of target names (name only)
      - ``platforms``: list of platform strings
      - ``swift_tools_version``: parsed tools version string or ``None``

    """
    result: dict[str, Any] = {
        "dependencies": {},
        "targets": [],
        "platforms": [],
        "swift_tools_version": None,
    }

    # swift-tools-version
    m = re.search(r"//\s*swift-tools-version:\s*([\d.]+)", content)
    if m:
        result["swift_tools_version"] = m.group(1)

    # .package(url: ..., from/exact/branch/revision: "...")
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        m = re.search(r'\.package\(url:\s*["\']([^"\']+)["\']', stripped)
        if not m:
            continue

        url = m.group(1).rstrip("/").removesuffix(".git")
        ver_m = re.search(
            r'(?:from|exact|revision|branch):\s*["\']([^"\']+)["\']'
            r'|\.\w+\(from:\s*["\']([^"\']+)["\']\)',
            stripped,
        )
        constraint = ver_m.group(1) or ver_m.group(2) or "*" if ver_m else "*"
        pkg_name = url.rstrip("/").split("/")[-1] if "/" in url else url
        result["dependencies"][pkg_name] = constraint

    # Target names
    for m in re.finditer(r'\.target\s*\(\s*name:\s*"([^"]+)"', content):
        result["targets"].append(m.group(1))
    for m in re.finditer(r'\.executableTarget\s*\(\s*name:\s*"([^"]+)"', content):
        result["targets"].append(m.group(1))
    for m in re.finditer(r'\.testTarget\s*\(\s*name:\s*"([^"]+)"', content):
        result["targets"].append(m.group(1))

    # Platforms
    for m in re.finditer(
        r'\.(macOS|iOS|watchOS|tvOS|visionOS|linux|windows)\s*\(\s*"([^"]+)"', content
    ):
        result["platforms"].append(f"{m.group(1)} {m.group(2)}")

    return result
