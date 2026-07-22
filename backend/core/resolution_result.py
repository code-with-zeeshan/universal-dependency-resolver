"""Structured resolution result — dataclass wrapping solver output."""

from __future__ import annotations

import typing
from dataclasses import dataclass, field

if typing.TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass
class ResolutionResult:
    """Structured result of a dependency resolution operation.

    Wraps the raw dict returned by ``ConflictResolver.resolve_dependencies``
    into a typed dataclass for safe, discoverable consumption by library users.
    """

    status: str
    resolved_packages: dict[str, dict[str, str]]
    dependency_tree: dict
    warnings: list[str]
    installation_order: list[str]

    error: str | None = None
    conflicts: list[dict] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """Return ``True`` if resolution completed successfully."""
        return self.status == "satisfiable"

    @property
    def is_timeout(self) -> bool:
        """Return ``True`` if resolution timed out."""
        return self.status == "timeout"

    @property
    def is_unsatisfiable(self) -> bool:
        """Return ``True`` if resolution found no valid solution."""
        return self.status == "unsatisfiable"

    @property
    def is_partial(self) -> bool:
        """Return ``True`` if resolution returned a partial result."""
        return self.status == "partial"

    @classmethod
    def from_dict(cls, data: Mapping[str, typing.Any]) -> ResolutionResult:
        """Build from the raw dict returned by ``ConflictResolver.resolve_dependencies``."""
        return cls(
            status=data.get("status", "unknown"),
            resolved_packages=data.get("resolved_packages", data.get("packages", {})),
            dependency_tree=data.get("dependency_tree", {}),
            warnings=data.get("warnings", []),
            installation_order=data.get("installation_order", []),
            error=data.get("error"),
            conflicts=data.get("conflicts", []),
        )

    def to_dict(self) -> dict[str, typing.Any]:
        """Serialize this result to a plain dictionary."""
        d: dict[str, typing.Any] = {
            "status": self.status,
            "resolved_packages": self.resolved_packages,
            "dependency_tree": self.dependency_tree,
            "warnings": self.warnings,
            "installation_order": self.installation_order,
        }
        if self.error is not None:
            d["error"] = self.error
        if self.conflicts:
            d["conflicts"] = self.conflicts
        return d
