"""Synthetic dependency graph generation for benchmarking and testing.

Provides ``PackageSpec`` and ``MatrixGenerator`` to create reproducible
multi-ecosystem dependency graphs of arbitrary size, depth, and complexity.
"""

from __future__ import annotations

import dataclasses
import random
from typing import Any

_SYNTHETIC_VERSIONS = [
    "1.0.0",
    "1.1.0",
    "1.2.0",
    "2.0.0",
    "2.1.0",
    "2.2.0",
    "2.3.0",
    "2.4.0",
    "2.5.0",
    "2.6.0",
    "2.7.0",
    "2.8.0",
    "2.9.0",
    "3.0.0",
    "3.1.0",
    "3.2.0",
    "3.3.0",
    "4.0.0",
    "4.1.0",
    "4.2.0",
]


@dataclasses.dataclass
class PackageSpec:
    """Specification for a single synthetic package.

    Attributes:
        name: Package name.
        ecosystem: Ecosystem identifier (e.g. ``"pypi"``, ``"npm"``).
        versions: List of version strings available for this package.
        constraint: Version constraint string (e.g. ``">=1.0.0"``).
        deps: Map of ``{ecosystem: {name: constraint}}`` dependencies.

    """

    name: str
    ecosystem: str
    versions: list[str]
    constraint: str = "*"
    deps: dict[str, dict[str, str]] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to the solver's input dict format."""
        return {
            "name": self.name,
            "ecosystem": self.ecosystem,
            "version_constraint": self.constraint,
            "available_versions": self.versions[:],
            "dependencies": self.deps or {},
            "system_requirements": {},
            "cross_ecosystem_deps": [],
        }


class MatrixGenerator:
    """Generates synthetic package graphs for solver benchmarks.

    Usage::

        gen = MatrixGenerator(seed=42)
        pkgs = gen.generate_graph(package_count=50, depth=3, branching=4)
        solver_input = gen.to_resolver_input(pkgs)
        total_versions = gen.count_versions(pkgs)
    """

    def __init__(self, seed: int = 42):
        """Initialize MatrixGenerator with given random seed."""
        self._rng = random.Random(seed)  # noqa: S311 — reproducible non-crypto randomness for test matrix generation

    def generate_package(
        self,
        name: str,
        ecosystem: str,
        version_count: int = 10,
        dep_count: int = 0,
        constraint: str | None = None,
        available_versions: list[str] | None = None,
        all_packages: list[PackageSpec] | None = None,
    ) -> PackageSpec:
        """Generate a single synthetic package.

        Args:
            name: Package name.
            ecosystem: Ecosystem identifier.
            version_count: Number of versions (used when ``available_versions``
                is not provided).
            dep_count: How many existing packages this should depend on.
            constraint: Version constraint (default ``"*"``).
            available_versions: Explicit version list (auto-generated if
                ``None``).
            all_packages: Previously generated packages to draw dependencies
                from.

        Returns:
            A new ``PackageSpec``.

        """
        if available_versions is not None:
            versions = available_versions
        else:
            versions = _SYNTHETIC_VERSIONS[:version_count]

        deps: dict[str, dict[str, str]] = {}
        if dep_count > 0 and all_packages:
            pool = [p for p in all_packages if p.name != name]
            if pool:
                chosen = self._rng.sample(pool, min(dep_count, len(pool)))
                for dep in chosen:
                    if dep.ecosystem not in deps:
                        deps[dep.ecosystem] = {}
                    deps[dep.ecosystem][dep.name] = f">={self._rng.choice(dep.versions)}"

        return PackageSpec(
            name=name,
            ecosystem=ecosystem,
            versions=versions,
            constraint=constraint or "*",
            deps=deps if deps else None,
        )

    def generate_graph(
        self,
        package_count: int = 20,
        depth: int = 3,
        branching: int = 3,
        ecosystems: list[str] | None = None,
        cross_eco_prob: float = 0.05,
    ) -> list[PackageSpec]:
        """Generate a synthetic dependency graph.

        Builds packages level-by-level up to *depth*, with each package
        depending on *branching* packages in the previous level.

        Args:
            package_count: Total number of packages.
            depth: Maximum dependency depth.
            branching: Number of dependencies per package.
            ecosystems: List of ecosystem identifiers (default
                ``["pypi"]``).
            cross_eco_prob: Probability that a dependency crosses
                ecosystems.

        Returns:
            List of ``PackageSpec`` instances forming a DAG.

        """
        if ecosystems is None:
            ecosystems = ["pypi"]
        n_eco = len(ecosystems)

        pkgs: list[PackageSpec] = []
        per_level = max(1, package_count // max(depth, 1))
        created = 0

        for level in range(depth):
            count = min(per_level, package_count - created)
            if count <= 0:
                break
            for i in range(count):
                eco = ecosystems[self._rng.randint(0, n_eco - 1)]
                name = f"{eco}-l{level}-p{i:04d}"
                version_count = self._rng.randint(5, 20)
                dep_count = branching if level > 0 else 0

                spec = self.generate_package(
                    name=name,
                    ecosystem=eco,
                    version_count=version_count,
                    dep_count=dep_count,
                    all_packages=pkgs,
                )
                pkgs.append(spec)
                created += 1

        return pkgs

    @staticmethod
    def to_resolver_input(packages: list[PackageSpec]) -> list[dict[str, Any]]:
        """Convert a list of ``PackageSpec`` to the solver's input format."""
        return [pkg.to_dict() for pkg in packages]

    @staticmethod
    def count_versions(packages: list[PackageSpec]) -> int:
        """Return the total number of version entries across all packages."""
        return sum(len(p.versions) for p in packages)
