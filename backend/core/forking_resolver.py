"""ForkingResolver — cross-solver validator + constraint relaxation fallback.

When the primary solver returns ``unsatisfiable`` or ``timeout``, this
resolver:

1. Runs the alternate solver (PubGrub ↔ Z3) on the same input to
   cross-validate.  If the alternate finds a solution, it is returned
   with a warning.

2. If both solvers agree on ``unsatisfiable`` (or no alternate is
   available), tries **constraint relaxation** — widening version
   constraints (removing upper bounds) on all packages.  This works
   around cases where the solver's per-version dependency data is
   incomplete or overly restrictive.

3. If constraint relaxation also fails, the original failure result is
   returned.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _widen_constraint(constraint: str) -> str:
    """Remove upper-bound constraints, keeping only lower bounds.

    ``==1.2.3``  → ``>=1.2.3``
    ``>=1.0,<2.0`` → ``>=1.0``
    ``>1.0,<2.0`` → ``>1.0``
    ``*`` → ``*``
    ``>=1.0`` → ``>=1.0``
    """
    if not constraint or constraint == "*":
        return "*"
    parts = [p.strip() for p in constraint.split(",")]
    lower = [p for p in parts if re.match(r"^[>=]+", p)]
    exact = [p for p in parts if p.startswith("==")]
    if not lower and not exact:
        return "*"
    if exact and not lower:
        return ">=" + exact[0][2:]
    return ", ".join(lower) if lower else "*"


class ForkingResolver:
    """Meta-solver with cross-validation and constraint relaxation.

    Args:
        primary_solver: The primary solver instance (used first).
        alternate_solver_factory: A zero-arg callable returning the
            alternate solver.  Called only when the primary fails.
    """

    def __init__(
        self,
        primary_solver: Any,
        alternate_solver_factory: Any = None,
    ) -> None:
        self._primary = primary_solver
        self._alt_factory = alternate_solver_factory
        self._alternate: Any = None

    def _get_alternate(self) -> Any:
        if self._alternate is None and self._alt_factory is not None:
            self._alternate = self._alt_factory()
        return self._alternate

    def _get_default_system_info(self) -> dict:
        return self._primary._get_default_system_info()

    @staticmethod
    def _relax_packages(packages: list[dict]) -> list[dict]:
        """Return a copy of *packages* with all constraints widened.

        1. Widen root version constraints (remove upper bounds).
        2. Swap narrow per-version dependency constraints for the wide
           merged set (``_fallback_dependencies``).  This works around
           cases where per-version dep data is incomplete or overly
           restrictive — the merged set includes deps from all versions,
           giving the solver more flexibility.
        """
        relaxed: list[dict] = []
        for pkg in packages:
            p = copy.deepcopy(pkg)
            ver = p.get("version", "*")
            if ver and ver != "*":
                p["version"] = _widen_constraint(ver)
            # Swap narrow per-version deps for wide merged deps when available
            if "_fallback_dependencies" in p:
                p["dependencies"] = p.pop("_fallback_dependencies")
            relaxed.append(p)
        return relaxed

    def resolve_dependencies(
        self,
        packages: list[dict],
        system_info: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """Resolve, cross-validate, then relax constraints on persistent failure."""
        result = self._primary.resolve_dependencies(packages, system_info, **kwargs)
        status = result.get("status", "")
        if status in ("satisfiable", "satisfiable_with_warnings"):
            return result

        cross: dict[str, Any] = {"primary_status": status}

        # --- Step 1: cross-validate with alternate solver ---
        alternate = self._get_alternate()
        if alternate is not None:
            logger.info(
                "ForkingResolver: primary solver failed (%s), cross-validating with alternate",
                status,
            )
            try:
                alt_result = alternate.resolve_dependencies(packages, system_info, **kwargs)
                alt_status = alt_result.get("status", "")
            except Exception as exc:
                logger.debug("ForkingResolver: alternate solver also failed: %s", exc)
                cross["alternate_status"] = "error"
                cross["alternate_error"] = str(exc)
                alt_status = "error"

            cross["alternate_status"] = alt_status

            if alt_status in ("satisfiable", "satisfiable_with_warnings"):
                logger.warning(
                    "ForkingResolver: solvers disagree! Primary=%s, Alternate=%s. "
                    "Using alternate solution.",
                    status,
                    alt_status,
                )
                alt_result["solver"] = alt_result.get("solver", "") + "+cross-validated"
                alt_result["cross_validation"] = cross
                return alt_result

        # --- Step 2: constraint relaxation fallback ---
        logger.info(
            "ForkingResolver: trying constraint relaxation fallback (primary=%s, alt=%s)",
            status,
            cross.get("alternate_status", "N/A"),
        )
        try:
            relaxed_pkgs = self._relax_packages(packages)
            relaxed_result = self._primary.resolve_dependencies(relaxed_pkgs, system_info, **kwargs)
            relaxed_status = relaxed_result.get("status", "")
        except Exception as exc:
            logger.debug("ForkingResolver: constraint relaxation also failed: %s", exc)
            cross["relaxation_status"] = "error"
            cross["relaxation_error"] = str(exc)
            result["cross_validation"] = cross
            return result

        cross["relaxation_status"] = relaxed_status
        if relaxed_status in ("satisfiable", "satisfiable_with_warnings"):
            logger.warning(
                "ForkingResolver: primary solver succeeded after constraint relaxation",
            )
            relaxed_result["solver"] = relaxed_result.get("solver", "") + "+relaxed"
            relaxed_result["cross_validation"] = cross
            return relaxed_result

        # --- All paths failed ---
        result["cross_validation"] = cross
        if cross.get("alternate_status") in ("satisfiable", "satisfiable_with_warnings"):
            return alt_result  # type: ignore[possibly-undefined]
        return result
