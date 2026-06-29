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

# Import auth components
from .auth import (
    Token,
    UserCreate,
    UserLogin,
    APIKeyCreate,
    get_current_user,
    get_current_active_user,
    require_scopes,
    AuthService,
    oauth2_scheme,
    login_for_access_token,
)

# Version info
try:
    from importlib.metadata import version as _v

    __version__ = _v("ud-resolver")
except Exception:
    __version__ = "0.0.0"
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
    # Auth
    "Token",
    "UserCreate",
    "UserLogin",
    "APIKeyCreate",
    "AuthService",
    "get_current_user",
    "get_current_active_user",
    "require_scopes",
    "oauth2_scheme",
    "login_for_access_token",
    # Utilities
    "get_client_ip",
    "get_user_agent",
]
