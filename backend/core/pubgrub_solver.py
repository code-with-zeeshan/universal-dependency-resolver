"""PubGrub-based dependency solver — drop-in for Z3-based ConflictResolver.

This module wraps the Rust-backed ``pubgrub-py`` library as the primary
solver for UDR's dependency resolution pipeline.  When ``pubgrub-py`` is
not available, it falls back to a pure-Python implementation of the
PubGrub algorithm (``PubGrubCoreSolver``).

It supports the same ``resolve_dependencies(system_info)`` interface as
``ConflictResolver`` so the two can be used interchangeably.
"""

import asyncio
import concurrent.futures
import logging
import platform
import re
from typing import Any

logger = logging.getLogger(__name__)

from backend.settings import SOLVER_MAX_VARIABLES

try:
    from backend.core.conflict_resolver import _cluster_versions_static as _cluster_versions
except ImportError:

    def _cluster_versions(versions: list[str], max_clusters: int = 100) -> list[str]:
        if len(versions) <= max_clusters:
            return versions
        return versions[:max_clusters]


_HAS_PUBGRUB_PY: bool | None = None
"""Whether pubgrub-py is available. ``None`` means not yet checked."""

_PUBGRUB_PY_RESOLVER: type | None = None  # lazy-imported
_PUBGRUB_PY_ERROR: type = Exception  # overwritten on successful import

_PUBGRUB_CORE_SOLVER: type | None = None  # lazy-imported
_PUBGRUB_CORE_ERROR: type = Exception  # overwritten on failed import

_ASYNC_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None


def _get_async_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _ASYNC_EXECUTOR
    if _ASYNC_EXECUTOR is None:
        _ASYNC_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    return _ASYNC_EXECUTOR


def _run_async_safe(coro: Any) -> Any:
    """Run a coroutine safely whether or not an event loop is running.

    ``asyncio.run()`` raises ``RuntimeError`` when called from inside a
    running event loop (e.g. CLI ``asyncio.run(main())`` or uvicorn).
    This helper detects that case and farms the work to a background
    thread instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    pool = _get_async_executor()
    return pool.submit(asyncio.run, coro).result()


def _check_pubgrub_py() -> bool:
    """Lazy-check whether the Rust-backed pubgrub-py is available."""
    global _HAS_PUBGRUB_PY, _PUBGRUB_PY_RESOLVER, _PUBGRUB_PY_ERROR
    global _PUBGRUB_CORE_SOLVER, _PUBGRUB_CORE_ERROR

    if _HAS_PUBGRUB_PY is not None:
        return _HAS_PUBGRUB_PY

    try:
        from pubgrub_py import ResolutionError as _NEW_ERROR
        from pubgrub_py import Resolver as _NEW_RESOLVER

        _PUBGRUB_PY_RESOLVER = _NEW_RESOLVER
        _PUBGRUB_PY_ERROR = _NEW_ERROR
        _HAS_PUBGRUB_PY = True
    except ImportError:
        logger.info("pubgrub-py not installed — using pure-Python fallback")
        from backend.core.pubgrub_core import PubGrubCoreSolver as _NEW_CORE
        from backend.core.pubgrub_core import ResolutionError as _NEW_CORE_ERR

        _PUBGRUB_CORE_SOLVER = _NEW_CORE
        _PUBGRUB_CORE_ERROR = _NEW_CORE_ERR
        _HAS_PUBGRUB_PY = False

    return _HAS_PUBGRUB_PY


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
        if system_info is None:
            system_info = self._get_default_system_info()
        self._pubgrub_sys_py_version = (
            system_info.get("runtime_versions", {}).get("python", {}).get("version", "")
        )
        # Guard: reject if total available versions exceed SOLVER_MAX_VARIABLES
        total_versions = sum(len(pkg.get("available_versions", []) or []) for pkg in packages)
        if total_versions > SOLVER_MAX_VARIABLES:
            logger.warning(
                "Too many versions (%d) — exceeds SOLVER_MAX_VARIABLES (%d)",
                total_versions,
                SOLVER_MAX_VARIABLES,
            )
            return {
                "status": "unsatisfiable",
                "error": (
                    f"Too many versions ({total_versions}) — "
                    f"exceeds SOLVER_MAX_VARIABLES ({SOLVER_MAX_VARIABLES})"
                ),
                "resolved_packages": {},
            }

        if _check_pubgrub_py():
            return self._resolve_via_pubgrub_py(packages)
        return self._resolve_via_pure_python(packages)

    def _resolve_via_pubgrub_py(self, packages: list[dict]) -> dict:
        """Resolve using the Rust-backed ``pubgrub-py``."""
        """Resolve using the Rust-backed ``pubgrub-py``."""
        resolver = _PUBGRUB_PY_RESOLVER()
        requirements: dict[str, str] = {}

        sanitized_to_original: dict[str, dict[str, list[str]]] = {}

        for pkg in packages:
            name = pkg["name"]
            eco = pkg.get("ecosystem", "pypi")
            constraint = pkg.get("version_constraint", "*")
            if not constraint or constraint == "*":
                constraint = ">=0.0.0"
            requirements[name] = _normalize_constraint(constraint, eco)

            ver_python_reqs = pkg.get("version_requires_python", {})
            versions = _cluster_versions(pkg.get("available_versions", []))
            ver_map: dict[str, list[str]] = {}
            deps_map: dict[str, dict[str, str]] = {}
            for ver_str in versions:
                # Skip if per-version Python requirement is incompatible
                py_req = ver_python_reqs.get(ver_str)
                if py_req and self._pubgrub_sys_py_version:
                    try:
                        from packaging.specifiers import SpecifierSet

                        if self._pubgrub_sys_py_version not in SpecifierSet(py_req):
                            continue
                    except Exception:
                        pass
                safe_ver = _sanitize_version(ver_str)
                ver_map.setdefault(safe_ver, []).append(ver_str)
                # Collect dependencies from ALL ecosystems (cross-eco support)
                dep_specs: dict[str, str] = {}
                all_deps = pkg.get("dependencies", {})
                for dep_eco, dep_info in all_deps.items():
                    if (
                        isinstance(dep_info, dict)
                        and dep_info
                        and all(isinstance(v, str) for v in dep_info.values())
                    ):
                        for d_name, d_spec in dep_info.items():
                            dep_specs[d_name] = _normalize_constraint(d_spec, dep_eco)
                        continue
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
                            dep_specs[d_name] = _normalize_constraint(d_spec, dep_eco)
                deps_map.setdefault(name, {})[safe_ver] = dep_specs
                sanitized_to_original[name] = ver_map

            for safe_ver, deps in deps_map.get(name, {}).items():
                resolver.add_package(name, safe_ver, deps)

        try:
            if self._solver_timeout:

                async def _resolve_with_timeout():
                    loop = asyncio.get_event_loop()
                    return await asyncio.wait_for(
                        loop.run_in_executor(None, resolver.resolve, requirements),
                        timeout=self._solver_timeout / 1000.0,
                    )

                result = _run_async_safe(_resolve_with_timeout())
            else:
                result = resolver.resolve(requirements)
        except _PUBGRUB_PY_ERROR as e:
            logger.warning("pubgrub-py resolution failed: %s", e)
            return {"status": "unsatisfiable", "resolution_error": str(e), "resolved_packages": {}}
        except TimeoutError:
            logger.warning("pubgrub-py resolution timed out after %d ms", self._solver_timeout)
            return {
                "status": "unsatisfiable",
                "resolution_error": "timeout",
                "resolved_packages": {},
            }

        resolved_packages: dict[str, dict] = {}
        for r_name, r_ver in result.items():
            pkg = next((p for p in packages if p["name"] == r_name), None)
            candidates = sanitized_to_original.get(r_name, {}).get(str(r_ver), [])
            if candidates:
                exact = [v for v in candidates if v == str(r_ver)]
                if exact:
                    final_ver = exact[0]
                else:
                    stable = [v for v in candidates if not _has_prerelease_suffix(v)]
                    final_ver = (stable or candidates)[0]
            else:
                final_ver = str(r_ver)
            resolved_packages[r_name] = {
                "version": final_ver,
                "ecosystem": pkg.get("ecosystem", "pypi") if pkg else "pypi",
            }

        # Build dependency tree from original package data
        dep_tree: dict[str, dict] = {}
        for pkg in packages:
            name = pkg["name"]
            if name in resolved_packages:
                dep_edges: dict[str, dict[str, str]] = {}
                all_deps = pkg.get("dependencies", {})
                for dep_eco, dep_info in all_deps.items():
                    if (
                        isinstance(dep_info, dict)
                        and dep_info
                        and all(isinstance(v, str) for v in dep_info.values())
                    ):
                        dep_edges.setdefault(dep_eco, {}).update(
                            {
                                d_name: d_spec
                                for d_name, d_spec in dep_info.items()
                                if d_name in resolved_packages
                            }
                        )
                    elif isinstance(dep_info, dict) and "all" in dep_info:
                        for dep in dep_info["all"]:
                            d_name = getattr(
                                dep, "name", dep.get("name", "") if isinstance(dep, dict) else ""
                            )
                            d_spec = getattr(dep, "version_spec", "*")
                            if d_name and d_name in resolved_packages:
                                dep_edges.setdefault(dep_eco, {})[d_name] = d_spec
                    elif isinstance(dep_info, list):
                        for dep in dep_info:
                            if isinstance(dep, str):
                                d_name = dep
                                d_spec = "*"
                            else:
                                d_name = (
                                    dep.get("name", "")
                                    if isinstance(dep, dict)
                                    else getattr(dep, "name", "")
                                )
                                d_spec = (
                                    dep.get("version_spec", "*")
                                    if isinstance(dep, dict)
                                    else getattr(dep, "version_spec", "*")
                                )
                            if d_name and d_name in resolved_packages:
                                dep_edges.setdefault(dep_eco, {})[d_name] = d_spec
                dep_tree[name] = {
                    "version": resolved_packages[name]["version"],
                    "dependencies": dep_edges,
                }

        return {
            "status": "satisfiable",
            "resolved_packages": resolved_packages,
            "dependency_tree": dep_tree,
        }

    def _resolve_via_pure_python(self, packages: list[dict]) -> dict:
        """Resolve using the pure-Python ``PubGrubCoreSolver``."""
        """Resolve using the pure-Python ``PubGrubCoreSolver``."""
        solver = _PUBGRUB_CORE_SOLVER()
        requirements: dict[str, str] = {}

        sanitized_to_original: dict[str, dict[str, list[str]]] = {}

        for pkg in packages:
            name = pkg["name"]
            eco = pkg.get("ecosystem", "pypi")
            constraint = pkg.get("version_constraint", "*")
            if not constraint or constraint == "*":
                constraint = ">=0.0.0"
            requirements[name] = _normalize_constraint(constraint, eco)

            ver_python_reqs = pkg.get("version_requires_python", {})
            versions = _cluster_versions(pkg.get("available_versions", []))
            ver_map: dict[str, list[str]] = {}
            for ver_str in versions:
                # Skip if per-version Python requirement is incompatible
                py_req = ver_python_reqs.get(ver_str)
                if py_req and self._pubgrub_sys_py_version:
                    try:
                        from packaging.specifiers import SpecifierSet

                        if self._pubgrub_sys_py_version not in SpecifierSet(py_req):
                            continue
                    except Exception:
                        pass
                safe_ver = _sanitize_version(ver_str)
                ver_map.setdefault(safe_ver, []).append(ver_str)
                # Collect dependencies from ALL ecosystems (cross-eco support)
                dep_specs: dict[str, str] = {}
                all_deps = pkg.get("dependencies", {})
                for dep_eco, dep_info in all_deps.items():
                    if (
                        isinstance(dep_info, dict)
                        and dep_info
                        and all(isinstance(v, str) for v in dep_info.values())
                    ):
                        for d_name, d_spec in dep_info.items():
                            dep_specs[d_name] = _normalize_constraint(d_spec, dep_eco)
                        continue
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
                            dep_specs[d_name] = _normalize_constraint(d_spec, dep_eco)
                solver.add_package(name, safe_ver, dep_specs)
                sanitized_to_original[name] = ver_map

        try:
            if self._solver_timeout:

                async def _resolve_with_timeout():
                    loop = asyncio.get_event_loop()
                    return await asyncio.wait_for(
                        loop.run_in_executor(None, solver.resolve, requirements),
                        timeout=self._solver_timeout / 1000.0,
                    )

                result = _run_async_safe(_resolve_with_timeout())
            else:
                result = solver.resolve(requirements)
        except (_PUBGRUB_PY_ERROR, _PUBGRUB_CORE_ERROR) as e:
            logger.warning("Pure-Python PubGrub resolution failed: %s", e)
            return {"status": "unsatisfiable", "resolution_error": str(e), "resolved_packages": {}}
        except TimeoutError:
            logger.warning(
                "Pure-Python PubGrub resolution timed out after %d ms", self._solver_timeout
            )
            return {
                "status": "unsatisfiable",
                "resolution_error": "timeout",
                "resolved_packages": {},
            }

        resolved_packages: dict[str, dict] = {}
        for r_name, r_ver in result.items():
            pkg = next((p for p in packages if p["name"] == r_name), None)
            candidates = sanitized_to_original.get(r_name, {}).get(str(r_ver), [])
            if candidates:
                exact = [v for v in candidates if v == str(r_ver)]
                if exact:
                    final_ver = exact[0]
                else:
                    stable = [v for v in candidates if not _has_prerelease_suffix(v)]
                    final_ver = (stable or candidates)[0]
            else:
                final_ver = str(r_ver)
            resolved_packages[r_name] = {
                "version": final_ver,
                "ecosystem": pkg.get("ecosystem", "pypi") if pkg else "pypi",
            }

        # Build dependency tree from original package data
        dep_tree: dict[str, dict] = {}
        for pkg in packages:
            name = pkg["name"]
            if name in resolved_packages:
                dep_edges: dict[str, dict[str, str]] = {}
                all_deps = pkg.get("dependencies", {})
                for dep_eco, dep_info in all_deps.items():
                    if (
                        isinstance(dep_info, dict)
                        and dep_info
                        and all(isinstance(v, str) for v in dep_info.values())
                    ):
                        dep_edges.setdefault(dep_eco, {}).update(
                            {
                                d_name: d_spec
                                for d_name, d_spec in dep_info.items()
                                if d_name in resolved_packages
                            }
                        )
                    elif isinstance(dep_info, dict) and "all" in dep_info:
                        for dep in dep_info["all"]:
                            d_name = getattr(
                                dep, "name", dep.get("name", "") if isinstance(dep, dict) else ""
                            )
                            d_spec = getattr(dep, "version_spec", "*")
                            if d_name and d_name in resolved_packages:
                                dep_edges.setdefault(dep_eco, {})[d_name] = d_spec
                    elif isinstance(dep_info, list):
                        for dep in dep_info:
                            if isinstance(dep, str):
                                d_name = dep
                                d_spec = "*"
                            else:
                                d_name = (
                                    dep.get("name", "")
                                    if isinstance(dep, dict)
                                    else getattr(dep, "name", "")
                                )
                                d_spec = (
                                    dep.get("version_spec", "*")
                                    if isinstance(dep, dict)
                                    else getattr(dep, "version_spec", "*")
                                )
                            if d_name and d_name in resolved_packages:
                                dep_edges.setdefault(dep_eco, {})[d_name] = d_spec
                dep_tree[name] = {
                    "version": resolved_packages[name]["version"],
                    "dependencies": dep_edges,
                }

        return {
            "status": "satisfiable",
            "resolved_packages": resolved_packages,
            "dependency_tree": dep_tree,
        }


def _to_semver(v: str) -> str:
    """Ensure a version string has 3 semver parts (e.g. ``"4.18"`` → ``"4.18.0"``)."""
    parts = v.strip().split(".")
    version_parts = []
    for p in parts:
        if p and p[0].isdigit():
            version_parts.append(p)
        else:
            break
    while len(version_parts) < 3:
        version_parts.append("0")
    return ".".join(version_parts[:3])


def _sanitize_version(version: str) -> str:
    """Sanitize a version string for pubgrub-py compatibility.

    pubgrub-py's version parser rejects suffixes like ``.dev1``, ``.post1``,
    or ``.alpha1`` that appear after a full three-part version, and also
    rejects leading zeros in numeric parts (e.g. ``0.12.01``) and
    two-part versions (``1.0`` needs to be ``1.0.0``).
    This function strips non-numeric suffixes, normalizes leading zeros,
    and pads to three numeric parts.
    """
    version = version.strip().lstrip("vV")
    parts = version.split(".")
    clean_parts: list[str] = []
    for p in parts:
        if p and p[0].isdigit():
            num = re.match(r"\d+", p)
            if num:
                clean_parts.append(str(int(num.group())))
            else:
                break
        else:
            break
    while len(clean_parts) < 3:
        clean_parts.append("0")
    return ".".join(clean_parts[:3]) or version


def _has_prerelease_suffix(v: str) -> bool:
    """Check if a version string has a pre-release suffix stripped by _sanitize_version."""
    parts = v.split(".")
    return any(p and not p[0].isdigit() for p in parts)


def _normalize_constraint(constraint: str, ecosystem: str) -> str:
    """Normalize a version constraint to PEP 440 / PubGrub-compatible form."""
    c = constraint.strip()
    if not c:
        return ">=0.0.0"
    if c == "*":
        return ">=0.0.0"

    # Split comma-separated constraints early — each part normalised independently.
    if "," in c:
        parts = [p.strip() for p in c.split(",")]
        normalised = [_normalize_single_constraint(p, ecosystem) for p in parts if p.strip()]
        normalised = [p for p in normalised if p.strip()]
        return ",".join(normalised) if normalised else c
    return _normalize_single_constraint(c, ecosystem)


def _normalize_single_constraint(c: str, ecosystem: str) -> str:
    """Normalize a single (non-comma-separated) version constraint."""

    # Normalize 2-part versions embedded in operators to 3-part semver
    # e.g. ">=1.20" -> ">=1.20.0",  ">=2.0" -> ">=2.0.0",  "<=1.5" -> "<=1.5.0"
    # pubgrub-py cannot parse 2-part versions.
    def _pad_version_in_constraint(constraint_str: str) -> str:
        parts = constraint_str.split(".", 2)
        if len(parts) == 2:
            if parts[1] and parts[1][0].isdigit():
                return f"{parts[0]}.{parts[1]}.0"
        elif len(parts) == 1 and parts[0] and parts[0][0].isdigit():
            return f"{parts[0]}.0.0"
        return constraint_str

    # Ecosystem-specific pre-processing
    if ecosystem == "gomodules":
        c = c.lstrip("vV ")
    elif ecosystem == "rubygems" and c.startswith("~>"):
        inner = c.removeprefix("~>").strip()
        if not re.fullmatch(r"\d+(\.\d+)*", inner):
            return c
        parts = inner.split(".", 2)
        if len(parts) >= 2:
            low = _to_semver(f"{parts[0]}.{parts[1]}")
            major = int(parts[0])
            return f">={low},<{major + 1}.0.0"
        return f">={_to_semver(parts[0])},<{int(parts[0]) + 1}.0.0"

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

    # Pad 2-part version constraints (>=1.20, <=2.0, !=1.5, etc.)
    # and bare version strings to 3-part semver for pubgrub-py compatibility.
    m = re.match(r"([><=!]+)\s*(.+)", c)
    if m:
        op = m.group(1)
        ver = m.group(2)
        if ver[0].isdigit() and ver.count(".") < 2:
            return f"{op}{_pad_version_in_constraint(ver)}"
        return c
    if c[0].isdigit() and c.count(".") < 2 and all(ch.isdigit() or ch == "." for ch in c):
        return f"=={_to_semver(c)}"
    return c
