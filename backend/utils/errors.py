"""Centralized error handling utilities for the backend."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    """High-level error categories used across the resolver service."""

    VALIDATION = "validation_error"
    SYSTEM_INFO = "system_info_error"
    SOLVER = "solver_error"
    UNSATISFIABLE = "unsatisfiable"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    INTERNAL = "internal_error"
    BATCH = "batch_error"
    NETWORK = "network_error"
    DATA_SOURCE = "data_source_error"


class ResolverErrorCode(StrEnum):
    """Granular error codes for the conflict resolver. Maps to ErrorCategory."""

    VALIDATION_ERROR = "validation_error"
    SYSTEM_INFO_ERROR = "system_info_error"
    SOLVER_ERROR = "solver_error"
    UNSATISFIABLE = "unsatisfiable"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    INTERNAL_ERROR = "internal_error"
    BATCH_ERROR = "batch_error"
    NETWORK_ERROR = "network_error"
    DATA_SOURCE_ERROR = "data_source_error"


@dataclass
class ResolverBaseError(Exception):
    """Base exception carrying structured payload information."""

    message: str
    category: ErrorCategory | None = None
    code: ErrorCategory | ResolverErrorCode | str | None = None
    details: dict[str, Any] | None = None
    warnings: list[str] | None = None
    status_code: int = 500

    def __post_init__(self):
        """Resolve category from code if only code is provided."""
        if self.category is None and self.code is not None:
            code_val = self.code.value if isinstance(self.code, Enum) else self.code
            try:
                self.category = ErrorCategory(code_val)
            except ValueError:
                self.category = ErrorCategory.INTERNAL
        elif self.category is None:
            self.category = ErrorCategory.INTERNAL

    def to_payload(self) -> dict[str, Any]:
        """Render the error in a standard API payload structure."""
        payload: dict[str, Any] = {
            "status": "error",
            "code": self.category.value if self.category else "unknown",
            "message": self.message,
            "resolved_packages": {},
            "warnings": self.warnings or [],
            "status_code": self.status_code,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class ResolverError(ResolverBaseError):
    """Backward-compatible alias for existing resolver errors."""


class ErrorFactory:
    """Helper methods for constructing domain-specific errors consistently."""

    default_messages: dict[ErrorCategory, str] = {
        ErrorCategory.VALIDATION: "Input validation failed.",
        ErrorCategory.SYSTEM_INFO: "System information validation failed.",
        ErrorCategory.SOLVER: "Solver encountered an error while resolving dependencies.",
        ErrorCategory.UNSATISFIABLE: "Dependency constraints are unsatisfiable.",
        ErrorCategory.CIRCULAR_DEPENDENCY: "Circular dependency detected.",
        ErrorCategory.INTERNAL: "An unexpected internal error occurred.",
        ErrorCategory.BATCH: "Batch resolution failed.",
        ErrorCategory.NETWORK: "Network request to external service failed.",
        ErrorCategory.DATA_SOURCE: "Data source returned an invalid response.",
    }

    default_status_codes: dict[ErrorCategory, int] = {
        ErrorCategory.VALIDATION: 400,
        ErrorCategory.SYSTEM_INFO: 400,
        ErrorCategory.SOLVER: 500,
        ErrorCategory.UNSATISFIABLE: 409,
        ErrorCategory.CIRCULAR_DEPENDENCY: 409,
        ErrorCategory.INTERNAL: 500,
        ErrorCategory.BATCH: 500,
        ErrorCategory.NETWORK: 502,
        ErrorCategory.DATA_SOURCE: 502,
    }

    @classmethod
    def build(
        cls,
        category: ErrorCategory,
        *,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        status_code: int | None = None,
    ) -> ResolverError:
        """Create a `ResolverError` using defaults when message is omitted."""
        resolved_message = message or cls.default_messages.get(
            category, "An unexpected error occurred."
        )
        resolved_status_code = status_code or cls.default_status_codes.get(category, 500)
        return ResolverError(
            message=resolved_message,
            category=category,
            details=details,
            warnings=warnings,
            status_code=resolved_status_code,
        )


def ensure_details_context(details: dict[str, Any] | None, **context: Any) -> dict[str, Any]:
    """Merge context data with existing details in a safe, copy-on-write way."""
    effective_details: dict[str, Any] = {"context": context} if context else {}
    if details:
        effective_details.update(details)
    return effective_details


def serialize_exception_chain(error: BaseException) -> list[dict[str, Any]]:
    """Capture the exception chain for diagnostics and telemetry."""
    chain: list[dict[str, Any]] = []
    current: BaseException | None = error  # type: ignore[assignment]
    while current:
        chain.append(
            {
                "type": type(current).__name__,
                "message": str(current),
            }
        )
        cause = current.__cause__ or current.__context__
        current = cause if isinstance(cause, BaseException) else None
    return chain


def make_internal_error(
    error: BaseException,
    *,
    context: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    correlation_id: str | None = None,
) -> ResolverError:
    """Create a standard internal error payload derived from an exception."""
    detail_context = context.copy() if context else {}
    if correlation_id:
        detail_context.setdefault("correlation_id", correlation_id)

    detail_context.setdefault("exception_chain", serialize_exception_chain(error))
    detail_context.setdefault("original_error", str(error))

    return ErrorFactory.build(
        ErrorCategory.INTERNAL,
        details=detail_context,
        warnings=warnings,
    )
