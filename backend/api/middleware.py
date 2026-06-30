# backend/api/middleware.py
import os
import time
import uuid
import json
import gzip
from typing import Any, Callable, Optional
from datetime import datetime, timezone
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import logging
import structlog

from backend.settings import (
    FEATURES,
    SLOW_REQUEST_THRESHOLD,
    ENABLE_REQUEST_LOGGING,
    ENABLE_PERFORMANCE_LOGGING,
    MAX_REQUEST_SIZE,
    PROMETHEUS_ENABLED,
)
from backend.core.cache import cache_manager

logger = logging.getLogger(__name__)

# Prometheus metrics
_request_duration: Optional[Any] = None
try:
    from prometheus_client import Histogram as _Histogram

    _request_duration = _Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint", "status"],
    )
except ImportError:
    pass


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Add and propagate unique correlation ID across services.

    Accepts incoming X-Correlation-ID from upstream (API gateway, load balancer)
    or generates one. Ensures every request has a traceable ID that survives
    across service boundaries.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        request.state.correlation_id = correlation_id
        request.state.request_id = correlation_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Request-ID"] = correlation_id

        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log requests and responses"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not ENABLE_REQUEST_LOGGING:
            return await call_next(request)

        start_time = time.time()

        # Log request
        request_body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                request_body = await request.body()

                # Recreate request with body
                async def receive():
                    return {"type": "http.request", "body": request_body}

                request._receive = receive
            except Exception:
                pass

        # Get request info
        request_info = {
            "request_id": getattr(request.state, "request_id", None),
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_host": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }

        logger.info(f"Request started: {json.dumps(request_info)}")

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log response
        response_info = {
            "request_id": getattr(request.state, "request_id", None),
            "status_code": response.status_code,
            "duration_seconds": round(duration, 3),
        }

        logger.info(f"Request completed: {json.dumps(response_info)}")

        # Add timing header
        response.headers["X-Process-Time"] = str(duration)

        return response


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Monitor and log slow requests"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not ENABLE_PERFORMANCE_LOGGING:
            return await call_next(request)

        start_time = time.time()

        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log slow requests
        if duration > SLOW_REQUEST_THRESHOLD:
            logger.warning(
                "Slow request detected",
                extra={
                    "request_id": getattr(request.state, "request_id", None),
                    "method": request.method,
                    "path": request.url.path,
                    "duration_seconds": round(duration, 3),
                    "threshold_seconds": SLOW_REQUEST_THRESHOLD,
                    "status_code": response.status_code,
                },
            )

        # Add performance headers
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        # Update metrics if enabled
        if PROMETHEUS_ENABLED and _request_duration is not None:
            _request_duration.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
            ).observe(duration)

        return response


class CompressionMiddleware(BaseHTTPMiddleware):
    """Compress responses when appropriate"""

    def __init__(self, app: ASGIApp, minimum_size: int = 1024):
        super().__init__(app)
        self.minimum_size = minimum_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not FEATURES.get("ENABLE_RESPONSE_COMPRESSION", True):
            return await call_next(request)

        # Check if client accepts gzip
        accept_encoding = request.headers.get("accept-encoding", "")
        if "gzip" not in accept_encoding:
            return await call_next(request)

        response = await call_next(request)

        # Only compress certain content types
        content_type = response.headers.get("content-type", "")
        compressible_types = [
            "application/json",
            "text/html",
            "text/plain",
            "text/css",
            "text/javascript",
            "application/javascript",
        ]

        if not any(ct in content_type for ct in compressible_types):
            return response

        # Check response size
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) < self.minimum_size:
            return response

        # Compress response body
        if hasattr(response, "body"):
            compressed_body = gzip.compress(response.body)
            response.body = compressed_body
            response.headers["content-encoding"] = "gzip"
            response.headers["content-length"] = str(len(compressed_body))
            # Add Vary header
            vary = response.headers.get("vary", "")
            if vary:
                response.headers["vary"] = f"{vary}, Accept-Encoding"
            else:
                response.headers["vary"] = "Accept-Encoding"

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to responses"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Add CSP header for API responses
        if request.url.path.startswith("/api/"):
            if request.url.path in ("/api/v1/docs", "/api/v1/redoc"):
                csp = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' https://fastapi.tiangolo.com data:; font-src 'self' data:; frame-ancestors 'none';"
            else:
                csp = "default-src 'none'; frame-ancestors 'none';"
            response.headers["Content-Security-Policy"] = csp

        # Add HSTS for HTTPS connections
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size"""

    def __init__(self, app: ASGIApp, max_size: Optional[int] = None):
        super().__init__(app)
        self.max_size = max_size or MAX_REQUEST_SIZE

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check Content-Length header
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "type": "request_too_large",
                        "message": f"Request body too large. Maximum size is {self.max_size} bytes",
                        "status_code": 413,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                },
            )

        # For streaming bodies, we need to check during reading
        if request.method in ["POST", "PUT", "PATCH"]:
            body_size = 0
            chunks = []

            async for chunk in request.stream():
                body_size += len(chunk)
                if body_size > self.max_size:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "type": "request_too_large",
                                "message": f"Request body too large. Maximum size is {self.max_size} bytes",
                                "status_code": 413,
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                        },
                    )
                chunks.append(chunk)

            body = b"".join(chunks)

            # Set _body so downstream middlewares and route handlers
            # can read the body via request.body() without re-consuming the stream
            request._body = body

        return await call_next(request)


class CacheMiddleware(BaseHTTPMiddleware):
    """Cache responses for GET requests"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only cache GET requests
        if request.method != "GET" or not FEATURES.get("ENABLE_CACHE", True):
            return await call_next(request)

        # Skip caching for certain paths
        skip_paths = ["/api/v1/health", "/api/v1/system/benchmarks", "/docs", "/redoc"]
        if any(request.url.path.startswith(path) for path in skip_paths):
            return await call_next(request)

        # Generate cache key
        cache_key = f"response:{request.method}:{request.url.path}:{request.url.query}"

        # Try to get from cache
        cached_response = await cache_manager.get(cache_key)
        if cached_response:
            # Return cached response
            return Response(
                content=cached_response["content"],
                status_code=cached_response["status_code"],
                headers=cached_response["headers"],
                media_type=cached_response.get("media_type"),
            )

        # Process request
        response = await call_next(request)

        # Cache successful responses
        if response.status_code == 200:
            # Read response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # Cache the response
            cache_data = {
                "content": body.decode("utf-8") if body else "",
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "media_type": response.media_type,
            }

            # Determine TTL based on endpoint
            ttl = 300  # 5 minutes default
            if "/packages/search" in request.url.path:
                ttl = 60  # 1 minute for search
            elif "/packages/" in request.url.path and "/versions" in request.url.path:
                ttl = 600  # 10 minutes for versions

            await cache_manager.set(cache_key, cache_data, ttl)

            # Return new response with body
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Collect metrics for monitoring"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not FEATURES.get("ENABLE_METRICS", True):
            return await call_next(request)

        start_time = time.time()

        # Increment request counter
        await cache_manager.increment("metrics:requests:total")
        await cache_manager.increment(f"metrics:requests:method:{request.method}")
        await cache_manager.increment(f"metrics:requests:path:{request.url.path}")

        try:
            response = await call_next(request)

            # Record response metrics
            duration = time.time() - start_time
            await cache_manager.increment(
                f"metrics:responses:status:{response.status_code}"
            )

            # Record timing metrics (using Redis sorted sets would be better)
            timing_key = f"metrics:timing:{request.url.path}:{datetime.utcnow().strftime('%Y%m%d%H')}"
            await cache_manager.set(
                timing_key, duration, ttl=86400
            )  # Keep for 24 hours

            return response

        except Exception as e:
            # Record error metrics
            await cache_manager.increment("metrics:errors:total")
            await cache_manager.increment(f"metrics:errors:type:{type(e).__name__}")
            raise


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    """Handle maintenance mode"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check if maintenance mode is enabled
        maintenance_mode = await cache_manager.get("system:maintenance_mode")

        if maintenance_mode:
            # Allow health checks during maintenance
            if request.url.path == "/api/v1/health":
                return await call_next(request)

            # Return maintenance response
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "type": "maintenance_mode",
                        "message": "The service is currently under maintenance. Please try again later.",
                        "status_code": 503,
                        "timestamp": datetime.utcnow().isoformat(),
                        "details": maintenance_mode
                        if isinstance(maintenance_mode, dict)
                        else {},
                    }
                },
                headers={
                    "Retry-After": "3600",  # Retry after 1 hour
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )

        return await call_next(request)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Emit structured audit logs for all mutating requests.

    Logs who (user/subject), what (action), which (resource), and when
    for POST, PUT, PATCH, DELETE requests. Compatible with SOC 2 / ISO 27001
    audit trail requirements.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        log = structlog.get_logger("backend.api.audit")

        response = await call_next(request)

        log.info(
            "audit.write",
            correlation_id=getattr(request.state, "correlation_id", None),
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params),
            status_code=response.status_code,
            client_host=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        return response


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """Protect against CSRF attacks for cookie-authenticated clients.

    For state-changing requests (POST/PUT/PATCH/DELETE), requires either:
    - A Bearer token in the Authorization header (API clients), or
    - A valid CSRF token in X-CSRF-Token header (browser clients).

    Safe methods (GET/HEAD/OPTIONS) are never blocked.
    """

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
    CSRF_COOKIE_NAME = "csrf_token"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method in self.SAFE_METHODS:
            return await call_next(request)

        # Allow bypassing CSRF when disabled via feature flag
        from backend.settings import FEATURES

        if not FEATURES.get("ENABLE_CSRF", True):
            return await call_next(request)

        # API clients using Bearer auth are exempt
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return await call_next(request)

        # Check for CSRF token in header vs cookie (double-submit pattern)
        csrf_cookie = request.cookies.get(self.CSRF_COOKIE_NAME)
        csrf_header = request.headers.get("X-CSRF-Token")

        if csrf_cookie and csrf_header and csrf_cookie == csrf_header:
            return await call_next(request)

        # No auth + no CSRF token — only block if same-origin can't be verified
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        allowed_origins = os.getenv("ALLOWED_ORIGINS", "").split(",")

        if origin and any(origin.strip() == o.strip() for o in allowed_origins):
            return await call_next(request)

        if referer and any(
            ref.strip() in referer for ref in allowed_origins if ref.strip()
        ):
            return await call_next(request)

        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "type": "csrf_protection",
                    "message": "CSRF validation failed. Include X-CSRF-Token header or use Bearer auth.",
                    "status_code": 403,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            },
        )


# Utility middleware functions
async def get_client_ip(request: Request) -> str:
    """Get client IP address from request"""
    # Check X-Forwarded-For header first (for proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


async def get_user_agent(request: Request) -> str:
    """Get user agent from request"""
    return request.headers.get("User-Agent", "unknown")


# Middleware configuration function
def setup_middleware(app):
    """Configure all middleware for the application"""
    # Order matters! Middleware is executed in reverse order for responses

    # Maintenance mode should be first (last to execute)
    app.add_middleware(MaintenanceModeMiddleware)

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Request size limit
    app.add_middleware(RequestSizeLimitMiddleware)

    # Compression
    app.add_middleware(CompressionMiddleware)

    # Caching
    if FEATURES.get("ENABLE_CACHE", True):
        app.add_middleware(CacheMiddleware)

    # Metrics collection
    if FEATURES.get("ENABLE_METRICS", True):
        app.add_middleware(MetricsMiddleware)

    # Performance monitoring
    if ENABLE_PERFORMANCE_LOGGING:
        app.add_middleware(PerformanceMiddleware)

    # Request logging
    if ENABLE_REQUEST_LOGGING:
        app.add_middleware(LoggingMiddleware)

    # Audit log for mutating requests
    app.add_middleware(AuditLogMiddleware)

    # CSRF protection (applies to cookie-based sessions)
    app.add_middleware(CSRFProtectionMiddleware)

    # Correlation ID (earliest in the chain so all downstream middleware see it)
    app.add_middleware(CorrelationIDMiddleware)

    logger.info("Middleware configuration completed")
