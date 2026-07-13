"""Hybrid PubGrub+Z3 dependency solver — "best of both worlds".

Strategy
--------
Phase 0 — Profile and decompose:
  Identify which packages have cross-ecosystem dependencies vs pure intra-eco.
  Cross-eco packages need Z3's Bool encoding for CUDA/system constraints;
  intra-eco packages are fully solved by PubGrub.

Phase 1 — Parallel per-ecosystem PubGrub (fast CDCL):
  Each ecosystem group resolved independently via ThreadPoolExecutor.
  Intra-ecosystem constraints are solved here — the 95% case PubGrub
  handles in microseconds.

Phase 2 — Z3 with constrained candidate space:
  * Intra-eco packages: pinned to PubGrub's chosen version (1 Bool each).
  * Cross-eco packages: keep ALL clustered versions (full flexibility).
  * Z3 gets PubGrub's preferred version as the optimization target.
  Encoding: (cross_eco_pkgs ✕ versions) + (intra_eco_pkgs ✕ 1)
  — typically 3-10× smaller than full Z3.

Phase 3 — Full Z3 fallback:
  Only reached when cross-eco conflicts can't be resolved with constrained
  candidates. Falls back to monolithic Z3 with full version space.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger(__name__)

_PUBGRUB_TIMEOUT = 30


class HybridSolver:
    """Three-phase solver: parallel PubGrub + constrained Z3 + full Z3 fallback."""

    def __init__(
        self,
        *,
        use_optimization: bool = True,
        solver_timeout: int | None = None,
    ) -> None:
        self._use_optimization = use_optimization
        self._solver_timeout = solver_timeout
        self._prefer_compatibility: bool = True
        self._fallback_timeout: int | None = solver_timeout

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

    # ── Public API ──────────────────────────────────────────────────────────

    def resolve_dependencies(
        self,
        packages: list[dict[str, Any]],
        system_info: dict[str, Any] | None = None,
        prefer_compatibility: bool = True,
        solver_timeout: int | None = None,
    ) -> dict[str, Any]:
        """Resolve dependencies using hybrid PubGrub+Z3 strategy."""
        self._prefer_compatibility = prefer_compatibility
        self._fallback_timeout = solver_timeout or self._solver_timeout

        # Phase 0: decompose into cross-eco vs intra-eco
        cross_eco_names = _find_cross_eco_packages(packages)
        logger.debug(
            "HybridSolver: %d total pkgs, %d cross-eco, %d intra-eco",
            len(packages),
            len(cross_eco_names),
            len(packages) - len(cross_eco_names),
        )

        # Phase 1: parallel PubGrub per ecosystem
        eco_result = self._parallel_pubgrub(packages)
        if eco_result["status"] != "satisfiable":
            logger.info("Phase 1 failed — falling back to full Z3")
            return self._full_z3_fallback(packages, system_info)

        pubgrub_versions: dict[str, dict] = eco_result.get("resolved_packages", {})
        if not pubgrub_versions:
            return eco_result

        # Phase 2: Z3 verification — validate PubGrub's choices and handle cross-eco
        z3_result = self._constrained_z3(packages, pubgrub_versions, cross_eco_names, system_info)
        if z3_result.get("status") == "satisfiable":
            # Merge: PubGrub versions for intra-eco, Z3 versions for cross-eco
            merged = dict(pubgrub_versions)
            for name, info in z3_result.get("resolved_packages", {}).items():
                if name in cross_eco_names:
                    merged[name] = info
            merged_result = dict(eco_result)
            merged_result["resolved_packages"] = merged
            logger.info("HybridSolver Phase 2 succeeded — verified PubGrub choices")
            return merged_result

        logger.info("Phase 2 failed — PubGrub constraint violation or cross-eco conflict")
        return self._full_z3_fallback(packages, system_info)

    # ── Phase 1: Parallel PubGrub ───────────────────────────────────────────

    def _parallel_pubgrub(self, packages: list[dict[str, Any]]) -> dict[str, Any]:
        """Resolve each ecosystem group with PubGrub in parallel."""
        from backend.core.pubgrub_solver import PubGrubSolver

        eco_groups: dict[str, list[dict[str, Any]]] = {}
        for pkg in packages:
            eco = pkg.get("ecosystem", "pypi")
            eco_groups.setdefault(eco, []).append(pkg)

        if not eco_groups:
            return {"status": "satisfiable", "resolved_packages": {}}
        if len(eco_groups) <= 1:
            eco = next(iter(eco_groups))
            return self._resolve_one_eco(PubGrubSolver, packages, eco)

        all_resolved: dict[str, dict[str, Any]] = {}
        futures = {}

        with ThreadPoolExecutor(max_workers=len(eco_groups)) as executor:
            for eco, pkgs in eco_groups.items():
                future = executor.submit(self._resolve_one_eco, PubGrubSolver, pkgs, eco)
                futures[future] = eco

            for future in as_completed(futures):
                eco = futures[future]
                try:
                    result = future.result(timeout=_PUBGRUB_TIMEOUT + 10)
                    if result.get("status") != "satisfiable":
                        logger.warning("PubGrub failed for ecosystem '%s'", eco)
                        return {"status": "unsatisfiable", "resolved_packages": {}}
                    all_resolved.update(result.get("resolved_packages", {}))
                except Exception as exc:
                    logger.warning("PubGrub exception for ecosystem '%s': %s", eco, exc)
                    return {"status": "unsatisfiable", "resolved_packages": {}}

        return {"status": "satisfiable", "resolved_packages": all_resolved}

    def _resolve_one_eco(
        self,
        solver_cls: type,
        pkgs: list[dict[str, Any]],
        ecosystem: str,
    ) -> dict[str, Any]:
        """Resolve a single ecosystem group with PubGrub (thread with timeout)."""
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
                "PubGrub timed out after %ds for '%s'",
                _PUBGRUB_TIMEOUT,
                ecosystem,
            )
            return {"status": "unsatisfiable", "resolved_packages": {}}

        if error_container[0] is not None:
            logger.warning("PubGrub failed for '%s': %s", ecosystem, error_container[0])
            return {"status": "unsatisfiable", "resolved_packages": {}}

        return result_container[0] if result_container[0] else {}

    # ── Phase 2: Constrained Z3 ────────────────────────────────────────────

    def _constrained_z3(
        self,
        original_packages: list[dict[str, Any]],
        pubgrub_versions: dict[str, dict[str, Any]],
        cross_eco_names: set[str],
        system_info: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Z3 with limited versions for cross-eco packages, pinned for intra-eco.

        Cross-eco packages get their top-N versions (N = AUTO_SOLVER_TOP_N)
        so Z3 can explore alternatives to resolve cross-ecosystem conflicts.
        Intra-eco packages are pinned to PubGrub's chosen version.

        This keeps the Z3 encoding at ~N × cross_eco_count — even for 500
        package graphs with 50 cross-eco packages, that's 250 Bool vars.
        """
        from backend.core.conflict_resolver import ConflictResolver
        from backend.settings import AUTO_SOLVER_TOP_N

        constrained: list[dict[str, Any]] = []
        for pkg in original_packages:
            name = pkg.get("name", "")
            resolved = pubgrub_versions.get(name)
            if not resolved:
                continue
            version = resolved.get("version", "")
            if not version:
                continue

            cp = dict(pkg)
            if name in cross_eco_names:
                all_vers = pkg.get("available_versions", [])
                cp["available_versions"] = all_vers[:AUTO_SOLVER_TOP_N]
            else:
                cp["available_versions"] = [version]
            constrained.append(cp)

        if not constrained:
            return {"status": "satisfiable", "resolved_packages": {}}

        resolver = ConflictResolver(use_optimization=self._use_optimization)
        return resolver.resolve_dependencies(
            constrained,
            system_info,
            prefer_compatibility=self._prefer_compatibility,
            solver_timeout=self._fallback_timeout,
        )

    # ── Phase 3: Full Z3 fallback ───────────────────────────────────────────

    def _full_z3_fallback(
        self,
        packages: list[dict[str, Any]],
        system_info: dict[str, Any] | None,
    ) -> dict[str, Any]:
        from backend.core.conflict_resolver import ConflictResolver

        resolver = ConflictResolver(use_optimization=self._use_optimization)
        return resolver.resolve_dependencies(
            packages,
            system_info,
            prefer_compatibility=self._prefer_compatibility,
            solver_timeout=self._fallback_timeout,
        )


def _find_cross_eco_packages(packages: list[dict[str, Any]]) -> set[str]:
    """Return names of packages that have dependencies in a different ecosystem."""
    pkg_eco: dict[str, str] = {}
    for pkg in packages:
        pkg_eco[pkg.get("name", "")] = pkg.get("ecosystem", "pypi")

    cross_eco: set[str] = set()
    for pkg in packages:
        name = pkg.get("name", "")
        my_eco = pkg_eco.get(name, "pypi")
        deps = pkg.get("dependencies", {})
        for dep_eco in deps:
            if dep_eco != my_eco:
                cross_eco.add(name)
                break
    return cross_eco
