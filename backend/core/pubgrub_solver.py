"""PubGrub-based dependency solver — drop-in for Z3-based ConflictResolver.

This module wraps the Rust-backed ``pubgrub-py`` library as the primary
solver for UDR's dependency resolution pipeline.  When ``pubgrub-py`` is
not available, it falls back to a pure-Python implementation of the
PubGrub algorithm (``PubGrubCoreSolver``).

It supports the same ``resolve_dependencies(system_info)`` interface as
``ConflictResolver`` so the two can be used interchangeably.
"""

import logging
import platform
import re
from typing import Any

logger = logging.getLogger(__name__)

_HAS_PUBGRUB_PY = False
try:
    from pubgrub_py import ResolutionError as _PubGrubPyError
    from pubgrub_py import Resolver as _PubGrubPyResolver

    _HAS_PUBGRUB_PY = True
except ImportError:
    logger.info("pubgrub-py not installed — using pure-Python fallback")
    from backend.core.pubgrub_core import PubGrubCoreSolver
    from backend.core.pubgrub_core import ResolutionError as _PubGrubCoreError
    from backend.core.pubgrub_core import ResolutionError as _PubGrubPyError


class PubGrubSolver:
    """PubGrub-based dependency solver.

    Translates UDR's package/version model into PubGrub's ``Resolver`` API
    and returns results in the same ``{"status": ..., "resolved_packages": ...}``
    format used by ``ConflictResolver``.

    Uses the Rust-backed ``pubgrub-py`` when available; falls back to a
    pure-Python implementation otherwise.
    """

    def __init__(
        self,
        *,
        use_optimization: bool = True,
        solver_timeout: int | None = None,
    ) -> None:
        """Initialize."""
        self._use_optimization = use_optimization
        self._solver_timeout = solver_timeout

    def _get_default_system_info(self) -> dict:
        """Provide default system info (drop-in for ConflictResolver)."""
        """Provide default system info (drop-in for ConflictResolver)."""
        return {
            "os": platform.system().lower(),
            "architecture": platform.machine(),
            "runtime_versions": {
                "python": {"version": ".".join(str(v) for v in platform.python_version_tuple()[:2])}
            },
            "gpu": {"available": False, "cuda": None},
        }

    def resolve_dependencies(
        self,
        packages: list[dict],
        system_info: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """Resolve a list of packages via PubGrub.

        Parameters
        ----------
        packages
            List of UDR-style package dicts with keys ``name``, ``ecosystem``,
            ``available_versions``, ``dependencies``.
        system_info
            Ignored by PubGrub (CUDA/system constraints handled separately).

        Returns
        -------
        dict
            Same shape as ``ConflictResolver.resolve_dependencies()``:
            ``{"status": "satisfiable"|"unsatisfiable",
               "resolved_packages": {name: {version, ecosystem, ...}}}``
        """
        if _HAS_PUBGRUB_PY:
            return self._resolve_via_pubgrub_py(packages)
        return self._resolve_via_pure_python(packages)

    def _resolve_via_pubgrub_py(self, packages: list[dict]) -> dict:
        """Resolve using the Rust-backed ``pubgrub-py``."""
        """Resolve using the Rust-backed ``pubgrub-py``."""
        resolver = _PubGrubPyResolver()
        requirements: dict[str, str] = {}

        for pkg in packages:
            name = pkg["name"]
            eco = pkg.get("ecosystem", "pypi")
            constraint = pkg.get("version_constraint", "*")
            if not constraint or constraint == "*":
                constraint = ">=0.0.0"
            requirements[name] = _normalize_constraint(constraint, eco)

            versions = pkg.get("available_versions", [])
            deps_map: dict[str, dict[str, str]] = {}
            for ver_str in versions:
                # Collect dependencies from ALL ecosystems (cross-eco support)
                dep_specs: dict[str, str] = {}
                all_deps = pkg.get("dependencies", {})
                for dep_eco, dep_info in all_deps.items():
                    dep_list = dep_info if isinstance(dep_info, list) else dep_info.get("all", [])
                    for dep in dep_list:
                        if isinstance(dep, str):
                            d_name = dep
                            d_spec = "*"
                        elif isinstance(dep, dict):
                            d_name = dep.get("name", "")
                            d_spec = dep.get("version_spec") or dep.get("version", "*")
                        else:
                            d_name = getattr(dep, "name", "")
                            d_spec = getattr(dep, "version_spec", "*") or getattr(
                                dep, "version", "*"
                            )
                        if d_name:
                            dep_specs[d_name] = _normalize_constraint(d_spec, eco)
                deps_map.setdefault(name, {})[ver_str] = dep_specs

            for ver_str, deps in deps_map.get(name, {}).items():
                resolver.add_package(name, ver_str, deps)

        try:
            result = resolver.resolve(requirements)
        except _PubGrubPyError as e:
            logger.warning("pubgrub-py resolution failed: %s", e)
            return {"status": "unsatisfiable", "resolution_error": str(e), "resolved_packages": {}}

        resolved_packages: dict[str, dict] = {}
        for r_name, r_ver in result.items():
            pkg = next((p for p in packages if p["name"] == r_name), None)
            resolved_packages[r_name] = {
                "version": str(r_ver),
                "ecosystem": pkg.get("ecosystem", "pypi") if pkg else "pypi",
            }

        return {"status": "satisfiable", "resolved_packages": resolved_packages}

    def _resolve_via_pure_python(self, packages: list[dict]) -> dict:
        """Resolve using the pure-Python ``PubGrubCoreSolver``."""
        """Resolve using the pure-Python ``PubGrubCoreSolver``."""
        solver = PubGrubCoreSolver()
        requirements: dict[str, str] = {}

        for pkg in packages:
            name = pkg["name"]
            eco = pkg.get("ecosystem", "pypi")
            constraint = pkg.get("version_constraint", "*")
            if not constraint or constraint == "*":
                constraint = ">=0.0.0"
            requirements[name] = _normalize_constraint(constraint, eco)

            versions = pkg.get("available_versions", [])
            for ver_str in versions:
                # Collect dependencies from ALL ecosystems (cross-eco support)
                dep_specs: dict[str, str] = {}
                all_deps = pkg.get("dependencies", {})
                for dep_eco, dep_info in all_deps.items():
                    dep_list = dep_info if isinstance(dep_info, list) else dep_info.get("all", [])
                    for dep in dep_list:
                        if isinstance(dep, str):
                            d_name = dep
                            d_spec = "*"
                        elif isinstance(dep, dict):
                            d_name = dep.get("name", "")
                            d_spec = dep.get("version_spec") or dep.get("version", "*")
                        else:
                            d_name = getattr(dep, "name", "")
                            d_spec = getattr(dep, "version_spec", "*") or getattr(
                                dep, "version", "*"
                            )
                        if d_name:
                            dep_specs[d_name] = _normalize_constraint(d_spec, eco)
                solver.add_package(name, ver_str, dep_specs)

        try:
            result = solver.resolve(requirements)
        except (_PubGrubPyError, _PubGrubCoreError) as e:
            logger.warning("Pure-Python PubGrub resolution failed: %s", e)
            return {"status": "unsatisfiable", "resolution_error": str(e), "resolved_packages": {}}

        resolved_packages: dict[str, dict] = {}
        for r_name, r_ver in result.items():
            pkg = next((p for p in packages if p["name"] == r_name), None)
            resolved_packages[r_name] = {
                "version": str(r_ver),
                "ecosystem": pkg.get("ecosystem", "pypi") if pkg else "pypi",
            }

        return {"status": "satisfiable", "resolved_packages": resolved_packages}


def _to_semver(v: str) -> str:
    """Ensure a version string has 3 semver parts (e.g. ``"4.18"`` → ``"4.18.0"``)."""
    parts = v.strip().split(".")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


def _normalize_constraint(constraint: str, ecosystem: str) -> str:
    """Normalize a version constraint to PEP 440 / PubGrub-compatible form."""
    c = constraint.strip()
    if not c:
        return ">=0.0.0"
    if c == "*":
        return ">=0.0.0"
    if c.startswith("^"):
        inner = c.removeprefix("^=").removeprefix("^")
        if not re.fullmatch(r"\d+(\.\d+)*", inner):
            return c  # not a valid semver, pass through raw
        parts = inner.split(".", 2)
        major = int(parts[0])
        if len(parts) >= 2 and parts[1] and parts[1][0].isdigit():
            low = _to_semver(f"{major}.{parts[1]}")
            return f">={low},<{major + 1}.0.0"
        return f">={_to_semver(str(major))},<{major + 1}.0.0"
    if c.startswith("~"):
        inner = c.removeprefix("~=").removeprefix("~")
        if not re.fullmatch(r"\d+(\.\d+)*", inner):
            return c  # not a valid semver, pass through raw
        parts = inner.split(".", 2)
        if len(parts) >= 2:
            low = _to_semver(f"{parts[0]}.{parts[1]}")
            minor = int(parts[1])
            return f">={low},<{parts[0]}.{minor + 1}.0"
        return f">={_to_semver(parts[0])},<{int(parts[0]) + 1}.0.0"
    # Pad bare version strings to 3 parts for pubgrub-py compatibility
    # Only apply when the string looks like a clean version (digits and dots only)
    if c[0].isdigit() and c.count(".") < 2 and all(ch.isdigit() or ch == "." for ch in c):
        return f"=={_to_semver(c)}"
    return c
