"""ForkingResolver — parallel portfolio meta-solver for dependency resolution.

When the primary solver returns ``unsatisfiable`` or ``timeout``, this
resolver analyses the conflict, creates N alternative fork scenarios
(with different version selections), and runs all forks in parallel via
``ThreadPoolExecutor``.  The first fork to find a solution wins.

Inspired by parallel portfolio SAT solving (ManySAT, Plingeling) and
path-forking in Prolog/CLP(FD) systems.
"""

from __future__ import annotations

import copy
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger(__name__)


def _most_constrained_packages(
    packages: list[dict],
    count: int = 3,
) -> list[tuple[int, dict]]:
    """Return the *count* most-constrained packages (most dep in-edges, fewest versions).

    Returns ``(score, pkg)`` tuples sorted descending so the caller can
    pick a target per fork.
    """
    name_to_pkg: dict[str, dict] = {}
    dep_counts: dict[str, int] = {}

    for pkg in packages:
        name = pkg.get("name", "")
        name_to_pkg[name] = pkg
        dep_counts.setdefault(name, 0)

        for deps in pkg.get("dependencies", {}).values():
            if isinstance(deps, dict):
                for dep_name in deps:
                    dep_counts.setdefault(dep_name, 0)
                    dep_counts[dep_name] += 1
            elif isinstance(deps, list):
                for d in deps:
                    dname = d.get("name") if isinstance(d, dict) else str(d)
                    dep_counts.setdefault(dname, 0)
                    dep_counts[dname] += 1

    scored: list[tuple[int, dict]] = []
    for pkg in packages:
        name = pkg.get("name", "")
        versions = pkg.get("available_versions", []) or []
        ver_count = len(versions)
        in_edges = dep_counts.get(name, 0)
        score = in_edges * 100 + (100 - ver_count) if ver_count <= 100 else in_edges
        scored.append((score, pkg))

    scored.sort(key=lambda x: -x[0])
    return scored[:count]


def _get_latest_version(pkg: dict) -> str | None:
    """Return the latest available version for a package, or *None*."""
    versions = pkg.get("available_versions", []) or []
    if not versions:
        return None
    s = sorted(versions, key=lambda v: _safe_version_key(v), reverse=True)
    return s[0] if s else None


def _safe_version_key(v: str) -> tuple:
    """Best-effort numeric version tuple for sorting."""
    try:
        from packaging.version import Version

        return Version(v)._key
    except Exception:
        parts = []
        for segment in v.split("."):
            try:
                parts.append(int(segment))
            except ValueError:
                parts.append(0)
        return tuple(parts)


# ── Fork strategy generators ──────────────────────────────────────────────


def _fork_skip_latest(
    packages: list[dict],
    target_name: str,
) -> list[dict] | None:
    """Exclude the *latest* version of *target_name* so the solver picks an older one."""
    new_pkgs = copy.deepcopy(packages)
    for pkg in new_pkgs:
        if pkg.get("name") == target_name:
            versions = pkg.get("available_versions", []) or []
            if len(versions) < 2:
                return None
            latest = _get_latest_version(pkg)
            if latest and latest in versions:
                versions.remove(latest)
                pkg["available_versions"] = versions
                break
    return new_pkgs


def _fork_skip_first_two(
    packages: list[dict],
    target_name: str,
) -> list[dict] | None:
    """Exclude the *two* latest versions, forcing resolution further down."""
    new_pkgs = copy.deepcopy(packages)
    for pkg in new_pkgs:
        if pkg.get("name") == target_name:
            versions = list(pkg.get("available_versions", []) or [])
            if len(versions) < 3:
                return None
            s = sorted(versions, key=lambda v: _safe_version_key(v), reverse=True)
            removed = s[:2]
            for r in removed:
                versions.remove(r)
            pkg["available_versions"] = versions
            break
    return new_pkgs


def _fork_major_version_pin(
    packages: list[dict],
    target_name: str,
) -> list[dict] | None:
    """Pin to the *previous* major version line (e.g. 1.x instead of 2.x)."""
    new_pkgs = copy.deepcopy(packages)
    for pkg in new_pkgs:
        if pkg.get("name") == target_name:
            versions = list(pkg.get("available_versions", []) or [])
            s = sorted(versions, key=lambda v: _safe_version_key(v), reverse=True)
            if len(s) < 2:
                return None
            latest = s[0]
            major = latest.split(".")[0] if "." in latest else latest
            # Keep only versions whose major is NOT the latest major
            kept = [v for v in versions if not v.startswith(major + ".") and v != major]
            prerelease = [
                v
                for v in versions
                if not v.startswith(major + ".")
                and v != major
                and any(c in v for c in ("a", "b", "rc", "dev", "post"))
            ]
            if kept and (len(kept) >= 1 or len(prerelease) >= 1):
                pkg["available_versions"] = kept
                break
            return None
    return new_pkgs


def _fork_constraint_relax(
    packages: list[dict],
    target_name: str,
) -> list[dict] | None:
    """Remove the version constraint from *target_name* (set to ``*``)."""
    new_pkgs = copy.deepcopy(packages)
    for pkg in new_pkgs:
        if pkg.get("name") == target_name:
            vc = pkg.get("version_constraint", "*")
            if vc == "*":
                return None
            pkg["version_constraint"] = "*"
            break
    return new_pkgs


_FORK_STRATEGIES = [
    ("skip-latest", _fork_skip_latest),
    ("skip-first-two", _fork_skip_first_two),
    ("major-pin", _fork_major_version_pin),
    ("constraint-relax", _fork_constraint_relax),
]


# ── ForkingResolver ───────────────────────────────────────────────────────


class ForkingResolver:
    """Meta-solver that forks parallel alternative resolution scenarios.

    When the primary solver fails (unsatisfiable / timeout), this resolver:

    1. Identifies the most constraint-heavy packages in the graph.
    2. Creates up to *max_forks* alternative package lists, each targeting
       a different critical package with a different strategy.
    3. Runs all forks in parallel via ``ThreadPoolExecutor``.
    4. Returns the first successful solution.

    If no fork succeeds, the original failure result is returned.

    The fork strategies are:
        - **skip-latest**: Exclude the newest version of a critical package
        - **skip-first-two**: Exclude the two newest versions
        - **major-pin**: Pin to an older major version line
        - **constraint-relax**: Remove the version constraint (set to ``*``)

    Args:
        base_solver: The primary solver instance (ConflicResolver, PubGrubSolver, etc.)
        max_forks: Maximum number of parallel fork trials (default 4).
        fork_timeout_ratio: Fraction of the original solver timeout to give each fork
            (default 0.5).  Each fork gets ``max(solver_timeout * ratio // max_forks, 10s)``.

    """

    def __init__(
        self,
        base_solver: Any,
        max_forks: int = 4,
        fork_timeout_ratio: float = 0.5,
    ) -> None:
        """Initialize the ForkingResolver."""
        self._solver = base_solver
        self._max_forks = max_forks
        self._fork_timeout_ratio = fork_timeout_ratio

    def resolve_dependencies(
        self,
        packages: list[dict],
        system_info: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """Resolve dependencies, forking parallel trials on failure."""
        solver_timeout = kwargs.get("solver_timeout")

        # Phase 1: primary solver
        result = self._solver.resolve_dependencies(packages, system_info, **kwargs)
        status = result.get("status", "")
        if status in ("satisfiable", "satisfiable_with_warnings"):
            return result

        logger.info(
            "ForkingResolver: primary solver failed (%s), creating forks",
            status,
        )

        # Phase 2: create alternative fork scenarios
        forks = self._create_forks(packages, result)
        if not forks:
            logger.info("ForkingResolver: no fork scenarios could be created")
            return result

        # Phase 3: parallel execution
        fork_timeout = self._calc_fork_timeout(solver_timeout)
        fork_result = self._execute_forks(forks, system_info, fork_timeout, **kwargs)
        if fork_result is not None:
            return fork_result

        return result

    # ── internal helpers ──────────────────────────────────────────────────

    def _create_forks(
        self,
        packages: list[dict],
        primary_result: dict,
    ) -> list[tuple[str, list[dict]]]:
        """Build a list of ``(label, forked_packages)`` alternatives."""
        critical = _most_constrained_packages(packages, count=self._max_forks)
        if not critical:
            return []

        forks: list[tuple[str, list[dict]]] = []
        for i, (_score, cpkg) in enumerate(critical):
            pkg_name = cpkg.get("name", "")
            strat_idx = i % len(_FORK_STRATEGIES)
            strat_name, strat_fn = _FORK_STRATEGIES[strat_idx]

            try:
                new_pkgs = strat_fn(packages, pkg_name)
                if new_pkgs is not None:
                    label = f"{strat_name}/{pkg_name}"
                    forks.append((label, new_pkgs))
                    logger.debug("ForkingResolver: created fork '%s'", label)
            except Exception as exc:
                logger.debug(
                    "ForkingResolver: strategy %s failed for %s: %s",
                    strat_name,
                    pkg_name,
                    exc,
                )

        return forks[: self._max_forks]

    def _calc_fork_timeout(self, solver_timeout: int | None) -> int:
        """Calculate per-fork timeout from the original solver timeout."""
        if solver_timeout is None or solver_timeout <= 0:
            return 30000  # default 30s per fork
        per_fork = int(solver_timeout * self._fork_timeout_ratio // max(self._max_forks, 1))
        return max(per_fork, 10000)

    def _execute_forks(
        self,
        forks: list[tuple[str, list[dict]]],
        system_info: dict | None,
        fork_timeout: int,
        **kwargs: Any,
    ) -> dict | None:
        """Execute all fork scenarios in parallel, returning the first valid solution."""
        max_workers = min(len(forks), self._max_forks)

        def _run(label: str, fpkgs: list[dict]) -> dict | None:
            try:
                sub_kwargs = dict(kwargs)
                sub_kwargs["solver_timeout"] = fork_timeout
                res = self._solver.resolve_dependencies(fpkgs, system_info, **sub_kwargs)
                if res.get("status") in ("satisfiable", "satisfiable_with_warnings"):
                    logger.info("ForkingResolver: fork '%s' succeeded", label)
                    res["solver"] = res.get("solver", "") + f"+fork:{label}"
                    return res
            except Exception as exc:
                logger.debug("ForkingResolver: fork '%s' raised %s", label, exc)
            return None

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map = {pool.submit(_run, label, pkgs): label for label, pkgs in forks}
            for future in as_completed(future_map):
                result = future.result()
                if result is not None:
                    # Cancel remaining futures
                    for f in future_map:
                        f.cancel()
                    return result

        return None
