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


# Pre-release weight map: lower weight = earlier in release cycle
_PRERELEASE_WEIGHTS: dict[str, int] = {
    "dev": 0,
    "a": 1,
    "alpha": 1,
    "b": 2,
    "beta": 2,
    "rc": 3,
    "pre": 3,
    "preview": 3,
}

_PRERELEASE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?:^|[-.])(dev|preview)(?:$|[-.]?\d*)", re.I), "dev"),
    (re.compile(r"(?:^|[-.])(alpha)(?:$|[-.]?\d*)", re.I), "a"),
    (re.compile(r"(?:^|[-.])(beta)(?:$|[-.]?\d*)", re.I), "b"),
    (re.compile(r"(?:^|[-.])(rc|pre)(?:$|[-.]?\d*)", re.I), "rc"),
    (re.compile(r"(?:^|[-.])a(?:\d*)$", re.I), "a"),  # standalone a1, a2 etc (PEP 440)
    (re.compile(r"(?:^|[-.])b(?:\d*)$", re.I), "b"),  # standalone b1, b2
]


def normalize_prerelease_weight(ver: str) -> int:
    """Return numeric pre-release weight (0=dev, 1=alpha, 2=beta, 3=rc, 100=release).

    Handles PEP 440 (``1.0.0.dev1``, ``1.0.0a1``, ``1.0.0rc2``) and
    semver (``1.0.0-dev.1``, ``1.0.0-alpha.1``, ``1.0.0-rc.2``) formats.
    Used for cross-ecosystem pre-release ordering decisions.
    """
    ver = ver.strip().lower()
    if ":" in ver:
        ver = ver.split(":", 1)[-1]
    ver = ver.lstrip("=vV ")
    # Try PEP 440 parser first
    try:
        from packaging.version import Version

        pv = Version(ver)
        if pv.dev is not None:
            return 0
        if pv.pre is not None:
            pre_key, _ = pv.pre
            return _PRERELEASE_WEIGHTS.get(pre_key, 1)
        if pv.is_prerelease:
            return 1  # unknown pre-release type
        return 100
    except Exception:
        pass
    # Fallback: regex matching for non-PEP 440 (npm, etc.)
    for sep in ("-", "."):
        parts = ver.split(sep, 1)
        if len(parts) < 2:
            continue
        for pattern, key in _PRERELEASE_PATTERNS:
            if pattern.search(parts[1]):
                return _PRERELEASE_WEIGHTS.get(key, 100)
    return 100


def compare_versions_with_prerelease(v1: str, v2: str) -> int:
    """Compare two versions, accounting for pre-release weight.

    Returns -1 if v1 < v2, 0 if equal, 1 if v1 > v2.
    """
    w1 = normalize_prerelease_weight(v1)
    w2 = normalize_prerelease_weight(v2)
    if w1 != w2:
        return -1 if w1 < w2 else 1
    # Same pre-release phase — compare lexicographically
    from packaging.version import Version

    try:
        pv1 = Version(v1)
        pv2 = Version(v2)
        if pv1 < pv2:
            return -1
        if pv1 > pv2:
            return 1
        return 0
    except Exception:
        if v1 < v2:
            return -1
        if v1 > v2:
            return 1
        return 0


def normalize_constraint(constraint: str, ecosystem: str) -> str | None:
    """Normalize *constraint* for *ecosystem* using the universal vers layer.

    Returns a PEP 508 / PEP 440 string compatible with ``SpecifierSet``,
    or ``"*"`` for any-version, or the raw constraint if no parser matches.
    """
    normalized = str(VersSpec.parse(constraint, ecosystem))
    if normalized == constraint:
        plugin_result = _try_plugin_constraint(constraint, ecosystem)
        if plugin_result is not None:
            return plugin_result
    return normalized


def _try_plugin_constraint(constraint: str, ecosystem: str) -> str | None:
    """Try registered plugin constraint handlers as a fallback."""
    try:
        from .plugin import handle_plugin_constraint

        return handle_plugin_constraint(constraint, ecosystem)
    except Exception:
        return None
