"""Module docstring."""

# backend/api/main.py
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import Response

# Monitoring imports
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

try:
    from prometheus_fastapi_instrumentator import Instrumentator
    from prometheus_fastapi_instrumentator.routing import _get_route_name as _orig_get_route_name

    def _safe_get_route_name(scope, routes, route_name=None):
        try:
            return _orig_get_route_name(scope, routes, route_name)
        except (AttributeError, TypeError):
            return route_name or "unknown"

    import prometheus_fastapi_instrumentator.routing as _pfi_routing

    _pfi_routing._get_route_name = _safe_get_route_name

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Use absolute imports
from backend import __version__
from backend.api.auth import get_current_user
from backend.api.dependencies import limiter
from backend.api.middleware import setup_middleware
from backend.api.routes import (
    auth as auth_routes,
)
from backend.api.routes import (
    check as check_routes,
)
from backend.api.routes import (
    completion as completion_routes,
)
from backend.api.routes import (
    index as index_routes,
)
from backend.api.routes import (
    lock as lock_routes,
)
from backend.api.routes import (
    packages,
    scan,
    system,
)
from backend.api.routes import (
    sbom as sbom_routes,
)
from backend.core.shutdown import ShutdownFlag, register_signal_handlers
from backend.data_sources.base_client import close_all_sessions
from backend.logging_config import setup_logging
from backend.settings import (
    ALLOWED_ORIGINS,
    API_KEY,
    API_KEY_HEADER,
    ENABLE_AUTH,
    ENV,
    FEATURES,
    REDIS_URL,
    SENTRY_DSN,
    UDR_STANDALONE,
)
from backend.tracing_config import setup_tracing

# Global shutdown flag for graceful shutdown
SHUTDOWN_FLAG = ShutdownFlag()

# Configure structured logging
setup_logging()
logger = structlog.get_logger(__name__)


# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifecycle events."""
    # Startup
    logger.info("Starting Universal Dependency Resolver API...")

    # Register signal handlers for graceful shutdown
    register_signal_handlers(SHUTDOWN_FLAG)

    # Configure OpenTelemetry tracing
    setup_tracing(app=app)
    logger.info("OpenTelemetry tracing configured")

    # Validate environment
    try:
        await validate_environment()
        logger.info("Environment validation completed successfully")
    except Exception as e:
        logger.error(f"Environment validation failed: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Universal Dependency Resolver API...")

    # Mark shutdown flag
    SHUTDOWN_FLAG.request_shutdown()

    # Gracefully shut down the OpenTelemetry tracer provider
    try:
        from opentelemetry import trace as otel_trace

        provider = otel_trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
        logger.info("OpenTelemetry tracer provider shut down")
    except Exception as e:
        logger.warning(f"Error shutting down tracer: {e}")

    # Dispose of database connections
    try:
        from backend.orchestrator.db_service import get_db_engine

        get_db_engine().dispose()
        logger.info("Database connections disposed")
    except Exception as e:
        logger.warning(f"Error disposing database connections: {e}")

    # Close all aiohttp sessions
    try:
        await close_all_sessions()
        logger.info("HTTP sessions closed")
    except Exception as e:
        logger.warning(f"Error closing HTTP sessions: {e}")


# Create FastAPI app with lifespan events
app = FastAPI(
    title="Universal Dependency Resolver API",
    description="A comprehensive API for resolving dependencies across multiple package ecosystems",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)
setup_middleware(app)

def _sentry_before_send(event: dict, hint: dict) -> dict | None:
    """Strip sensitive data from Sentry events before sending."""
    if "request" in event:
        request = event["request"]
        request.pop("data", None)
        headers = request.get("headers", {})
        for sensitive_header in ("authorization", "cookie", "x-api-key", "x-auth-token"):
            headers.pop(sensitive_header, None)
        request["headers"] = headers
    return event

# Setup monitoring
if SENTRY_DSN and SENTRY_AVAILABLE:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=ENV,
        before_send=_sentry_before_send,
    )
    logger.info("Sentry monitoring enabled")

if PROMETHEUS_AVAILABLE:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("Prometheus metrics enabled at /metrics")

# Configure CORS
allowed_origins = [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]
# Add file:// for desktop Electron app
if "file://" not in allowed_origins:
    allowed_origins.append("file://")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
)


# API Key Authentication Middleware
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Async api key middleware."""
    exempt_paths = {"/healthz", "/readyz", "/api/v1/health", "/api/v1/readyz"}
    if request.url.path in exempt_paths or request.method == "OPTIONS":
        return await call_next(request)

    if not FEATURES.get("ENABLE_AUTH", True):
        return await call_next(request)

    api_key = request.headers.get(API_KEY_HEADER)
    if not api_key:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing API key"},
        )

    # 1. Check against env var API_KEY (super-admin, backward compat)
    if secrets.compare_digest(api_key, API_KEY):
        request.state.api_key_name = "env-super-admin"
        request.state.api_key_role = "admin"
        return await call_next(request)

    # 2. Check against database-backed API keys
    try:
        from backend.orchestrator.db_service import authenticate_api_key

        result = await asyncio.to_thread(authenticate_api_key, api_key)
        if result is not None:
            request.state.api_key_name = result["name"]
            request.state.api_key_role = result["role"]
            return await call_next(request)
    except Exception:
        logger.exception("Auth middleware error during API key validation")

    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Invalid or missing API key"},
    )


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions consistently."""
    log = structlog.get_logger("backend.api.main.exception")
    log.error(
        "Unhandled exception",
        error=str(exc),
        exc_info=True,
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": "An unexpected error occurred",
                "type": "internal_server_error",
                "timestamp": datetime.now().isoformat(),
            }
        },
    )


# Custom HTTPException handler for consistent error format
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions with consistent format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
                "type": "http_error",
                "status_code": exc.status_code,
                "timestamp": datetime.now().isoformat(),
            }
        },
    )


# Environment validation function
async def validate_environment() -> None:
    """Validate environment configuration on startup."""
    standalone = UDR_STANDALONE

    if not standalone:
        from backend.settings import DATABASE_URL

        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")

    # Validate critical settings
    try:
        from backend.settings import validate_settings

        config_warnings = validate_settings()
        for w in config_warnings:
            logger.warning(f"Configuration issue: {w}")
    except Exception as e:
        logger.warning(f"Settings validation failed: {e}")

    # Log optional variables status
    for var_name, var_val in [
        ("REDIS_URL", REDIS_URL),
        ("ALLOWED_ORIGINS", ALLOWED_ORIGINS),
        ("API_KEY", API_KEY),
    ]:
        if var_val:
            logger.info(f"Optional variable {var_name} is configured")
        else:
            logger.warning(f"Optional variable {var_name} is not set")

    # Guard: production must have auth enabled
    if ENV == "production" and not ENABLE_AUTH:
        raise RuntimeError(
            "Refusing to start in production mode with ENABLE_AUTH=false. "
            "Set ENABLE_AUTH=true and configure SECRET_KEY."
        )

    # Test database connection
    try:
        from sqlalchemy import text

        from backend.orchestrator.db_service import get_db_engine

        with get_db_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
    except Exception as e:
        raise RuntimeError(f"Database connection failed: {e}")

    # Test Redis connection if configured (skipped in standalone/desktop mode)
    redis_url = REDIS_URL
    if redis_url and not standalone:
        try:
            import redis

            r = redis.from_url(redis_url)
            r.ping()
            logger.info("Redis connection successful")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Falling back to in-memory cache.")


# Root endpoint
@app.get("/", tags=["General"])
@limiter.limit("10/minute")
async def root(request: Request) -> dict:
    """Get API information and available endpoints."""
    return {
        "name": "Universal Dependency Resolver API",
        "version": __version__,
        "documentation": {"openapi": "/api/v1/docs", "redoc": "/api/v1/redoc"},
        "endpoints": {
            "health": "/api/v1/health",
            "system_info": "/api/v1/system/info",
            "package_info": "/api/v1/packages/{ecosystem}/{name}",
            "resolve": "/api/v1/packages/resolve",
            "export": "/api/v1/packages/export",
            "formats": "/api/v1/packages/export-formats",
        },
    }


@app.get("/healthz", tags=["Health"])
async def healthz():
    """Async healthz."""
    return {"status": "ok"}


@app.get("/readyz", tags=["Health"])
async def readyz():
    """Async readyz."""
    return {"status": "ok"}


# Health check endpoint with dependency checks (requires auth — reveals infrastructure)
@app.get("/api/v1/health", tags=["General"])
@limiter.limit("30/minute")
async def health_check(request: Request, _user=Depends(get_current_user)) -> dict:
    """Health check endpoint that verifies all critical dependencies.

    Returns detailed status of each component (requires authentication).
    """
    health_status: dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": __version__,
    }

    try:
        from backend.orchestrator.db_service import check_health

        db_health = check_health()
        if db_health.get("status") == "unhealthy":
            health_status["status"] = "unhealthy"
    except Exception:
        health_status["status"] = "unhealthy"

    return health_status


# Include routers with versioned prefix
# Register auth router only when auth is enabled (saas mode)
if ENABLE_AUTH:
    app.include_router(auth_routes.router, prefix="/api/v1/auth", tags=["Auth"])
else:
    logger.info("Auth endpoints disabled (ENABLE_AUTH=false)")

app.include_router(system.router, prefix="/api/v1/system", tags=["System"])

app.include_router(packages.router, prefix="/api/v1/packages", tags=["Packages"])


app.include_router(scan.router, prefix="/api/v1", tags=["Scan"])
app.include_router(lock_routes.router, prefix="/api/v1", tags=["Lock"])

app.include_router(index_routes.router, prefix="/api/v1/index", tags=["Index"])
app.include_router(completion_routes.router, prefix="/api/v1", tags=["Completion"])
app.include_router(check_routes.router, prefix="/api/v1", tags=["Check"])
app.include_router(sbom_routes.router, prefix="/api/v1", tags=["SBOM"])


# Optional: Add middleware for response time tracking
@app.middleware("http")
async def add_process_time_header(request: Request, call_next) -> Response:
    """Add response time header."""
    import time

    start_time = time.time()

    response = await call_next(request)

    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Structlog request/response logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log each request and response with structured logging."""
    start_time = time.time()
    log = structlog.get_logger("backend.api.main.request")

    method = request.method
    path = request.url.path
    import uuid

    request_id = (
        getattr(request.state, "correlation_id", None)
        or getattr(request.state, "request_id", None)
        or str(uuid.uuid4())
    )
    request.state.request_id = request_id
    request.state.correlation_id = request_id

    log.info(
        "Request started",
        method=method,
        path=path,
        request_id=request_id,
        query_params={
            k: "***" if "token" in k.lower() or "key" in k.lower() or "password" in k.lower() else v
            for k, v in request.query_params.items()
        },
        client_host=request.client.host if request.client else None,
    )

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        log.error(
            "Request failed",
            method=method,
            path=path,
            request_id=getattr(request.state, "request_id", request_id),
            duration_ms=round(duration_ms, 2),
            error=str(exc),
            exc_info=True,
        )
        raise

    duration_ms = (time.time() - start_time) * 1000
    effective_id = getattr(request.state, "correlation_id", None) or getattr(
        request.state, "request_id", request_id
    )
    log.info(
        "Request completed",
        method=method,
        path=path,
        request_id=effective_id,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )

    response.headers["X-Process-Time"] = f"{duration_ms / 1000:.3f}"
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=ENV == "development",
    )
