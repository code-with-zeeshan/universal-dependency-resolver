"""Cross-solver comparison tests.

Verifies that ConflictResolver (Z3) and PubGrubSolver produce compatible
results on identical inputs — satisfiable/unsatisfiable status, determinism,
and version compatibility.
"""

import pytest

from backend.core.pubgrub_solver import PubGrubSolver

try:
    from backend.core.conflict_resolver import ConflictResolver

    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False


def _make_pkg(name: str, versions: list[str], deps: dict | None = None, eco: str = "pypi") -> dict:
    """Build a package dict in the format both solvers expect."""
    pkg = {
        "name": name,
        "ecosystem": eco,
        "version_constraint": "*",
        "available_versions": versions,
        "dependencies": {},
    }
    if deps:
        pkg["dependencies"] = deps
    return pkg


def _make_simple_graph() -> list[dict]:
    """A depends on B, B has 2 versions."""
    return [
        _make_pkg("A", ["1.0.0", "1.1.0"], deps={"pypi": {"B": ">=1.0.0"}}),
        _make_pkg("B", ["1.0.0", "2.0.0"]),
    ]


def _make_unsatisfiable_graph() -> list[dict]:
    """A >=2.0 and A <1.0 — impossible."""
    return [
        _make_pkg(
            "A", ["0.5.0", "1.0.0", "1.5.0", "2.0.0", "3.0.0"], deps={"pypi": {"B": ">=2.0"}}
        ),
        _make_pkg(
            "B", ["1.0.0", "1.5.0", "2.0.0", "2.5.0", "3.0.0"], deps={"pypi": {"A": ">=2.0,<1.0"}}
        ),
    ]


def _make_independent_graph() -> list[dict]:
    """Two independent packages with no cross-deps."""
    return [
        _make_pkg("X", ["1.0.0", "2.0.0"]),
        _make_pkg("Y", ["3.0.0", "4.0.0"]),
    ]


# ── Solvers ───────────────────────────────────────────────────────────────────


@pytest.fixture
def z3_solver():
    if not HAS_Z3:
        pytest.skip("z3-solver not installed")
    return ConflictResolver(use_optimization=False)


@pytest.fixture
def pubgrub_solver():
    return PubGrubSolver()


# ── Satisfiable cases ─────────────────────────────────────────────────────────


class TestCrossSolverSatisfiable:
    """Both solvers should return satisfiable for valid dependency graphs."""

    def test_both_satisfiable_simple(self, z3_solver, pubgrub_solver):
        packages = _make_simple_graph()
        z3_result = z3_solver.resolve_dependencies(packages)
        pg_result = pubgrub_solver.resolve_dependencies(packages)
        assert z3_result["status"] == "satisfiable"
        assert pg_result["status"] == "satisfiable"

    def test_both_resolve_compatible_versions(self, z3_solver, pubgrub_solver):
        """A and B both resolved, A's constraint on B is satisfied."""
        packages = _make_simple_graph()
        z3_result = z3_solver.resolve_dependencies(packages)
        pg_result = pubgrub_solver.resolve_dependencies(packages)

        for name in ("A", "B"):
            assert name in z3_result["resolved_packages"]
            assert name in pg_result["resolved_packages"]

        # A depends on B >=1.0.0 — both resolved B to a version >= 1.0.0
        for result in (z3_result, pg_result):
            b_ver = result["resolved_packages"]["B"]["version"]
            assert b_ver.startswith(("1.", "2."))

    def test_both_independent_resolve(self, z3_solver, pubgrub_solver):
        """Independent packages with no cross-deps should resolve."""
        packages = _make_independent_graph()
        z3_result = z3_solver.resolve_dependencies(packages)
        pg_result = pubgrub_solver.resolve_dependencies(packages)
        assert z3_result["status"] == "satisfiable"
        assert pg_result["status"] == "satisfiable"
        for name in ("X", "Y"):
            assert name in z3_result["resolved_packages"]
            assert name in pg_result["resolved_packages"]


# ── Unsatisfiable cases ───────────────────────────────────────────────────────


class TestCrossSolverUnsatisfiable:
    """Both solvers should detect unsatisfiable constraints."""

    def test_both_unsatisfiable(self, z3_solver, pubgrub_solver):
        packages = _make_unsatisfiable_graph()
        z3_result = z3_solver.resolve_dependencies(packages)
        pg_result = pubgrub_solver.resolve_dependencies(packages)
        assert z3_result["status"] == "unsatisfiable"
        assert pg_result["status"] == "unsatisfiable"

    def test_no_versions_satisfy_constraint(self, z3_solver, pubgrub_solver):
        """A single package with impossible constraint."""
        packages = [
            _make_pkg("A", ["1.0.0"], deps={"pypi": {"B": ">=2.0"}}),
            _make_pkg("B", ["1.0.0"]),
        ]
        z3_result = z3_solver.resolve_dependencies(packages)
        pg_result = pubgrub_solver.resolve_dependencies(packages)
        assert z3_result["status"] == "unsatisfiable"
        assert pg_result["status"] == "unsatisfiable"


# ── Determinism ───────────────────────────────────────────────────────────────


class TestCrossSolverDeterminism:
    """Running the same solver twice on the same input must give the same result."""

    def test_z3_deterministic(self, z3_solver):
        packages = _make_simple_graph()
        r1 = z3_solver.resolve_dependencies(packages)
        r2 = z3_solver.resolve_dependencies(packages)
        assert r1["status"] == r2["status"]
        if r1["status"] == "satisfiable":
            for name in r1["resolved_packages"]:
                assert (
                    r2["resolved_packages"].get(name, {}).get("version")
                    == r1["resolved_packages"][name]["version"]
                )

    def test_pubgrub_deterministic(self, pubgrub_solver):
        packages = _make_independent_graph()
        r1 = pubgrub_solver.resolve_dependencies(packages)
        r2 = pubgrub_solver.resolve_dependencies(packages)
        assert r1["status"] == r2["status"]
        if r1["status"] == "satisfiable":
            for name in r1["resolved_packages"]:
                assert (
                    r2["resolved_packages"].get(name, {}).get("version")
                    == r1["resolved_packages"][name]["version"]
                )

    def test_pubgrub_deterministic_larger(self, pubgrub_solver):
        """Determinism holds for the simple graph too."""
        packages = _make_simple_graph()
        r1 = pubgrub_solver.resolve_dependencies(packages)
        r2 = pubgrub_solver.resolve_dependencies(packages)
        assert r1["status"] == r2["status"]
        if r1["status"] == "satisfiable":
            for name in r1["resolved_packages"]:
                assert (
                    r2["resolved_packages"].get(name, {}).get("version")
                    == r1["resolved_packages"][name]["version"]
                )


# ── Single-solver smoke tests (no z3 dependency) ──────────────────────────────


class TestPubGrubSolo:
    """PubGrub-only tests that don't require z3."""

    def test_single_package_resolves(self, pubgrub_solver):
        packages = [_make_pkg("A", ["1.0.0", "2.0.0"])]
        result = pubgrub_solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert "A" in result["resolved_packages"]

    def test_empty_packages(self, pubgrub_solver):
        result = pubgrub_solver.resolve_dependencies([])
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"] == {}

    def test_no_versions(self, pubgrub_solver):
        packages = [_make_pkg("A", [])]
        result = pubgrub_solver.resolve_dependencies(packages)
        assert result["status"] == "unsatisfiable"

    def test_diamond_dependency(self, pubgrub_solver):
        """A -> B, C; B and C both depend on D with compatible constraints."""
        packages = [
            _make_pkg("A", ["1.0.0"], deps={"pypi": {"B": ">=1.0", "C": ">=1.0"}}),
            _make_pkg("B", ["1.0.0", "2.0.0"], deps={"pypi": {"D": ">=1.0,<3.0"}}),
            _make_pkg("C", ["1.0.0", "2.0.0"], deps={"pypi": {"D": ">=2.0,<4.0"}}),
            _make_pkg("D", ["1.0.0", "2.0.0", "3.0.0"]),
        ]
        result = pubgrub_solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        for name in ("A", "B", "C", "D"):
            assert name in result["resolved_packages"]


# ── Z3-side behavior (dedicated unit coverage for the 4x-touched areas) ───────


class TestZ3PrereleaseHandling:
    """Z3 path must never pick a prerelease over a stable release, and must
    prefer stable-only upgrades in _upgrade_to_latest (parity with BUG 1
    fixes that previously only had PubGrub-side tests)."""

    def test_prerelease_not_selected_over_stable(self, z3_solver):
        packages = [
            {
                "name": "django",
                "ecosystem": "pypi",
                "version_constraint": ">=4.0",
                "available_versions": ["4.2.0", "5.0.0", "5.1.0rc1", "5.1.0"],
                "dependencies": {},
            }
        ]
        result = z3_solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        version = result["resolved_packages"]["django"]["version"]
        assert version == "5.1.0"
        assert version != "5.1.0rc1"

    def test_prerelease_allowed_when_only_match(self, z3_solver):
        packages = [
            {
                "name": "mypkg",
                "ecosystem": "pypi",
                "version_constraint": ">=2.0b1",
                "available_versions": ["1.9.0", "2.0b1"],
                "dependencies": {},
            }
        ]
        result = z3_solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"]["mypkg"]["version"] in ("2.0b1", "2.0.0b1")

    def test_upgrade_to_latest_keeps_constraints(self, z3_solver):
        """_upgrade_to_latest must not violate a dependency constraint
        (regression for the flaky _upgrade_to_latest prerelease bug)."""
        packages = [
            _make_pkg("A", ["1.0.0", "2.0.0"], deps={"pypi": {"B": ">=1.0,<3.0"}}),
            _make_pkg("B", ["1.0.0", "2.0.0", "3.0.0", "4.0.0"]),
        ]
        result = z3_solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        b_ver = result["resolved_packages"]["B"]["version"]
        assert b_ver.startswith(("1.", "2."))

    def test_bare_version_constraint_is_exact(self, z3_solver):
        """bare '0.20.0' must behave as ==0.20.0, never as >=0.20,<0.21
        (the bare-version SpecifierSet wrapping fix)."""
        packages = [
            {
                "name": "app",
                "ecosystem": "pypi",
                "version_constraint": "0.20.0",
                "available_versions": ["0.19.0", "0.20.0", "0.21.0"],
                "dependencies": {},
            }
        ]
        result = z3_solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"]["app"]["version"] == "0.20.0"


class TestZ3UpgradeToLatest:
    """Direct coverage of _upgrade_to_latest post-processing on fixture-level
    inputs: with optimization disabled, the SAT pick may be arbitrary, so the
    upgrade pass must raise it to the newest feasible version."""

    def test_upgrade_reaches_newest_stable(self, z3_solver):
        packages = [_make_pkg("A", ["1.0.0", "1.2.0", "2.0.0"])]
        result = z3_solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"]["A"]["version"] == "2.0.0"

    def test_upgrade_skips_prerelease(self, z3_solver):
        packages = [_make_pkg("A", ["1.0.0", "2.0.0", "3.0.0rc1"])]
        result = z3_solver.resolve_dependencies(packages)
        assert result["status"] == "satisfiable"
        assert result["resolved_packages"]["A"]["version"] == "2.0.0"


# ── Solver-parity harness (Z3 vs PubGrub on identical inputs) ─────────────────


class TestSolverParity:
    """Both backends must agree on status, name-set and resolved versions for
    identical inputs — a permanent guard against backend drift."""

    PARITY_GRAPHS = {
        "simple": lambda: _make_simple_graph(),
        "independent": lambda: _make_independent_graph(),
        "diamond": lambda: [
            _make_pkg("A", ["1.0.0"], deps={"pypi": {"B": ">=1.0", "C": ">=1.0"}}),
            _make_pkg("B", ["1.0.0", "2.0.0"], deps={"pypi": {"D": ">=1.0,<3.0"}}),
            _make_pkg("C", ["1.0.0", "2.0.0"], deps={"pypi": {"D": ">=2.0,<4.0"}}),
            _make_pkg("D", ["1.0.0", "2.0.0", "3.0.0"]),
        ],
        "prerelease": lambda: [
            _make_pkg("A", ["1.0.0", "2.0.0"], deps={"pypi": {"B": ">=1.0"}}),
            _make_pkg("B", ["1.0.0", "2.0.0", "3.0.0rc1"]),
        ],
        "transitive_chain": lambda: [
            _make_pkg("A", ["1.0.0"], deps={"pypi": {"B": ">=1.0"}}),
            _make_pkg("B", ["1.0.0", "1.5.0"], deps={"pypi": {"C": ">=0.5"}}),
            _make_pkg("C", ["0.5.0", "1.0.0", "1.5.0"]),
        ],
    }

    @pytest.mark.parametrize("graph_name", list(PARITY_GRAPHS))
    def test_parity_identical(self, z3_solver, pubgrub_solver, graph_name):
        packages = self.PARITY_GRAPHS[graph_name]()
        z3_result = z3_solver.resolve_dependencies(packages)
        pg_result = pubgrub_solver.resolve_dependencies(packages)

        # 1. status must agree
        assert z3_result["status"] == pg_result["status"], (
            f"{graph_name}: Z3={z3_result['status']} PubGrub={pg_result['status']}"
        )
        if z3_result["status"] != "satisfiable":
            return

        # 2. name-set must agree
        z3_names = set(z3_result["resolved_packages"])
        pg_names = set(pg_result["resolved_packages"])
        assert z3_names == pg_names, f"{graph_name}: names differ"

        # 3. for fully-stable graphs, exact versions must agree
        for name in z3_names:
            z3v = z3_result["resolved_packages"][name]["version"]
            pgv = pg_result["resolved_packages"][name]["version"]
            if graph_name != "prerelease":
                assert z3v == pgv, f"{graph_name}.{name}: Z3={z3v} PubGrub={pgv}"
            else:
                # version may be expressed with different prerelease spellings
                assert z3v.split("rc")[0] == pgv.split("rc")[0]
