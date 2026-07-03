"""CUDA variant utilities.

Re-exports from orchestrator for backward compatibility.
"""

from backend.orchestrator.resolve import (
    _extract_cuda_variants,
    _normalize_cuda,
    _select_best_cuda_variant,
)


def _extract_severity(vuln: dict) -> str:
    """Extract Severity."""
    sev = vuln.get("severity", [])
    if isinstance(sev, list) and sev:
        return sev[0].get("score", sev[0].get("type", "UNKNOWN"))
    if isinstance(sev, str):
        return sev
    return "UNKNOWN"
