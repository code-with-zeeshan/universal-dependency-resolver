"""Reproduce the superset-scale regression: ~200 packages, PubGrub solver."""

from itertools import chain

import pytest

from backend.core.pubgrub_solver import PubGrubSolver


def _gen_superset_like_packages(count: int = 200) -> list[dict]:
    """Generate a synthetic monorepo resembling apache/superset's dependency graph.

    Creates ``count`` packages in a layered dependency structure:
    - 10% root packages (no dependents, vary independently)
    - 40% mid-layer packages (depend on 1-3 root packages)
    - 50% leaf packages (depend on 1-2 mid-layer packages)

    Each package has 3-5 available versions and realistic Python-style
    constraints (``>=X.Y.Z,<W`` or ``~=X.Y``).
    """
    assert count >= 20
    n_root = max(2, count // 10)
    n_mid = max(8, count * 4 // 10)
    n_leaf = count - n_root - n_mid

    root_indexes = list(range(n_root))
    mid_indexes = list(range(n_root, n_root + n_mid))
    leaf_indexes = list(range(n_root + n_mid, n_root + n_mid + n_leaf))

    packages: list[dict] = []

    def _versions(base: int) -> list[str]:
        return [f"{base}.0.0", f"{base}.1.0", f"{base}.2.0", f"{base}.3.0", f"{base}.5.0"]

    def _constraint_for(dep_idx: int) -> str:
        base = dep_idx + 1
        # Alternate between >= and ~= style constraints
        if dep_idx % 3 == 0:
            return f">={base}.0.0,<{base + 1}.0.0"
        if dep_idx % 3 == 1:
            return f">={base}.0.0"
        return f"~={base}.0"

    # Root packages: no dependencies
    for i in root_indexes:
        name = f"pkg_root_{i}"
        packages.append(
            {
                "name": name,
                "ecosystem": "pypi",
                "available_versions": _versions(i + 1),
                "dependencies": {},
                "version_constraint": ">=0.0.0",
            }
        )

    # Mid-layer packages: depend on small random subset of root packages
    import random

    rng = random.Random(42)
    for i in mid_indexes:
        name = f"pkg_mid_{i}"
        n_deps = rng.randint(1, min(3, n_root))
        dep_idxs = rng.sample(root_indexes, n_deps)
        deps_list = [
            {"name": f"pkg_root_{d}", "version": _constraint_for(d), "ecosystem": "pypi"}
            for d in dep_idxs
        ]
        packages.append(
            {
                "name": name,
                "ecosystem": "pypi",
                "available_versions": _versions(i + 1),
                "dependencies": {"pypi": deps_list},
                "version_constraint": ">=0.0.0",
            }
        )

    # Leaf packages: depend on 1-2 mid-layer packages
    for i in leaf_indexes:
        name = f"pkg_leaf_{i}"
        n_deps = rng.randint(1, 2)
        dep_idxs = rng.sample(mid_indexes, min(n_deps, len(mid_indexes)))
        deps_list = [
            {"name": f"pkg_mid_{d}", "version": _constraint_for(d), "ecosystem": "pypi"}
            for d in dep_idxs
        ]
        packages.append(
            {
                "name": name,
                "ecosystem": "pypi",
                "available_versions": _versions(i + 1),
                "dependencies": {"pypi": deps_list},
                "version_constraint": ">=0.0.0",
            }
        )

    return packages


class TestSupersetScale:
    """PubGrub resolution at superset-like scale (monorepo with ~200 packages)."""

    @pytest.mark.parametrize("n_pkgs", [50, 100, 200])
    def test_pubgrub_resolves_large_monorepo(self, n_pkgs: int):
        pubgrub = PubGrubSolver()
        packages = _gen_superset_like_packages(count=n_pkgs)
        result = pubgrub.resolve_dependencies(packages)
        assert result["status"] == "satisfiable", (
            f"Failed at {n_pkgs} packages: {result.get('resolution_error', 'unknown')}"
        )
        assert len(result["resolved_packages"]) == n_pkgs, (
            f"Expected {n_pkgs} resolved, got {len(result['resolved_packages'])}"
        )

    def test_pubgrub_200_deep_diamond(self):
        """Deep dependency diamond: A → B1..B50 → C1..C100 → D1..D50 → E."""
        pubgrub = PubGrubSolver()
        packages = []
        # A (root)
        packages.append(
            {
                "name": "A",
                "ecosystem": "pypi",
                "available_versions": ["1.0.0", "1.1.0"],
                "dependencies": {
                    "pypi": [
                        {"name": f"B{i}", "version": ">=1.0.0", "ecosystem": "pypi"}
                        for i in range(50)
                    ]
                },
                "version_constraint": ">=1.0.0",
            }
        )
        # B1..B50
        for i in range(50):
            packages.append(
                {
                    "name": f"B{i}",
                    "ecosystem": "pypi",
                    "available_versions": ["1.0.0", "1.1.0", "1.2.0"],
                    "dependencies": {
                        "pypi": [
                            {"name": f"C{j}", "version": ">=1.0.0", "ecosystem": "pypi"}
                            for j in range(i * 2, i * 2 + 2)
                        ]
                    },
                    "version_constraint": ">=1.0.0",
                }
            )
        # C0..C99
        for i in range(100):
            packages.append(
                {
                    "name": f"C{i}",
                    "ecosystem": "pypi",
                    "available_versions": ["1.0.0", "1.1.0"],
                    "dependencies": {
                        "pypi": [
                            {"name": f"D{j}", "version": ">=1.0.0", "ecosystem": "pypi"}
                            for j in range(i % 50, i % 50 + 2)
                        ]
                    },
                    "version_constraint": ">=1.0.0",
                }
            )
        # D0..D51
        for i in range(52):
            packages.append(
                {
                    "name": f"D{i}",
                    "ecosystem": "pypi",
                    "available_versions": ["1.0.0", "1.1.0", "1.2.0", "1.3.0"],
                    "dependencies": {
                        "pypi": [{"name": "E", "version": ">=1.0.0,<3.0.0", "ecosystem": "pypi"}]
                    },
                    "version_constraint": ">=1.0.0",
                }
            )
        # E (shared leaf)
        packages.append(
            {
                "name": "E",
                "ecosystem": "pypi",
                "available_versions": ["1.0.0", "1.5.0", "2.0.0", "2.5.0"],
                "dependencies": {},
                "version_constraint": ">=1.0.0",
            }
        )

        total = 1 + 50 + 100 + 52 + 1  # 204
        result = pubgrub.resolve_dependencies(packages)
        assert result["status"] == "satisfiable", (
            f"Deep diamond failed: {result.get('resolution_error', 'unknown')}"
        )
        assert len(result["resolved_packages"]) == total, (
            f"Expected {total} resolved, got {len(result['resolved_packages'])}"
        )

    def test_pubgrub_stress_chain(self):
        """500-package linear chain: P0 → P1 → ... → P499."""
        pubgrub = PubGrubSolver()
        packages = []
        for i in range(500):
            deps = (
                {"pypi": [{"name": f"P{i + 1}", "version": ">=1.0.0", "ecosystem": "pypi"}]}
                if i < 499
                else {}
            )
            packages.append(
                {
                    "name": f"P{i}",
                    "ecosystem": "pypi",
                    "available_versions": ["1.0.0", "1.1.0", "1.2.0"],
                    "dependencies": deps,
                    "version_constraint": ">=1.0.0",
                }
            )
        result = pubgrub.resolve_dependencies(packages)
        assert result["status"] == "satisfiable", (
            f"Chain of 500 failed: {result.get('resolution_error', 'unknown')}"
        )
        assert len(result["resolved_packages"]) == 500
