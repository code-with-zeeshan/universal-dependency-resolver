"""Pinning policy engine — user-configurable dependency pinning, freezing, and blocking."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PinningPolicy:
    """User-configurable pinning policy for dependency resolution.

    Attributes
    ----------
    pin_mode
        Global pinning strategy: ``"none"`` (default), ``"patch"`` (auto-pin to latest
        patch in resolved range), ``"minor"`` (auto-pin to latest minor), or ``"exact"``
        (pin all packages to the exact version the solver chose).
    pinned
        Per-package exact-version overrides ``{name: version}``.  The solver will
        replace the package's constraint with ``==version``.
    blocked
        Package names to exclude from resolution entirely.  The solver will refuse
        to produce a solution if a blocked package is required.
    freeze
        If ``True`` and a lock file is present, all packages that appear in the lock
        file are constrained to their locked version.  Only new/changed packages
        go through re-resolution.

    """

    pin_mode: str = "none"
    pinned: dict[str, str] = field(default_factory=dict)
    blocked: list[str] = field(default_factory=list)
    freeze: bool = False


def apply_pinning_policy(
    packages: list[dict],
    policy: PinningPolicy | None,
) -> list[dict]:
    """Apply pinning *policy* to *packages* (resolver inputs), in place.

    Returns the filtered list of packages (blocked packages removed).
    """
    if policy is None:
        return list(packages)

    result: list[dict] = []
    for pkg in packages:
        name = pkg.get("name", "")

        if name in policy.blocked:
            logger.info("Blocked package '%s' removed from resolution", name)
            continue

        constraint = pkg.get("version_constraint", "*")

        if name in policy.pinned:
            constraint = f"=={policy.pinned[name]}"
            logger.debug("Pinned %s to %s", name, constraint)
        elif policy.pin_mode != "none" and constraint and constraint != "*":
            constraint = _apply_pin_mode(constraint, policy.pin_mode, name)

        pkg["version_constraint"] = constraint
        result.append(pkg)

    return result


def freeze_from_lock(
    packages: list[dict],
    lock_data: dict | None,
) -> list[dict]:
    """Overlay locked versions from *lock_data* onto *packages*.

    For each package that appears in both the resolver inputs and the lock file,
    its ``version_constraint`` is replaced with ``==locked_version``.
    """
    if not lock_data:
        return list(packages)

    locked_pkgs = lock_data.get("packages", {})
    result: list[dict] = []
    for pkg in packages:
        name = pkg.get("name", "")
        locked = locked_pkgs.get(name, {})
        locked_ver = locked.get("resolved_version") or locked.get("version", "")
        if locked_ver:
            pkg["version_constraint"] = f"=={locked_ver}"
            logger.debug("Froze %s at %s", name, locked_ver)
        result.append(pkg)
    return result


def _apply_pin_mode(constraint: str, mode: str, name: str) -> str:
    """Narrow *constraint* to a stricter range based on *mode*.

    - ``"patch"``:  ``>=1.2.3,<1.3``  →  ``>=1.2.3,<1.2.4`` (or exact patch)
    - ``"minor"``:  ``>=1.2.3,<2.0``  →  ``~=1.2``
    - ``"exact"``:  ``>=1.2.3``       →  (no-op — exact is per-package, not global)
    """
    if mode == "exact":
        return constraint

    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version

        specs = SpecifierSet(constraint)
        # Find the most specific upper bound
        versions = sorted(
            [Version(str(s.version)) for s in specs if s.operator in (">=", ">", "==", "~=")],
        )
        if not versions:
            return constraint

        latest = versions[-1]

        if mode == "patch":
            major, minor, patch = latest.major, latest.minor, latest.micro
            return f">={latest},<{Version(f'{major}.{minor}.{patch + 1}')}"
        if mode == "minor":
            major, minor = latest.major, latest.minor
            return f">={latest},<{Version(f'{major}.{minor + 1}.0')}"
    except Exception:
        logger.debug("Could not apply pin_mode %s to '%s' for %s", mode, constraint, name)

    return constraint
