"""Sanitize internal error messages for user-friendly display."""

_INTERNAL_PATTERNS: dict[str, str] = {
    "must be a dictionary": "has an invalid format (expected key-value pairs)",
    "gpu information must be": "GPU configuration is in an unexpected format",
    "runtime_versions must be": "runtime version information is in an unexpected format",
    "package entries must be dictionaries": "one or more package entries have an invalid format",
    "ResolvedPackagesError": "package resolution failed — see details above",
    "ResolverError": "resolver encountered an internal error",
}


def sanitize_for_user(message: str) -> str:
    """Replace internal type jargon with user-friendly equivalents."""
    for pattern, replacement in _INTERNAL_PATTERNS.items():
        if pattern in message:
            return replacement
    return message
