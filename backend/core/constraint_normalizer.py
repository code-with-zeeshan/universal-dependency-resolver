"""Constraint normalization — delegates to ``vers`` for all ecosystem parsers."""

import re

from .vers import VersSpec


def normalize_version(ver: str, ecosystem: str = "pypi") -> str:
    """Normalize a version string for comparison.

    Strips 'v'/'V' prefixes, '=' prefixes, and converts to PEP 440 format.
    """
    ver = ver.strip().lstrip("=vV ")
    if not ver:
        return "0.0.0"
    parts = ver.split(".")
    normalized = []
    for p in parts:
        clean = re.sub(r"[^0-9]", "", p)
        normalized.append(clean if clean else "0")
    while len(normalized) < 3:
        normalized.append("0")
    return ".".join(normalized[:3])


def parse_semver(ver: str):
    """Parse semver."""
    parts = ver.split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return major, minor, patch


def normalize_constraint(constraint: str, ecosystem: str) -> str | None:
    """Normalize *constraint* for *ecosystem* using the universal vers layer.

    Returns a PEP 508 / PEP 440 string compatible with ``SpecifierSet``,
    or ``"*"`` for any-version, or the raw constraint if no parser matches.
    """
    return str(VersSpec.parse(constraint, ecosystem))
