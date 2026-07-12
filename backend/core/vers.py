"""Universal version spec — normalize ecosystem constraints into PEP 440.

Each ecosystem has its own constraint syntax (npm ``^1.2.0``, Ruby ``~> 1.2``,
Go ``v1.2.3``, etc.).  `VersSpec` parses any of them into a normalized
intermediate representation that can be converted to a PEP 440 ``SpecifierSet``
for the Z3 solver.

Usage::

    spec = VersSpec.parse("^1.2.0", "npm")
    assert spec.is_compatible("1.5.0")
    assert not spec.is_compatible("2.0.0")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from packaging.specifiers import SpecifierSet
from packaging.version import parse as parse_version

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VersSpec:
    """Normalised version-range spec.

    Fields
    ------
    ecosystem
        Source ecosystem identifier (e.g. ``"npm"``, ``"rubygems"``).
    raw
        Original constraint string as supplied by the user / manifest.
    pep508
        PEP 508 / PEP 440 representation suitable for ``SpecifierSet``
        (e.g. ``">=1.2.0,<2.0.0"``, ``"==1.2.3"``, ``"*"``).
    """

    ecosystem: str
    raw: str
    pep508: str = "*"

    # ── factory ──────────────────────────────────────────────────────

    @staticmethod
    def parse(constraint: str | None, ecosystem: str) -> VersSpec:
        """Parse *constraint* using the grammar for *ecosystem*."""
        if constraint is None:
            constraint = ""
        parser = _PARSERS.get(ecosystem) or _parse_pip
        return parser(constraint, ecosystem)

    # ── consumers ────────────────────────────────────────────────────

    def to_specifier_set(self) -> SpecifierSet | None:
        """Return a PEP 440 ``SpecifierSet``, or *None* if universal."""
        if self.pep508 == "*":
            return None
        try:
            return SpecifierSet(self.pep508)
        except Exception:
            return None

    def is_compatible(self, version_str: str) -> bool:
        """Return *True* if *version_str* satisfies this spec."""
        if self.pep508 == "*":
            return True
        try:
            ver = parse_version(version_str)
            spec = SpecifierSet(self.pep508)
            return ver in spec
        except Exception:
            return False

    def __str__(self) -> str:
        """Str."""
        return self.pep508 if self.pep508 != "*" else "*"

    def __repr__(self) -> str:
        """Repr."""
        return f"VersSpec(eco={self.ecosystem}, raw={self.raw!r}, pep508={self.pep508!r})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VersionTuple = tuple[int, int, int]
_SEMVER_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _parse_semver(text: str) -> VersionTuple:
    m = _SEMVER_RE.match(text.strip())
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2) or "0"), int(m.group(3) or "0"))


def _fmt(v: VersionTuple) -> str:
    return f"{v[0]}.{v[1]}.{v[2]}"


# ---------------------------------------------------------------------------
# Per-ecosystem parsers  (registered in _PARSERS)
# ---------------------------------------------------------------------------


def _parse_pip(constraint: str, ecosystem: str) -> VersSpec:
    """PyPI / pip-style: ``>=1.0,<2.0``, ``~=1.0``, ``==1.2.3``, ``!=1.0``."""
    c = constraint.strip()
    if not c or c in ("*", "any", ""):
        return VersSpec(ecosystem, constraint, "*")

    m = re.match(r"\s*(~=)\s*([\d.]+)\s*$", c)
    if m:
        ver = m.group(2)
        major, _minor, _patch = _parse_semver(ver)
        pep = f">={ver},<{major + 1}.0.0"
        return VersSpec(ecosystem, constraint, pep)

    m = re.match(r"\s*(!=)\s*([\d.]+)\s*$", c)
    if m:
        return VersSpec(ecosystem, constraint, f"!={m.group(2)}")

    m = re.match(r"\s*(==|>=|<=|>|<)\s*([\d.]+)\s*$", c)
    if m:
        return VersSpec(ecosystem, constraint, f"{m.group(1)}{m.group(2)}")

    m = re.match(r"\s*=\s*([\d.]+)\s*$", c)
    if m:
        return VersSpec(ecosystem, constraint, f"=={m.group(1)}")

    m = re.match(r"(?:==)?\s*(\d+)\.\*\s*$", c)
    if m:
        ver = m.group(1)
        pep = f">={ver}.0.0,<{int(ver) + 1}.0.0"
        return VersSpec(ecosystem, constraint, pep)

    if "," in c:
        parts = [p.strip() for p in c.split(",")]
        normalised = [_parse_pip(p, ecosystem).pep508 for p in parts]
        valid = [n for n in normalised if n != "*"]
        if valid:
            return VersSpec(ecosystem, constraint, ",".join(valid))

    return VersSpec(ecosystem, constraint, constraint)


def _parse_npm_like(constraint: str, ecosystem: str) -> VersSpec:
    """Npm / crates / pub / packagist: ``^1.2.0``, ``~1.2.0``, bare ``1.2``."""
    c = constraint.strip()
    if not c or c in ("*", "any", ""):
        return VersSpec(ecosystem, constraint, "*")

    m = re.match(r"^\^?\s*(\d+)\.\*\s*$", c)
    if m:
        ver = m.group(1)
        return VersSpec(ecosystem, constraint, f">={ver}.0.0,<{int(ver) + 1}.0.0")

    m = re.match(r"^~>\s*([\d.]+)$", c)
    if m and ecosystem == "rubygems":
        major, _minor, _patch = _parse_semver(m.group(1))
        return VersSpec(ecosystem, constraint, f">={m.group(1)},<{major + 1}.0.0")

    m = re.match(r"^(\^|~)\s*([\d.]+)$", c)
    if m:
        op, ver = m.group(1), m.group(2)
        major, minor, patch = _parse_semver(ver)
        if op == "^":
            if major > 0:
                return VersSpec(ecosystem, constraint, f">={ver},<{major + 1}.0.0")
            if minor > 0:
                return VersSpec(ecosystem, constraint, f">={ver},<0.{minor + 1}.0")
            return VersSpec(ecosystem, constraint, f">={ver},<0.0.{patch + 1}")
        return VersSpec(ecosystem, constraint, f">={ver},<{major}.{minor + 1}.0")

    m = re.match(r"^([\d.]+)$", c)
    if m:
        ver = m.group(1)
        major, minor, patch = _parse_semver(ver)
        if ecosystem == "crates":
            if major > 0:
                return VersSpec(ecosystem, constraint, f">={ver},<{major + 1}.0.0")
            if minor > 0:
                return VersSpec(ecosystem, constraint, f">={ver},<0.{minor + 1}.0")
            return VersSpec(ecosystem, constraint, f">={ver},<0.0.{patch + 1}")
        return VersSpec(ecosystem, constraint, f">={ver}")

    m = re.match(r"^\s*(>=|<=|>|<|==|!=)\s*([\d.]+)$", c)
    if m:
        return VersSpec(ecosystem, constraint, f"{m.group(1)}{m.group(2)}")

    return VersSpec(ecosystem, constraint, c)


def _parse_go(constraint: str, ecosystem: str) -> VersSpec:
    """Go modules: ``v1.2.3``, pseudo-versions, ``>=1.2, <1.3``."""
    c = constraint.strip()
    if not c or c in ("*", "any", ""):
        return VersSpec(ecosystem, constraint, "*")
    c = c.lstrip("=vV ")
    return VersSpec(ecosystem, constraint, f">={c}")


def _parse_hex(constraint: str, ecosystem: str) -> VersSpec:
    """Hex / Elixir: ``~> 1.2`` (pessimistic, different from Ruby's)."""
    c = constraint.strip()
    if not c or c in ("*", "any", ""):
        return VersSpec(ecosystem, constraint, "*")
    m = re.match(r"^~>\s*([\d.]+)$", c)
    if m:
        ver = m.group(1)
        parts = ver.split(".")
        if len(parts) == 1:
            return VersSpec(ecosystem, constraint, f">={ver}.0.0,<{int(parts[0]) + 1}.0.0")
        major, minor, _patch = _parse_semver(ver)
        return VersSpec(ecosystem, constraint, f">={ver},<{major}.{minor + 1}.0")
    return _parse_npm_like(c, ecosystem)


def _parse_swift(constraint: str, ecosystem: str) -> VersSpec:
    r"""Swift: ``from: \"1.2.3\"``, ``exact: \"1.2.3\"``, ``branch: \"main\"``."""
    c = constraint.strip()
    if not c or c in ("*", "any", ""):
        return VersSpec(ecosystem, constraint, "*")
    m = re.match(r'(?:from|exact|branch|revision):\s*"([^"]+)"', c)
    if m:
        value = m.group(1)
        if c.startswith("exact"):
            return VersSpec(ecosystem, constraint, f"=={value}")
    return VersSpec(ecosystem, constraint, c)


# All constraint syntaxes that map to npm-like behaviour by default
_NPM_LIKE = frozenset({"npm", "crates", "pub", "packagist", "rubygems"})

# Registered parser dispatch
_PARSERS: dict[str, Any] = {
    "pypi": _parse_pip,
    "conda": _parse_pip,
    "npm": _parse_npm_like,
    "crates": _parse_npm_like,
    "pub": _parse_npm_like,
    "packagist": _parse_npm_like,
    "rubygems": _parse_npm_like,
    "gomodules": _parse_go,
    "hex": _parse_hex,
    "swift": _parse_swift,
    "homebrew": _parse_pip,
    "apt": _parse_pip,
    "apk": _parse_pip,
    "haskell": _parse_pip,
    "gradle": _parse_npm_like,
    "cocoapods": _parse_npm_like,
    "nuget": _parse_npm_like,
    "maven": _parse_npm_like,
}


def parse(constraint: str, ecosystem: str) -> VersSpec:
    """Shorthand for ``VersSpec.parse(constraint, ecosystem)``."""
    return VersSpec.parse(constraint, ecosystem)
