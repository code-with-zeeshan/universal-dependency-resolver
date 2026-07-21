"""Constraint normalization — delegates to ``vers`` for all ecosystem parsers."""

import re

from .vers import VersSpec

_GO_PSEUDO_VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+)-\d+\.\d{14}-[a-f0-9]{12}$")
_DEBIAN_EPOCH_RE = re.compile(r"^(\d+):(.+)$")
_RPM_RELEASE_RE = re.compile(r"^(.*)-(.*)$")


def normalize_version(ver: str, ecosystem: str = "pypi") -> str:
    """Normalize a version string for comparison.

    Strips 'v'/'V' prefixes, '=' prefixes, and converts to PEP 440 format.
    Handles Go pseudo-versions by extracting the base semantic version.
    Handles Debian epoch (``epoch:upstream-{revision}``) and Conda globs.
    """
    ver = ver.strip()
    if not ver:
        return "0.0.0"

    # Debian epoch: "1:2.3.4-5" → upstream is "2.3.4", epoch is stored as prefix
    epoch_match = _DEBIAN_EPOCH_RE.match(ver)
    if epoch_match and ecosystem in ("apt", "apk", "debian"):
        epoch = epoch_match.group(1)
        upstream = epoch_match.group(2)
        # Strip Debian revision
        upstream = upstream.split("-")[0]
        return f"{epoch}:{_normalize_upstream(upstream)}"

    # Strip Debian/APK revision for apt/apk ecosystems
    if ecosystem in ("apt", "apk", "debian") and "-" in ver:
        ver = ver.split("-")[0]

    # RPM EVR: "1:2.3.4-5.el8" → "2.3.4"
    if ecosystem == "rpm":
        if ":" in ver:
            ver = ver.split(":", 1)[-1]
        ver = ver.split("-")[0]
        return _normalize_upstream(ver)

    ver = ver.lstrip("=vV ")
    # Go pseudo-version: vX.Y.Z-0.yyyymmddhhmmss-abcdefabcdef
    m = _GO_PSEUDO_VERSION_RE.match(ver)
    if m:
        return m.group(1)
    return _normalize_upstream(ver)


def _normalize_upstream(ver: str) -> str:
    """Normalize an upstream version string (no epoch) to semver-like format."""
    # Conda glob: "1.2.*" or "1.2*"
    if ver.endswith((".*", "*")):
        base = ver.rstrip(".*")
        return _normalize_upstream(base)
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
