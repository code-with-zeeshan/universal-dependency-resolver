"""Pure-Python PubGrub solver — no Rust required.

Implements the PubGrub algorithm (Natalie Weizenbaum's CDCL-based dependency
resolver) as a drop-in for the ``PubGrubSolver`` class.

Reference: https://github.com/dart-lang/pub/blob/master/doc/solver.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

logger = logging.getLogger(__name__)


# ─── Data structures ────────────────────────────────────────────────────────


@dataclass
class Term:
    """A statement about a package version.

    ``package`` must satisfy ``constraint`` when ``positive`` is True,
    and must NOT satisfy it when False.
    """

    package: str
    constraint: str  # PEP 440 specifier like ">=1.0,<2.0" or "==1.2.3"
    positive: bool = True

    def __repr__(self) -> str:
        sign = "" if self.positive else "not "
        return f"{sign}{self.package} {self.constraint}"

    def satisfies(self, other: Term) -> bool:
        """Check if this term satisfies *other*."""
        if self.package != other.package:
            return True
        if self.positive and other.positive:
            return _implied_by(other.constraint, self.constraint)
        if not self.positive and not other.positive:
            return _implied_by(self.constraint, other.constraint)
        if self.positive and not other.positive:
            return not _overlaps(self.constraint, other.constraint)
        return False

    def contradicts(self, other: Term) -> bool:
        """Check if this term contradicts *other* (can't both be true)."""
        if self.package != other.package:
            return False
        if self.positive and other.positive:
            return not _overlaps(self.constraint, other.constraint)
        if not self.positive and not other.positive:
            return False
        if self.positive and not other.positive:
            return _implied_by(other.constraint, self.constraint)
        if not self.positive and other.positive:
            return _implied_by(other.constraint, self.constraint)
        return False

    def intersect(self, other: Term) -> Term | None:
        """Intersect two terms for the same package."""
        if self.package != other.package:
            return None
        if self.positive and other.positive:
            c = _intersect(self.constraint, other.constraint)
            return Term(self.package, c, True) if c else None
        if not self.positive and not other.positive:
            c = _union(self.constraint, other.constraint)
            return Term(self.package, c, False) if c else None
        positive_term = self if self.positive else other
        negative_term = other if self.positive else self
        c = _difference(positive_term.constraint, negative_term.constraint)
        return Term(positive_term.package, c, True) if c else None

    def inverse(self) -> Term:
        """Return the term that contradicts this one."""
        return Term(self.package, self.constraint, not self.positive)


@dataclass
class Incompatibility:
    """A set of terms that cannot all be true simultaneously.

    Like a clause in SAT — at most ``len(terms) - 1`` can be true.
    """

    terms: list[Term]
    cause: Incompatibility | None = None  # For conflict tracking

    def __repr__(self) -> str:
        return f"Incompatibility({self.terms})"


@dataclass
class Assignment:
    """An assignment in the partial solution."""

    term: Term
    decision_level: int
    cause: Incompatibility | None = None  # None for decisions, set for derivations


@dataclass
class PartialSolution:
    """The current partial solution — a sequence of assignments."""

    assignments: list[Assignment] = field(default_factory=list)
    _decision_level: int = 0

    @property
    def decision_level(self) -> int:
        return self._decision_level

    def decide(self, package: str, version: str) -> None:
        """Add a decision assignment (we chose a version)."""
        self._decision_level += 1
        term = Term(package, f"=={version}", positive=True)
        self.assignments.append(Assignment(term, self._decision_level, None))

    def derive(self, term: Term, cause: Incompatibility) -> None:
        """Add a derived assignment (inferred from an incompatibility)."""
        self.assignments.append(Assignment(term, self._decision_level, cause))

    def backtrack(self, to_level: int) -> None:
        """Remove all assignments after *to_level*."""
        while self.assignments and self.assignments[-1].decision_level > to_level:
            self.assignments.pop()
        self._decision_level = to_level

    def _inconsistent_pkg(self) -> str | None:
        """Return a package with conflicting positive assignments, or None."""
        pos_by_pkg: dict[str, list[Term]] = {}
        for a in self.assignments:
            if a.term.positive:
                pos_by_pkg.setdefault(a.term.package, []).append(a.term)
        for pkg, terms in pos_by_pkg.items():
            if len(terms) > 1:
                combined = terms[0]
                for t in terms[1:]:
                    combined = combined.intersect(t)
                    if combined is None:
                        return pkg
        return None

    def _satisfier_entry(self, package: str) -> Assignment | None:
        """Find the assignment that satisfies *package* (if any)."""
        for a in reversed(self.assignments):
            if a.term.package == package and a.term.positive:
                return a
        return None

    def satisfies(self, term: Term) -> bool | None:
        """Check how the current solution relates to *term*.

        Returns True if satisfied, False if contradicted, None if unknown.
        Multiple assignments for the same package are intersected:
        the combined assignment is the intersection of all individual
        assignment terms.
        """
        pkg_terms: list[Term] = []
        for a in self.assignments:
            if a.term.package == term.package:
                pkg_terms.append(a.term)

        if not pkg_terms:
            return None

        combined_pos: Term | None = None
        for t in pkg_terms:
            if t.positive:
                if combined_pos is None:
                    combined_pos = t
                else:
                    combined_pos = combined_pos.intersect(t)
                    if combined_pos is None:
                        break

        if combined_pos is not None:
            if combined_pos.satisfies(term):
                return all(not (not t.positive and t.contradicts(term)) for t in pkg_terms)
            if combined_pos.contradicts(term):
                return False

        # Inconsistent or no combined positive — check each term individually
        any_satisfies = False
        for t in pkg_terms:
            if t.positive:
                if t.satisfies(term):
                    any_satisfies = True
                elif t.contradicts(term):
                    return False
            else:
                if t.satisfies(term):
                    return False
                if t.contradicts(term):
                    any_satisfies = True

        if any_satisfies:
            return True
        return None

    def relation(self, incompatibility: Incompatibility) -> str:
        """Return the relation between this solution and an incompatibility.

        Returns:
          "satisfied"   — all terms are satisfied
          "conflict"    — all terms satisfied except exactly one which is unknown
                          (unit propagation can fire on the unknown term)
          "unknown"     — otherwise (multiple unknown or any contradicted)
        """
        satisfied_count = 0
        unknown_count = 0
        for term in incompatibility.terms:
            rel = self.satisfies(term)
            if rel is True:
                satisfied_count += 1
            elif rel is None:
                unknown_count += 1
            else:
                return "unknown"
        total = len(incompatibility.terms)
        if satisfied_count == total:
            return "satisfied"
        if satisfied_count == total - 1 and unknown_count == 1:
            return "conflict"
        return "unknown"


# ─── Core solver ────────────────────────────────────────────────────────────


class PubGrubCoreSolver:
    """Pure-Python PubGrub algorithm implementation."""

    def __init__(self) -> None:
        self._packages: dict[str, dict[str, dict[str, str]]] = {}
        self._incompatibilities: list[Incompatibility] = []

    def add_package(
        self,
        name: str,
        version: str,
        deps: dict[str, str],
    ) -> None:
        """Register a package version and its dependencies."""
        if name not in self._packages:
            self._packages[name] = {}
        self._packages[name][version] = deps
        version_term = Term(name, f"=={version}", positive=True)
        dep_terms = [Term(dep_name, dep_con, positive=False) for dep_name, dep_con in deps.items()]
        if dep_terms:
            self._incompatibilities.append(Incompatibility([version_term, *dep_terms]))

    def resolve(self, requirements: dict[str, str]) -> dict[str, str]:
        """Resolve *requirements* {name: constraint} to {name: version}.

        Returns dict of resolved versions, or raises ``ResolutionError``.
        """
        solution = PartialSolution()

        # Store root requirements separately — they're NOT conflict-detection
        # targets; they're only used to check solution completeness.
        self._root_requirements: list[Term] = [
            Term(pkg_name, constraint, positive=True)
            for pkg_name, constraint in requirements.items()
        ]

        while True:
            # Unit propagation loop
            while True:
                conflict = self._find_conflict(solution)
                if conflict is None:
                    break

                rel = solution.relation(conflict)
                if rel == "conflict":
                    # Almost-satisfied — unit propagation: derive the missing term
                    for term in conflict.terms:
                        if solution.satisfies(term) is None:
                            solution.derive(term.inverse(), conflict)
                            break
                    else:
                        raise ResolutionError("Unit propagation failed")
                    continue

                # All terms satisfied — real conflict, need to resolve
                cause = self._resolve_conflict(conflict, solution)
                if cause is None:
                    raise ResolutionError("Unsatisfiable")
                solution.backtrack(cause[1])

            # Check if all root requirements are satisfied
            all_satisfied = True
            for term in self._root_requirements:
                if solution.satisfies(term) is not True:
                    all_satisfied = False
                    break
            if all_satisfied:
                break

            # Check for inconsistent positive assignments per package
            inc_pkg = solution._inconsistent_pkg()
            if inc_pkg is not None:
                # Backtrack to before the inconsistency
                earliest = min(
                    a.decision_level for a in solution.assignments if a.term.package == inc_pkg
                )
                solution.backtrack(earliest - 1 if earliest > 0 else 0)

            # Decision making: pick an unsatisfied package
            pkg_to_decide = self._pick_package(solution)
            if pkg_to_decide is None:
                break

            version = self._pick_version(pkg_to_decide, solution)
            if version is None:
                conflict = self._build_conflict_for_missing_version(pkg_to_decide, solution)
                cause = self._resolve_conflict(conflict, solution)
                if cause is None:
                    raise ResolutionError("Unsatisfiable")
                solution.backtrack(cause[1])
                continue

            solution.decide(pkg_to_decide, version)

        # Build result — exact decisions first
        result: dict[str, str] = {}
        for a in solution.assignments:
            if a.term.positive and a.term.constraint.startswith("=="):
                ver = a.term.constraint.lstrip("= ")
                if ver and ver != "*" and a.term.package not in result:
                    result[a.term.package] = ver
        # Fill range-only packages with their best version
        for pkg_name, versions in self._packages.items():
            if pkg_name not in result:
                best = None
                for ver in sorted(versions.keys(), key=lambda v: _safe_version(v), reverse=True):
                    t = Term(pkg_name, f"=={ver}", positive=True)
                    if solution.satisfies(t) is not False:
                        best = ver
                        break
                if best is not None:
                    result[pkg_name] = best

        return result

    def _find_conflict(self, solution: PartialSolution) -> Incompatibility | None:
        """Find the first incompatibility that is satisfied or almost-satisfied.

        Returns "satisfied" incompatibilities first (real conflicts),
        then falls back to "conflict" (almost-satisfied, for unit propagation).

        Single-term incompatibilities (root requirements) never trigger
        unit propagation — they are only checked for completion.
        """
        satisfied = None
        for incomp in self._incompatibilities:
            rel = solution.relation(incomp)
            if rel == "satisfied":
                return incomp
            if rel == "conflict" and len(incomp.terms) >= 2 and satisfied is None:
                satisfied = incomp
        return satisfied

    def _resolve_conflict(
        self,
        conflict: Incompatibility,
        solution: PartialSolution,
    ) -> tuple[Incompatibility, int] | None:
        """Resolve a conflict, returning (new_incompatibility, backtrack_level).

        Returns None if the conflict is at level 0 (root cause — unsatisfiable).
        """
        current = conflict
        level = solution.decision_level
        while level > 0:
            # Find the last assignment involved in the conflict
            terms_by_pkg: dict[str, Term] = {}
            for term in current.terms:
                if term.package not in terms_by_pkg:
                    terms_by_pkg[term.package] = term

            last_assignment = None
            last_pkg = None
            for a in reversed(solution.assignments):
                if a.term.package in terms_by_pkg:
                    last_assignment = a
                    last_pkg = a.term.package
                    break

            if last_assignment is None:
                return None

            if last_pkg is not None and last_assignment is not None:
                terms = [t for p, t in terms_by_pkg.items() if p != last_pkg]
                if last_assignment.cause:
                    cause_terms = list(last_assignment.cause.terms)
                else:
                    cause_terms = [last_assignment.term.inverse()]

                new_terms = terms + cause_terms
                new_incomp = Incompatibility(new_terms, cause=current)
                self._incompatibilities.append(new_incomp)

                current = new_incomp
                level = last_assignment.decision_level - 1

        if level == 0:
            return None

        return (current, level)

    def _pick_package(self, solution: PartialSolution) -> str | None:
        """Pick an unsatisfied package to decide next."""
        # First check root requirements
        for term in self._root_requirements:
            if solution.satisfies(term) is not True:
                return term.package
        # Check packages that need concrete version decisions
        for pkg_name in self._packages:
            has_exact_decision = any(
                a.term.package == pkg_name
                and a.term.positive
                and a.term.constraint.startswith("==")
                for a in solution.assignments
            )
            if not has_exact_decision:
                return pkg_name
        return None

    def _pick_version(self, package: str, solution: PartialSolution) -> str | None:
        """Pick the best version of *package* consistent with current solution."""
        versions = sorted(
            self._packages.get(package, {}).keys(),
            key=lambda v: _safe_version(v),
            reverse=True,
        )
        # Gather existing positive terms for this package
        pos_terms = [
            a.term for a in solution.assignments if a.term.package == package and a.term.positive
        ]
        for ver in versions:
            ver_term = Term(package, f"=={ver}", positive=True)
            # Skip if candidate contradicts existing positive assignments
            conflicting = False
            for pt in pos_terms:
                if pt.intersect(ver_term) is None:
                    conflicting = True
                    break
            if conflicting:
                continue
            # Check no incompatibility becomes fully satisfied
            compatible = True
            for incomp in self._incompatibilities:
                if any(t.package == package for t in incomp.terms):
                    rel = solution.relation(incomp)
                    if rel == "satisfied":
                        compatible = False
                        break
            if compatible:
                return ver
        return None

    def _build_conflict_for_missing_version(
        self, package: str, solution: PartialSolution
    ) -> Incompatibility:
        """Build an incompatibility saying *package* has no valid versions."""
        term = Term(package, "<0.0.0", positive=True)
        return Incompatibility([term])


class ResolutionError(Exception):
    """Raised when PubGrub resolution fails."""


# ─── Constraint helpers ─────────────────────────────────────────────────────


def _safe_version(v: str) -> tuple:
    """Parse a version string into a sortable tuple."""
    try:
        parsed = Version(v)
        return parsed._key
    except InvalidVersion:
        parts = v.split(".")
        nums = []
        for p in parts:
            try:
                nums.append(int(p))
            except ValueError:
                nums.append(0)
        while len(nums) < 3:
            nums.append(0)
        return tuple(nums)


def _version_in_range(ver: str, constraint: str) -> bool:
    """Check if a version satisfies a PEP 440 constraint."""
    if constraint == "*" or not constraint:
        return True
    try:
        return SpecifierSet(constraint).contains(ver)
    except Exception:
        return False


def _overlaps(c1: str, c2: str) -> bool:
    """Check if two constraints share any common version.

    Uses SpecifierSet.contains() with representative test versions since
    packaging>=24.0 removed SpecifierSet.issubset.
    """
    try:
        s1 = SpecifierSet(c1) if c1 and c1 != "*" else SpecifierSet(">=0.0.0")
        s2 = SpecifierSet(c2) if c2 and c2 != "*" else SpecifierSet(">=0.0.0")
        return bool(_intersect_str(str(s1), str(s2)))
    except Exception:
        return c1 == c2 or c1 == "*" or c2 == "*"


def _implied_by(c1: str, c2: str) -> bool:
    """Check if constraint *c2* ⊆ *c1* (all versions in c2 are also in c1).

    Uses SpecifierSet.contains() with representative versions:
    - For == constraints: check that exact version is in c1
    - For other constraints: check edge versions
    """
    try:
        return _implied_by_simple(c1, c2)
    except Exception:
        return c1 == c2 or c2 == "*"


def _implied_by_simple(c1: str, c2: str) -> bool:
    """Check implication using representative version tests."""
    s1 = SpecifierSet(c1) if c1 and c1 != "*" else SpecifierSet(">=0.0.0")
    s2 = SpecifierSet(c2) if c2 and c2 != "*" else SpecifierSet(">=0.0.0")

    # Extract test versions from c2 and filter to only versions c2 allows
    test_versions = _extract_test_versions(c2)
    test_versions = [v for v in test_versions if s2.contains(v)]
    if not test_versions:
        return False

    return all(s1.contains(v) for v in test_versions)


def _extract_test_versions(constraint: str) -> list[str]:
    """Extract representative versions to test a constraint."""
    parts = constraint.split(",")
    versions: list[str] = []
    for p in parts:
        p = p.strip()
        if p.startswith("=="):
            versions.append(p[2:].strip())
        elif p.startswith(">="):
            v = p[2:].strip()
            versions.append(v)
            versions.append(_bump_version(v, 0, 0, 1))
        elif p.startswith(">"):
            v = p[1:].strip()
            versions.append(_bump_version(v, 0, 0, 1))
        elif p.startswith("<="):
            v = p[2:].strip()
            versions.append(v)
        elif p.startswith("<"):
            v = p[1:].strip()
            versions.append(_bump_version(v, 0, 0, -1))
        elif p.startswith("~="):
            v = p[2:].strip()
            versions.append(v)
            parts_v = v.split(".")
            if len(parts_v) >= 2:
                next_minor = int(parts_v[1]) + 1
                versions.append(f"{parts_v[0]}.{next_minor}.0")
    return versions


def _bump_version(v: str, major_bump: int, minor_bump: int, patch_bump: int) -> str:
    """Add an offset to a version string."""
    parts = v.split(".")
    if len(parts) >= 3:
        return f"{int(parts[0]) + major_bump}.{int(parts[1]) + minor_bump}.{int(parts[2]) + patch_bump}"
    if len(parts) >= 2:
        return f"{int(parts[0]) + major_bump}.{int(parts[1]) + minor_bump}.{abs(patch_bump)}"
    return f"{int(parts[0]) + major_bump}.0.0"


def _intersect(c1: str, c2: str) -> str | None:
    """Return the intersection of two constraints, or None if empty."""
    try:
        return _intersect_str(c1, c2)
    except Exception:
        return c1 if c1 != "*" else (c2 if c2 != "*" else "*")


def _intersect_str(c1: str, c2: str) -> str | None:
    """Intersect two specifier strings using SpecifierSet & operator."""
    s1 = SpecifierSet(c1) if c1 and c1 != "*" else SpecifierSet(">=0.0.0")
    s2 = SpecifierSet(c2) if c2 and c2 != "*" else SpecifierSet(">=0.0.0")
    result = s1 & s2
    if not result:
        return None
    # Verify the result actually contains at least one version
    # (packaging may return truthy SpecifierSet with no versions, e.g. ==2.0.0,>=3.0)
    for v in _extract_test_versions(str(result)):
        if result.contains(v):
            return str(result)
    # Try a few common versions
    for v in ["0.0.1", "1.0.0", "2.0.0", "3.0.0", "10.0.0"]:
        if result.contains(v):
            return str(result)
    return None


def _union(c1: str, c2: str) -> str:
    """Return a constraint that covers both *c1* and *c2*.

    For negative terms, union means "any version NOT in either constraint".
    """
    try:
        intersection = _intersect_str(c1, c2)
        if intersection is None:
            return "<0.0.0"
        return intersection
    except Exception:
        return c1 if c1 != "*" else c2


def _difference(c1: str, c2: str) -> str | None:
    """Return a constraint that satisfies *c1* but NOT *c2*."""
    try:
        s1 = SpecifierSet(c1) if c1 and c1 != "*" else SpecifierSet(">=0.0.0")
        s2 = SpecifierSet(c2) if c2 and c2 != "*" else SpecifierSet(">=0.0.0")
        result = s1 - s2
        if not result:
            return None
        return str(result)
    except Exception:
        return c1 if c2 == "*" else (None if c1 == c2 else c1)
