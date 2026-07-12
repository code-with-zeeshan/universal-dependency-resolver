"""Hybrid PubGrub+Z3 dependency solver.

Strategy
--------
Phase 1 — Per-ecosystem PubGrub (fast CDCL):
  Group packages by ecosystem. Resolve each ecosystem independently
  using PubGrub's CDCL algorithm (pure-Python fallback or Rust-backed
  ``pubgrub-py``).  Intra-ecosystem constraints are solved here —
  this is the 95% case that PubGrub handles in microseconds.

Phase 2 — Cross-ecosystem Z3 reconciliation (small encoding):
  Pin every package to the version PubGrub chose (1 version per
  package).  Feed this to Z3 with CUDA conflict rules, system
  constraints, and cross-ecosystem dependency edges.  With 1 Bool
  per package instead of (package × version), Z3's encoding is
  200× smaller and solves in microseconds.

If Phase 1 fails (unsatisfiable ecosystem), times out, or Phase 2
finds a cross-ecosystem conflict, fall back to full Z3 (current default).

This avoids Z3's encoding explosion (10K+ Bool vars for 500×50)
while handling cross-ecosystem constraints that PubGrub alone can't.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_PUBGRUB_TIMEOUT = 30  # seconds per ecosystem before falling back to Z3


class HybridSolver:
    """Two-phase solver: PubGrub per ecosystem + Z3 cross-eco reconciliation."""
    """Two-phase solver: PubGrub per ecosystem + Z3 cross-eco reconciliation."""

    def __init__(
        self,
        *,
        use_optimization: bool = True,
        solver_timeout: int | None = None,
    ) -> None:
        """Initialize."""
        self._use_optimization = use_optimization
        self._solver_timeout = solver_timeout
        self._prefer_compatibility: bool = True
        self._fallback_timeout: int | None = solver_timeout

    def _get_default_system_info(self) -> dict:
        """Provide default system info (drop-in for ConflictResolver compatibility)."""
        """Provide default system info (drop-in for ConflictResolver compatibility)."""
        import platform

        return {
            "os": platform.system().lower(),
            "architecture": platform.machine(),
            "runtime_versions": {
                "python": {
                    "version": ".".join(
                        str(v) for v in platform.python_version_tuple()[:2]
                    )
                }
            },
            "gpu": {"available": False, "cuda": None},
        }

    # ── Public API (same shape as ConflictResolver) ────────────────────────

    def resolve_dependencies(
        self,
        packages: list[dict[str, Any]],
        system_info: dict[str, Any] | None = None,
        prefer_compatibility: bool = True,
        solver_timeout: int | None = None,
    ) -> dict[str, Any]:
        """Resolve dependencies using hybrid PubGrub+Z3 strategy.

        Returns same ``{"status", "resolved_packages", ...}`` format as
        ``ConflictResolver.resolve_dependencies()``.
        """
        self._prefer_compatibility = prefer_compatibility
        fallback_timeout = solver_timeout or self._solver_timeout
        self._fallback_timeout = fallback_timeout

        # Phase 1: PubGrub per ecosystem
        eco_result = self._try_pubgrub_per_eco(packages)
        if eco_result["status"] != "satisfiable":
            logger.info("PubGrub per-ecosystem failed — falling back to full Z3")
            return self._full_z3_fallback(packages, system_info)

        # Phase 2: Pin PubGrub choices and verify cross-eco constraints with Z3
        pubgrub_versions: dict[str, dict] = eco_result.get("resolved_packages", {})
        if not pubgrub_versions:
            return eco_result

        z3_result = self._verify_cross_eco(
            packages, pubgrub_versions, system_info
        )
        if z3_result.get("status") == "satisfiable":
            logger.info(
                "Hybrid solver succeeded: PubGrub + Z3 cross-eco check passed"
            )
            return eco_result

        logger.info(
            "Cross-ecosystem conflict detected — falling back to full Z3"
        )
        return self._full_z3_fallback(packages, system_info)

    # ── Phase 1: PubGrub per ecosystem ────────────────────────────────────

    def _try_pubgrub_per_eco(
        self, packages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        from backend.core.pubgrub_solver import PubGrubSolver

        eco_groups: dict[str, list[dict[str, Any]]] = {}
        for pkg in packages:
            eco = pkg.get("ecosystem", "pypi")
            eco_groups.setdefault(eco, []).append(pkg)

        all_resolved: dict[str, dict[str, Any]] = {}
        for eco, pkgs in eco_groups.items():
            result = self._resolve_one_eco(PubGrubSolver, pkgs, eco)
            if result.get("status") != "satisfiable":
                return {"status": "unsatisfiable", "resolved_packages": {}}
            all_resolved.update(result.get("resolved_packages", {}))

        return {"status": "satisfiable", "resolved_packages": all_resolved}

    def _resolve_one_eco(
        self,
        solver_cls: type,
        pkgs: list[dict[str, Any]],
        ecosystem: str,
    ) -> dict[str, Any]:
        """Resolve a single ecosystem group with PubGrub (with timeout).

        The pure-Python PubGrub fallback can hang on unsatisfiable
        dependency graphs.  We run it in a daemon thread with a 30s
        timeout and fall back to Z3 if it doesn't complete.
        """
        import threading

        solver = solver_cls(
            use_optimization=self._use_optimization,
            solver_timeout=self._solver_timeout,
        )

        result_container: list[dict | None] = [None]
        error_container: list[Exception | None] = [None]

        def _run() -> None:
            try:
                result_container[0] = solver.resolve_dependencies(pkgs)
            except Exception as exc:
                error_container[0] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=_PUBGRUB_TIMEOUT)

        if thread.is_alive():
            logger.warning(
                "PubGrub timed out after %ds for ecosystem '%s' — "
                "falling back to full Z3",
                _PUBGRUB_TIMEOUT,
                ecosystem,
            )
            return {"status": "unsatisfiable", "resolved_packages": {}}

        if error_container[0] is not None:
            logger.warning(
                "PubGrub failed for ecosystem '%s': %s — "
                "falling back to full Z3",
                ecosystem,
                error_container[0],
            )
            return {"status": "unsatisfiable", "resolved_packages": {}}

        return result_container[0] if result_container[0] else {}

    # ── Phase 2: Z3 cross-eco verification ────────────────────────────────

    def _verify_cross_eco(
        self,
        original_packages: list[dict[str, Any]],
        pubgrub_versions: dict[str, dict[str, Any]],
        system_info: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Pin each package to the version PubGrub chose and verify with Z3.

        Each package gets exactly 1 ``available_versions`` entry.  Z3 then
        has nothing to *solve* — it just checks CUDA conflict rules,
        system constraints, and cross-ecosystem dependency edges.
        With 1 Bool per package the encoding is 200× smaller.
        """
        from backend.core.conflict_resolver import ConflictResolver

        pinned_packages: list[dict[str, Any]] = []
        for pkg in original_packages:
            name = pkg.get("name", "")
            resolved = pubgrub_versions.get(name)
            if not resolved:
                continue
            version = resolved.get("version", "")
            if not version:
                continue
            pinned = dict(pkg)
            pinned["available_versions"] = [version]
            pinned_packages.append(pinned)

        if not pinned_packages:
            return {"status": "satisfiable", "resolved_packages": {}}

        resolver = ConflictResolver(
            use_optimization=self._use_optimization,
        )
        return resolver.resolve_dependencies(
            pinned_packages,
            system_info,
            prefer_compatibility=self._prefer_compatibility,
            solver_timeout=self._fallback_timeout,
        )

    # ── Fallback: full Z3 (current default) ───────────────────────────────

    def _full_z3_fallback(
        self,
        packages: list[dict[str, Any]],
        system_info: dict[str, Any] | None,
    ) -> dict[str, Any]:
        from backend.core.conflict_resolver import ConflictResolver

        resolver = ConflictResolver(
            use_optimization=self._use_optimization,
        )
        return resolver.resolve_dependencies(
            packages,
            system_info,
            prefer_compatibility=self._prefer_compatibility,
            solver_timeout=self._fallback_timeout,
        )
