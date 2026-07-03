"""Custom exception classes for structured error handling."""

from typing import Dict, Any, Optional, List


class DependencyResolverError(Exception):
    """Base exception for dependency resolver errors."""

    def __init__(
        self,
        message: str,
        error_code: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize."""
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(DependencyResolverError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: Optional[str] = None):
        """Initialize."""
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=400,
            details={"field": field} if field else {},
        )


class PackageNotFoundError(DependencyResolverError):
    """Raised when a package cannot be found."""

    def __init__(self, package_name: str, ecosystem: Optional[str] = None):
        """Initialize."""
        super().__init__(
            message=f"Package '{package_name}' not found",
            error_code="PACKAGE_NOT_FOUND",
            status_code=404,
            details={"package_name": package_name, "ecosystem": ecosystem},
        )


class EcosystemNotSupportedError(DependencyResolverError):
    """Raised when an ecosystem is not supported."""

    def __init__(self, ecosystem: str):
        """Initialize."""
        super().__init__(
            message=f"Ecosystem '{ecosystem}' is not supported",
            error_code="ECOSYSTEM_NOT_SUPPORTED",
            status_code=400,
            details={"ecosystem": ecosystem},
        )


class ConflictResolutionError(DependencyResolverError):
    """Raised when dependency conflicts cannot be resolved."""

    def __init__(self, message: str, conflicts: Optional[List[Dict]] = None):
        """Initialize."""
        super().__init__(
            message=message,
            error_code="CONFLICT_RESOLUTION_FAILED",
            status_code=409,
            details={"conflicts": conflicts or []},
        )


class RateLimitExceededError(DependencyResolverError):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: Optional[int] = None):
        """Initialize."""
        super().__init__(
            message="Rate limit exceeded",
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after": retry_after},
        )
