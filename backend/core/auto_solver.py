"""AutoSolver — profiles the dependency graph and delegates to the fastest solver backend.

Decision matrix
---------------
| Profile                          | Solver       | Rationale                          |
|----------------------------------|--------------|------------------------------------|
| ↓ Small, no CUDA                 | PubGrub      | CDCL in microseconds               |
| Single eco, with CUDA            | Z3           | CUDA conflict rules need Bool vars |
| Multi eco, CUDA / cross-deps     | HybridSolver | PubGrub per-eco + Z3 cross-eco     |
| Multi eco, no CUDA, no cross     | PubGrub      | Ecosystems independent             |
| > LARGE pkgs, no CUDA            | PubGrub      | Avoid Z3 O(V²) encoding explosion  |
| > LARGE pkgs, with CUDA          | Z3           | CUDA requires Bool encoding        |
| Any solver fails                 | Try next     | PubGrub ↔ Hybrid ↔ Z3 chain        |

Notes
-----
- ``_resolve_with_alternatives`` (hand-written DFS below Z3) is
  **disabled by default** — Z3 is a CDCL SAT solver, and if it
  returns unsat, a naive DFS won't find a solution it missed.
- ForkingResolver is disabled by default (``USE_FORKING_SOLVER=false``).
"""

from __future__ import annotations

import logging
from typing import Any

from backend.settings import (
    AUTO_SOLVER_LARGE_THRESHOLD,
    AUTO_SOLVER_SMALL_THRESHOLD,
    USE_HYBRID_SOLVER,
    USE_PUBGRUB_SOLVER,
    USE_Z3_SOLVER,
)

logger = logging.getLogger(__name__)


class AutoSolver:
    """Profiles the dependency graph and delegates to the fastest solver.

    Respects explicit env-var overrides (USE_Z3_SOLVER, USE_HYBRID_SOLVER,
    USE_PUBGRUB_SOLVER) when set.  Otherwise profiles and auto-selects.
    """

    def __init__(
        self,
        *,
        use_optimization: bool = True,
        solver_timeout: int | None = None,
    ) -> None:
        """Initialize the AutoSolver."""
        self._use_optimization = use_optimization
        self._solver_timeout = solver_timeout

    def _get_default_system_info(self) -> dict:
        import platform

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
        packages: list[dict[str, Any]],
        system_info: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Profile packages and delegate to the optimal solver backend."""
        profile = _profile_packages(packages, system_info)

        # Respect explicit env-var overrides first
        solver, name = self._select_solver(profile)

        logger.info(
            "AutoSolver selected '%s': %s",
            name,
            _fmt_profile(profile),
        )

        result = solver.resolve_dependencies(packages, system_info, **kwargs)
        result["solver"] = name

        if result.get("status") == "satisfiable":
            return result

        # Fallback chain: try the next solver in priority order
        logger.info(
            "AutoSolver fallback: '%s' failed (%s), trying next", name, result.get("status")
        )
        fallback_solvers = self._fallback_chain(profile)
        for fb_name, fb_solver in fallback_solvers:
            logger.info("AutoSolver fallback: trying '%s'", fb_name)
            fb_result = fb_solver.resolve_dependencies(packages, system_info, **kwargs)
            fb_result["solver"] = fb_name
            if fb_result.get("status") == "satisfiable":
                return fb_result

        return result

    def _select_solver(self, profile: dict) -> tuple[Any, str]:
        """Select solver based on profile and env-var overrides."""
        # Respect explicit env-var overrides first
        if USE_Z3_SOLVER:
            solver = self._z3_solver()
            if solver is not None:
                return solver, "z3-override"
            logger.warning("USE_Z3_SOLVER=true but z3-solver not installed; falling back")
        if USE_HYBRID_SOLVER:
            solver = self._hybrid_solver()
            if solver is not None:
                return solver, "hybrid-override"
            logger.warning("USE_HYBRID_SOLVER=true but z3-solver not installed; falling back")
        if USE_PUBGRUB_SOLVER:
            return self._pubgrub_solver(), "pubgrub-override"

        # GPU constraint detection — Z3 is required for GPU conflict rules
        if profile["has_gpu_constraint"]:
            if profile["multi_eco"] and profile["has_cross_eco_deps"]:
                solver = self._hybrid_solver()
                if solver is not None:
                    return solver, "hybrid-gpu-multi"
                logger.warning(
                    "z3-solver not installed for hybrid-gpu-multi; falling to Z3 single-pass"
                )
                z3_s = self._z3_solver()
                if z3_s is not None:
                    return z3_s, "z3-gpu-multi-fallback"
            else:
                solver = self._z3_solver()
                if solver is not None:
                    return solver, "z3-gpu"
                logger.warning(
                    "GPU constraints detected but z3-solver not installed; "
                    "GPU conflict rules will be skipped"
                )

        # Decision tree — CUDA already handled above, rest is profile-based
        if profile["multi_eco"] and profile["has_cross_eco_deps"]:
            solver = self._hybrid_solver()
            if solver is not None:
                return solver, "hybrid-multi-eco"
            logger.warning(
                "z3-solver not installed for hybrid-multi-eco; falling back to Z3 single-pass"
            )
            z3_s = self._z3_solver()
            if z3_s is not None:
                return z3_s, "z3-multi-eco-fallback"
            logger.warning("z3 not available either; cross-eco rules will be skipped")

        if profile["has_cross_eco_deps"]:
            solver = self._hybrid_solver()
            if solver is not None:
                return solver, "hybrid-cross-eco"
            logger.warning("z3-solver not installed for hybrid-cross-eco; falling to PubGrub")

        if profile["is_small"]:
            return self._pubgrub_solver(), "pubgrub-small"

        if profile["is_large"] and not profile["has_cross_eco_deps"]:
            return self._pubgrub_solver(), "pubgrub-large"

        return self._pubgrub_solver(), "pubgrub-default"

    def _fallback_chain(self, profile: dict) -> list[tuple[str, Any]]:
        """Build fallback chain: next-best solvers after the initial choice."""
        chain: list[tuple[str, Any]] = []

        prefer_pubgrub = not profile["has_gpu_constraint"] and not profile["multi_eco"]
        if prefer_pubgrub:
            z3_s = self._z3_solver()
            if z3_s is not None:
                chain.append(("z3-fallback", z3_s))
            hybrid_s = self._hybrid_solver()
            if hybrid_s is not None:
                chain.append(("hybrid-fallback", hybrid_s))
        else:
            chain.append(("pubgrub-fallback", self._pubgrub_solver()))
            z3_s = self._z3_solver()
            if z3_s is not None:
                chain.append(("z3-fallback", z3_s))

        return chain

    def _pubgrub_solver(self) -> Any:
        from backend.core.pubgrub_solver import PubGrubSolver

        return PubGrubSolver(
            use_optimization=self._use_optimization, solver_timeout=self._solver_timeout
        )

    def _z3_available(self) -> bool:
        try:
            import z3  # noqa: F401

            return True
        except ImportError:
            return False

    def _z3_solver(self) -> Any | None:
        if not self._z3_available():
            logger.warning("z3-solver not installed; skipping Z3 solver path")
            return None
        from backend.core.conflict_resolver import ConflictResolver

        return ConflictResolver(use_optimization=self._use_optimization)

    def _hybrid_solver(self) -> Any | None:
        if not self._z3_available():
            logger.warning("z3-solver not installed; skipping Hybrid solver path")
            return None
        from backend.core.hybrid_solver import HybridSolver

        return HybridSolver(
            use_optimization=self._use_optimization, solver_timeout=self._solver_timeout
        )


def _fmt_profile(profile: dict) -> str:
    """Format profile dict as a concise log string."""
    return (
        f"{profile['pkg_count']} pkgs, {profile['eco_count']} ecosystems, "
        f"GPU={profile['has_gpu_constraint']}, cross={profile['has_cross_eco_deps']}, "
        f"{profile['total_versions']} total versions, "
        f"{'small' if profile['is_small'] else 'large' if profile['is_large'] else 'medium'}"
    )


def _profile_packages(
    packages: list[dict[str, Any]],
    system_info: dict[str, Any] | None = None,
) -> dict:
    """Build a profile dict describing the dependency graph shape.

    Checks both package-level ``system_requirements`` and the top-level
    ``system_info`` dict (which carries ``--cuda`` CLI flag) for CUDA presence.
    """
    ecosystems: set[str] = set()
    has_gpu_constraint = False
    total_versions = 0
    max_versions = 0
    has_cross_eco_deps = False
    pkg_eco: dict[str, str] = {}

    for pkg in packages:
        name = pkg.get("name", "")
        eco = pkg.get("ecosystem", "pypi")
        ecosystems.add(eco)
        pkg_eco[name] = eco
        versions = pkg.get("available_versions", []) or []
        total_versions += len(versions)
        max_versions = max(max_versions, len(versions))

        sr = pkg.get("system_requirements", {})
        if isinstance(sr, dict):
            for gpu_type in ("cuda", "rocm", "intel_gpu", "metal", "gpu"):
                if sr.get(gpu_type):
                    has_gpu_constraint = True
                    break

    # Also check system_info for GPU constraints (set via CLI flags)
    gpu_types = ("cuda", "rocm", "intel_gpu", "metal")
    if system_info:
        gpu = system_info.get("gpu", {})
        if isinstance(gpu, dict):
            for gpu_type in gpu_types:
                if gpu.get(gpu_type):
                    has_gpu_constraint = True
                    break
        for gpu_type in gpu_types:
            if system_info.get(gpu_type):
                has_gpu_constraint = True
                break

    # Detect cross-ecosystem dependencies
    for pkg in packages:
        deps = pkg.get("dependencies", {})
        for dep_eco, dep_list in deps.items():
            if dep_eco != pkg_eco.get(pkg.get("name", ""), "pypi"):
                has_cross_eco_deps = True
                break
        if has_cross_eco_deps:
            break

    return {
        "pkg_count": len(packages),
        "eco_count": len(ecosystems),
        "multi_eco": len(ecosystems) > 1,
        "has_gpu_constraint": has_gpu_constraint,
        "has_cross_eco_deps": has_cross_eco_deps,
        "total_versions": total_versions,
        "max_versions_per_pkg": max_versions,
        "is_small": len(packages) <= AUTO_SOLVER_SMALL_THRESHOLD,
        "is_large": len(packages) > AUTO_SOLVER_LARGE_THRESHOLD,
    }
