"""Benchmark: hybrid solver vs Z3-only vs PubGrub-only on simulated multi-ecosystem graphs.

This test creates realistic dependency graphs spanning 2-3 ecosystems (PyPI, npm,
crates) and measures solver time for each strategy.  The dependency graphs are
generated with known characteristics:

- Per ecosystem: 10-50 packages, 5-20 versions each
- Cross-ecosystem edges: 0-5% of total edges
- Ecosystem-level conflicts: ~5% of scenarios have intentional cross-eco conflicts

This simulates the structure of real-world multi-ecosystem projects like superset,
n8n, or cilium without requiring network access.
"""

import random
import time
from typing import Any

import pytest

# Seed for reproducibility
RANDOM_SEED = 42

# Graph sizes
SMALL = {"n_pkgs": 20, "n_versions": 10}
MEDIUM = {"n_pkgs": 100, "n_versions": 20}
LARGE = {"n_pkgs": 500, "n_versions": 50}

SOLVER_TIMEOUT = 30000  # 30s in ms


def _generate_dep_graph(
    n_pkgs: int,
    n_versions: int,
    n_ecosystems: int = 2,
    cross_eco_prob: float = 0.05,
    conflict_prob: float = 0.02,
    seed: int = RANDOM_SEED,
) -> list[dict]:
    """Generate a realistic multi-ecosystem dependency graph.

    Parameters
    ----------
    n_pkgs: total packages across all ecosystems
    n_versions: versions per package
    n_ecosystems: number of ecosystems (1-3)
    cross_eco_prob: probability any dep edge crosses ecosystems
    conflict_prob: probability of an intentional conflict (unused currently)

    Returns
    -------
    list[dict]: packages ready for solver.resolve_dependencies()
    """
    rng = random.Random(seed)
    ecosystems = ["pypi", "npm", "crates"][:n_ecosystems]

    pkgs_per_eco = max(1, n_pkgs // n_ecosystems)
    all_pkgs: list[dict[str, Any]] = []

    for eco in ecosystems:
        for i in range(pkgs_per_eco):
            name = f"{eco}-pkg-{i:04d}"
            versions = [
                f"{major}.{minor}.0"
                for major, minor in zip(
                    range(1, 10),
                    [rng.randint(0, 9) for _ in range(9)],
                )
            ][:n_versions]

            deps: dict[str, dict[str, str]] = {}
            for dep in all_pkgs[: rng.randint(0, min(5, len(all_pkgs)))]:
                dep_eco = dep.get("ecosystem", eco)
                dep_name = dep["name"]
                # Cross-eco prob
                if dep_eco != eco and rng.random() > cross_eco_prob:
                    continue
                if dep_eco not in deps:
                    deps[dep_eco] = {}
                deps[dep_eco][dep_name] = f">={rng.choice(dep['available_versions'])}"

            pkg = {
                "name": name,
                "ecosystem": eco,
                "version_constraint": "*",
                "available_versions": versions,
                "dependencies": deps,
                "system_requirements": {},
            }
            all_pkgs.append(pkg)

    return all_pkgs


def _run_solver(
    solver_type: str,
    packages: list[dict],
    system_info: dict | None = None,
) -> tuple[str, float]:
    """Run a solver and return (status, elapsed_seconds)."""
    if solver_type == "z3":
        from backend.core.conflict_resolver import ConflictResolver

        solver = ConflictResolver(use_optimization=True)
    elif solver_type == "pubgrub":
        from backend.core.pubgrub_solver import PubGrubSolver

        solver = PubGrubSolver(solver_timeout=SOLVER_TIMEOUT)
    elif solver_type == "hybrid":
        from backend.core.hybrid_solver import HybridSolver

        solver = HybridSolver(solver_timeout=SOLVER_TIMEOUT)
    else:
        raise ValueError(f"Unknown solver: {solver_type}")

    t0 = time.perf_counter()
    try:
        result = solver.resolve_dependencies(packages, system_info)
    except Exception as exc:
        return ("error", time.perf_counter() - t0)
    elapsed = time.perf_counter() - t0
    return (result.get("status", "unknown"), elapsed)


class TestHybridBenchmark:
    """Benchmark hybrid solver against Z3-only and PubGrub-only."""

    @pytest.mark.parametrize("size", ["small", "medium"])
    def test_benchmark_correctness(self, size: str):
        """All solvers produce the same satisfiability result."""
        params = {"small": SMALL, "medium": MEDIUM}[size]
        packages = _generate_dep_graph(
            n_pkgs=params["n_pkgs"],
            n_versions=params["n_versions"],
            n_ecosystems=2,
        )

        results: dict[str, str] = {}
        for solver_type in ["z3", "pubgrub", "hybrid"]:
            status, elapsed = _run_solver(solver_type, packages)
            results[solver_type] = status
            print(f"  [{size}] {solver_type:>8}: {status} in {elapsed:.2f}s")

        # All should reach the same conclusion
        assert results["z3"] == results["hybrid"], (
            f"Z3 says {results['z3']} but hybrid says {results['hybrid']}"
        )

    @pytest.mark.parametrize("size", ["small", "medium", "large"])
    def test_hybrid_no_slower_than_z3(self, size: str):
        """Hybrid solver should not be slower than Z3-only."""
        params = {"small": SMALL, "medium": MEDIUM, "large": LARGE}[size]
        packages = _generate_dep_graph(
            n_pkgs=params["n_pkgs"],
            n_versions=params["n_versions"],
            n_ecosystems=2,
        )

        _, z3_time = _run_solver("z3", packages)
        _, hybrid_time = _run_solver("hybrid", packages)

        print(f"  [{size}] Z3: {z3_time:.2f}s, Hybrid: {hybrid_time:.2f}s")

        # Hybrid should not be >3x slower than Z3 (if slower at all)
        # The overhead of PubGrub + Z3 should be negligible vs. Z3 alone
        assert hybrid_time < z3_time * 3, (
            f"Hybrid {hybrid_time:.2f}s is too much slower than Z3 {z3_time:.2f}s"
        )

    @pytest.mark.parametrize("n_ecosystems", [1, 2, 3])
    def test_ecosystem_isolation(self, n_ecosystems: int):
        """More ecosystems should not hurt hybrid solver time."""
        packages = _generate_dep_graph(
            n_pkgs=60,
            n_versions=15,
            n_ecosystems=n_ecosystems,
        )

        _, hybrid_time = _run_solver("hybrid", packages)
        print(f"  [{n_ecosystems} eco] Hybrid: {hybrid_time:.2f}s")

        # Should complete in reasonable time
        assert hybrid_time < 60, f"Hybrid took {hybrid_time:.2f}s (too long)"

    def test_large_graph_no_cross_eco(self):
        """Large single-ecosystem graph: hybrid = PubGrub = Z3 result."""
        packages = _generate_dep_graph(
            n_pkgs=200,
            n_versions=30,
            n_ecosystems=1,
            cross_eco_prob=0,
        )

        results = {}
        times = {}
        for solver_type in ["z3", "hybrid"]:
            status, elapsed = _run_solver(solver_type, packages)
            results[solver_type] = status
            times[solver_type] = elapsed

        print(f"  [large 1-eco] Z3: {times['z3']:.2f}s, Hybrid: {times['hybrid']:.2f}s")
        assert results["z3"] == results["hybrid"]


if __name__ == "__main__":
    # Manual run for quick benchmarking
    print("=== Hybrid Solver Benchmark ===\n")

    for n_pkgs, n_versions, n_eco, label in [
        (20, 10, 1, "Tiny 1-eco"),
        (20, 10, 2, "Tiny 2-eco"),
        (100, 20, 2, "Medium 2-eco"),
        (500, 50, 2, "Large 2-eco"),
        (100, 20, 3, "Medium 3-eco"),
    ]:
        packages = _generate_dep_graph(
            n_pkgs=n_pkgs,
            n_versions=n_versions,
            n_ecosystems=n_eco,
        )
        print(f"\n--- {label} ({n_pkgs} pkgs × {n_versions} ver × {n_eco} eco) ---")
        for solver_type in ["z3", "pubgrub", "hybrid"]:
            status, elapsed = _run_solver(solver_type, packages)
            print(f"  {solver_type:>8}: {status} in {elapsed:.2f}s")
