import re
from typing import Optional


def parse_semver(ver: str):
    parts = ver.split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return major, minor, patch


def normalize_constraint(constraint: str, ecosystem: str) -> str:
    if not constraint or constraint == "*":
        return "*"

    result = _normalize_npm(constraint, ecosystem)
    if result is not None:
        return result

    return constraint


def _normalize_npm(constraint: str, ecosystem: str) -> Optional[str]:
    if ecosystem not in ("npm", "crates", "rubygems", "pub", "packagist"):
        return None

    constraint = constraint.strip()

    if ecosystem == "rubygems":
        m = re.match(r"^~>\s*(\d+(?:\.\d+)*(?:\.\d+)?)$", constraint)
        if m:
            major, minor, patch = parse_semver(m.group(1))
            return f">={m.group(1)},<{major + 1}.0.0"
        return constraint

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

    return None
