"""Module docstring."""

from backend.orchestrator import (
    _apply_cuda_variants,
    _select_best_cuda_variant,
)

from .main import _build_parser, main
from .shared import (
    VERSION,
    _aggregator_to_resolver_input,
    _build_resolved_table,
    _extract_cuda_variants,
    _extract_severity,
    _extract_system_requirements,
    _fetch_package_data,
    _generate_install_command,
    _normalize_cuda,
    _output_json,
    _parse_package_spec,
    _read_lock_file,
    _resolve_transitive,
    _select_manifests_interactive,
    _validate_manifest_update_line,
    console,
    err_console,
    logger,
)

__all__ = [
    "VERSION",
    "_aggregator_to_resolver_input",
    "_apply_cuda_variants",
    "_build_parser",
    "_build_resolved_table",
    "_extract_cuda_variants",
    "_extract_severity",
    "_extract_system_requirements",
    "_fetch_package_data",
    "_generate_install_command",
    "_normalize_cuda",
    "_output_json",
    "_parse_package_spec",
    "_read_lock_file",
    "_resolve_transitive",
    "_select_best_cuda_variant",
    "_select_manifests_interactive",
    "_validate_manifest_update_line",
    "console",
    "err_console",
    "logger",
    "main",
]
