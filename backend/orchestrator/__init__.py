"""Orchestration layer — shared workflow logic for CLI and API.

This package contains cross-cutting workflow functions that are consumed
by both the CLI and API layers. It must NOT import from ``backend.cli``
or ``backend.api`` — only from ``backend.core``, ``backend.settings``,
and ``backend.data_sources``.
"""

from .install import _generate_install_command
from .resolve import (
    _aggregator_to_resolver_input,
    _apply_cuda_variants,
    _extract_cuda_variants,
    _extract_system_requirements,
    _normalize_cuda,
    _parse_package_spec,
    _resolve_transitive,
    _select_best_cuda_variant,
    create_solver,
)
from .scanner import _download_github_repo

__all__ = [
    "_aggregator_to_resolver_input",
    "_apply_cuda_variants",
    "_download_github_repo",
    "_extract_cuda_variants",
    "_extract_system_requirements",
    "_generate_install_command",
    "_normalize_cuda",
    "_parse_package_spec",
    "_resolve_transitive",
    "_select_best_cuda_variant",
    "create_solver",
]
