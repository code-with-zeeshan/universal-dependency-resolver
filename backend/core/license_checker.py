"""License compliance engine — SPDX normalizer + policy checker.

Usage::

    from backend.core.license_checker import check_license_compatibility

    result = check_license_compatibility({"requests": "Apache-2.0"})
    # -> {"requests": {"license": "Apache-2.0", "status": "allowed", ...}}
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SPDX alias table — maps common license identifiers to canonical SPDX IDs
# ---------------------------------------------------------------------------
_SPDX_ALIASES: dict[str, str] = {
    "mit": "MIT",
    "mit license": "MIT",
    "mit license (expat)": "MIT",
    "expat": "MIT",
    "apache 2.0": "Apache-2.0",
    "apache 2": "Apache-2.0",
    "apache2": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "bsd": "BSD-3-Clause",
    "bsd 3": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "bsd 3 clause": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd 2": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-like": "BSD-3-Clause",
    "gpl 2": "GPL-2.0-only",
    "gpl 2.0": "GPL-2.0-only",
    "gpl-2.0": "GPL-2.0-only",
    "gpl-2.0-only": "GPL-2.0-only",
    "gpl 3": "GPL-3.0-only",
    "gpl 3.0": "GPL-3.0-only",
    "gpl-3.0": "GPL-3.0-only",
    "gpl-3.0-only": "GPL-3.0-only",
    "lgpl 2.1": "LGPL-2.1-only",
    "lgpl 2.1-only": "LGPL-2.1-only",
    "lgpl-2.1": "LGPL-2.1-only",
    "lgpl-2.1-only": "LGPL-2.1-only",
    "lgpl 3": "LGPL-3.0-only",
    "lgpl 3.0": "LGPL-3.0-only",
    "lgpl-3.0": "LGPL-3.0-only",
    "lgpl-3.0-only": "LGPL-3.0-only",
    "mpl 2.0": "MPL-2.0",
    "mpl 2": "MPL-2.0",
    "mpl-2.0": "MPL-2.0",
    "mozilla public license 2.0": "MPL-2.0",
    "unlicense": "Unlicense",
    "cc0-1.0": "CC0-1.0",
    "cc0 1.0": "CC0-1.0",
    "public domain": "Unlicense",
    "zlib": "Zlib",
    "zlib/libpng": "Zlib",
    "isc": "ISC",
    "artistic-2.0": "Artistic-2.0",
    "postgresql": "PostgreSQL",
    "python software foundation license": "PSF-2.0",
    "psf": "PSF-2.0",
    "psf-2.0": "PSF-2.0",
    "boost software license 1.0": "BSL-1.0",
    "bsl-1.0": "BSL-1.0",
    "bsd 3-clause no nuclear license": "BSD-3-Clause-No-Nuclear",
}

# ---------------------------------------------------------------------------
# License category mapping
# ---------------------------------------------------------------------------
_CATEGORY: dict[str, str] = {
    "MIT": "permissive",
    "Apache-2.0": "permissive",
    "BSD-2-Clause": "permissive",
    "BSD-3-Clause": "permissive",
    "BSD-3-Clause-No-Nuclear": "permissive",
    "ISC": "permissive",
    "Zlib": "permissive",
    "Unlicense": "permissive",
    "CC0-1.0": "permissive",
    "PSF-2.0": "permissive",
    "PostgreSQL": "permissive",
    "BSL-1.0": "permissive",
    "Artistic-2.0": "permissive",
    "MPL-2.0": "weak_copyleft",
    "LGPL-2.1-only": "weak_copyleft",
    "LGPL-3.0-only": "weak_copyleft",
    "GPL-2.0-only": "strong_copyleft",
    "GPL-3.0-only": "strong_copyleft",
}

# ---------------------------------------------------------------------------
# Default policy — safe for most commercial use
# ---------------------------------------------------------------------------
DEFAULT_POLICY: dict[str, str] = {
    "permissive": "allow",
    "weak_copyleft": "warn",
    "strong_copyleft": "deny",
    "unknown": "warn",
}


def normalize_license(raw: str) -> str:
    """Normalize a raw license string to a canonical SPDX identifier.

    Handles common aliases, whitespace, and case variations.
    Returns the canonical SPDX ID, or the input if unrecognised.
    """
    cleaned = raw.strip().lower()
    # Strip period at end of sentence-like values
    cleaned = cleaned.rstrip(".")
    # Try direct alias lookup
    if cleaned in _SPDX_ALIASES:
        return _SPDX_ALIASES[cleaned]
    # Try removing surrounding quotes
    if cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1]
        if cleaned in _SPDX_ALIASES:
            return _SPDX_ALIASES[cleaned]
    # If it's already a valid-looking SPDX, return as-is
    if re.match(r"^[A-Za-z0-9.+\-]+$", raw.strip()):
        spdx = _to_spdx_case(raw.strip())
        # Check common patterns: "MIT" → MIT, "Apache-2.0" → Apache-2.0
        lower = spdx.lower()
        if lower in _SPDX_ALIASES:
            return _SPDX_ALIASES[lower]
        return spdx
    return raw.strip()


def _to_spdx_case(s: str) -> str:
    """Minimal case fix — MIT → MIT, apache-2.0 → Apache-2.0, etc."""
    parts = s.replace("-", " ").replace(".", " ").split()
    if not parts:
        return s
    # First part title-cased, rest lower
    return parts[0].title() + "".join(f"-{p.lower()}" for p in parts[1:])


def check_license_compatibility(
    package_licenses: dict[str, str | list[str]],
    policy: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Check license compatibility for a set of packages.

    Parameters
    ----------
    package_licenses
        Mapping of ``package_name`` → raw license string or list of strings.
    policy
        Optional policy override.  Defaults to ``DEFAULT_POLICY``:
        allow permissive, warn weak-copyleft, deny strong-copyleft.

    Returns
    -------
    dict
        ``{name: {license, normalized, category, status, reason}}``

    """
    policy = policy or DEFAULT_POLICY
    results: dict[str, dict[str, Any]] = {}

    for name, raw_licenses in package_licenses.items():
        if isinstance(raw_licenses, str):
            raw_licenses = [raw_licenses]

        normalized_list: list[str] = []
        for r in raw_licenses:
            n = normalize_license(r)
            if n not in normalized_list:
                normalized_list.append(n)

        categories = [_CATEGORY.get(n, "unknown") for n in normalized_list]
        overall_category = _classify_categories(categories)

        decision = _apply_policy(overall_category, policy)

        results[name] = {
            "license": raw_licenses if len(raw_licenses) > 1 else raw_licenses[0],
            "normalized": normalized_list if len(normalized_list) > 1 else normalized_list[0],
            "category": overall_category,
            "status": decision["status"],
            "reason": decision["reason"],
        }

    return results


def _classify_categories(categories: list[str]) -> str:
    """Given SPDX categories for a package, return the strictest."""
    if "strong_copyleft" in categories:
        return "strong_copyleft"
    if "weak_copyleft" in categories:
        return "weak_copyleft"
    if "unknown" in categories:
        return "unknown"
    return "permissive"


def _apply_policy(category: str, policy: dict[str, str]) -> dict[str, str]:
    """Apply policy to a license category."""
    action = policy.get(category, "warn")
    if action == "deny":
        return {
            "status": "denied",
            "reason": "GPL-family copyleft license — review before use"
            if category == "strong_copyleft"
            else "license not allowed by policy",
        }
    if action == "warn":
        return {
            "status": "warning",
            "reason": "weak copyleft — check compatibility with project license"
            if category == "weak_copyleft"
            else "license not recognised — manual review recommended"
            if category == "unknown"
            else "copyleft — review before use",
        }
    return {
        "status": "allowed",
        "reason": "permissive license — compatible with most projects"
        if category == "permissive"
        else "allowed by policy",
    }
