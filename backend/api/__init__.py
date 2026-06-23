# backend/api/__init__.py
"""
Universal Dependency Resolver API Package

This package contains all API-related components including routes,
middleware, authentication, and exception handling.
"""

# Import main app instance
from .main import app

# Import routers
from .routes import packages, system

# Import middleware
from .middleware import (
    CorrelationIDMiddleware,
    LoggingMiddleware,
    PerformanceMiddleware,
    CompressionMiddleware,
    SecurityHeadersMiddleware,
    RequestSizeLimitMiddleware,
    CacheMiddleware,
    MetricsMiddleware,
    MaintenanceModeMiddleware,
    AuditLogMiddleware,
    CSRFProtectionMiddleware,
    setup_middleware,
    get_client_ip,
    get_user_agent,
)

# Import exceptions
from .exceptions import (
    DependencyResolverError,
    ValidationError,
    PackageNotFoundError,
    EcosystemNotSupportedError,
    ConflictResolutionError,
    RateLimitExceededError,
)

# Import auth components
from .auth import (
    # Models
    Token,
    TokenData,
    UserCreate,
    UserLogin,
    APIKeyCreate,
    # Functions
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    generate_api_key,
    get_current_user,
    get_current_active_user,
    require_scopes,
    # Service
    AuthService,
    # OAuth2
    oauth2_scheme,
    login_for_access_token,
)

# Version info
__version__ = "1.0.0"
__author__ = "Universal Dependency Resolver Team"

# Export main components
__all__ = [
    # App
    "app",
    # Routers
    "packages",
    "system",
    # Middleware
    "setup_middleware",
    "CorrelationIDMiddleware",
    "LoggingMiddleware",
    "PerformanceMiddleware",
    "CompressionMiddleware",
    "SecurityHeadersMiddleware",
    "RequestSizeLimitMiddleware",
    "CacheMiddleware",
    "MetricsMiddleware",
    "MaintenanceModeMiddleware",
    "AuditLogMiddleware",
    "CSRFProtectionMiddleware",
    # Exceptions
    "DependencyResolverError",
    "ValidationError",
    "PackageNotFoundError",
    "EcosystemNotSupportedError",
    "ConflictResolutionError",
    "RateLimitExceededError",
    # Auth
    "Token",
    "UserCreate",
    "UserLogin",
    "APIKeyCreate",
    "AuthService",
    "get_current_user",
    "get_current_active_user",
    "require_scopes",
    # Utilities
    "get_client_ip",
    "get_user_agent",
]
