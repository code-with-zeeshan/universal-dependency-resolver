"""Module docstring."""
import re
from typing import Optional


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


def normalize_constraint(constraint: str, ecosystem: str) -> Optional[str]:
    """Normalize constraint."""
    given = constraint
    if not constraint:
        return "*"

    constraint = constraint.strip()
    if not constraint or constraint in ("*", "any", ""):
        return "*"

    if ecosystem in ("npm", "crates", "rubygems", "pub", "packagist"):
        result = _normalize_npm(constraint, ecosystem)
        if result is not None:
            return result

    result = _normalize_pip(constraint)
    if result is not None:
        return result

    return given.strip()


def _normalize_pip(constraint: str) -> Optional[str]:
    """Normalize pip."""
    m = re.match(r"\s*(~=)\s*(\d+(?:\.\d+)*(?:\.\d+)?)\s*$", constraint)
    if m:
        ver = m.group(2)
        major, minor, patch = parse_semver(ver)
        return f">={ver},<{major + 1}.0.0"

    m = re.match(r"\s*(!=)\s*(\d+(?:\.\d+)*(?:\.\d+)?)\s*$", constraint)
    if m:
        return f"!={m.group(2)}"

    m = re.match(r"\s*(==|>=|<=|>|<)\s*(\d+(?:\.\d+)*(?:\.\d+)?)\s*$", constraint)
    if m:
        return f"{m.group(1)}{m.group(2)}"

    m = re.match(r"\s*=\s*(\d+(?:\.\d+)*(?:\.\d+)?)\s*$", constraint)
    if m:
        return f"=={m.group(1)}"

    m = re.match(r"(?:==)?\s*(\d+)\.\*\s*$", constraint)
    if m:
        ver = m.group(1)
        return f">={ver}.0.0,<{int(ver) + 1}.0.0"

    if "," in constraint:
        parts = [p.strip() for p in constraint.split(",")]
        normalized = []
        for part in parts:
            result = _normalize_pip(part)
            if result:
                normalized.append(result)
        if len(normalized) > 1:
            return ",".join(normalized)
        elif len(normalized) == 1:
            return normalized[0]

    return None


def _normalize_npm(constraint: str, ecosystem: str) -> Optional[str]:
    """Normalize npm."""
    if ecosystem not in ("npm", "crates", "rubygems", "pub", "packagist"):
        return None

    m = re.match(r"^\^?\s*(\d+)\.\*\s*$", constraint)
    if m:
        ver = m.group(1)
        return f">={ver}.0.0,<{int(ver) + 1}.0.0"

    if ecosystem == "rubygems":
        m = re.match(r"^~>\s*(\d+(?:\.\d+)*(?:\.\d+)?)$", constraint)
        if m:
            major, minor, patch = parse_semver(m.group(1))
            return f">={m.group(1)},<{major + 1}.0.0"

    m = re.match(r"^(\^|~)\s*(\d+(?:\.\d+)*(?:\.\d+)?)$", constraint)
    if m:
        op, ver = m.group(1), m.group(2)
        major, minor, patch = parse_semver(ver)
        if op == "^":
            if major > 0:
                return f">={ver},<{major + 1}.0.0"
            elif minor > 0:
                return f">={ver},<0.{minor + 1}.0"
            else:
                return f">={ver},<0.0.{patch + 1}"
        else:
            return f">={ver},<{major}.{minor + 1}.0"

    m = re.match(r"^(\d+(?:\.\d+)*(?:\.\d+)?)$", constraint)
    if m:
        ver = m.group(1)
        major, minor, patch = parse_semver(ver)
        if ecosystem == "crates":
            if major > 0:
                return f">={ver},<{major + 1}.0.0"
            elif minor > 0:
                return f">={ver},<0.{minor + 1}.0"
            else:
                return f">={ver},<0.0.{patch + 1}"
        return f">={ver}"

    m = re.match(r"^\s*(>=|<=|>|<|==|!=)\s*(\d+(?:\.\d+)*(?:\.\d+)?)$", constraint)
    if m:
        return f"{m.group(1)}{m.group(2)}"

    return None
