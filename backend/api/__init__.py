# backend/api/__init__.py
"""Universal Dependency Resolver API Package.

This package contains all API-related components including routes,
middleware, authentication, and exception handling.
"""

# Import main app instance
# Import auth components
from .auth import (
    APIKeyCreate,
    AuthService,
    Token,
    UserCreate,
    UserLogin,
    get_current_active_user,
    get_current_user,
    login_for_access_token,
    oauth2_scheme,
    require_scopes,
)
from .main import app

# Import middleware
from .middleware import (
    AuditLogMiddleware,
    CacheMiddleware,
    CompressionMiddleware,
    CorrelationIDMiddleware,
    CSRFProtectionMiddleware,
    LoggingMiddleware,
    MaintenanceModeMiddleware,
    MetricsMiddleware,
    PerformanceMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
    get_client_ip,
    get_user_agent,
    setup_middleware,
)

# Import routers
from .routes import packages, system

# Version info
try:
    from importlib.metadata import version as _v

    __version__ = _v("ud-resolver")
except Exception:
    __version__ = "0.0.0"
__author__ = "Universal Dependency Resolver Team"

# Export main components
__all__ = [
    "APIKeyCreate",
    "AuditLogMiddleware",
    "AuthService",
    "CSRFProtectionMiddleware",
    "CacheMiddleware",
    "CompressionMiddleware",
    "CorrelationIDMiddleware",
    "LoggingMiddleware",
    "MaintenanceModeMiddleware",
    "MetricsMiddleware",
    "PerformanceMiddleware",
    "RequestSizeLimitMiddleware",
    "SecurityHeadersMiddleware",
    # Auth
    "Token",
    "UserCreate",
    "UserLogin",
    # App
    "app",
    # Utilities
    "get_client_ip",
    "get_current_active_user",
    "get_current_user",
    "get_user_agent",
    "login_for_access_token",
    "oauth2_scheme",
    # Routers
    "packages",
    "require_scopes",
    # Middleware
    "setup_middleware",
    "system",
]
