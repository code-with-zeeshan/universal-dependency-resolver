"""Module docstring."""

# backend/api/main.py
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request, status
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

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Use absolute imports
from backend import __version__
from backend.api.dependencies import limiter
from backend.api.middleware import setup_middleware
from backend.api.routes import (
    auth as auth_routes,
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
from backend.data_sources.base_client import close_all_sessions
from backend.logging_config import setup_logging
from backend.settings import API_KEY, API_KEY_HEADER, FEATURES
from backend.tracing_config import setup_tracing

# Configure structured logging
setup_logging()
logger = structlog.get_logger(__name__)


# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifecycle events."""
    # Startup
    logger.info("Starting Universal Dependency Resolver API...")

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

    # Dispose of database connections
    try:
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

# Setup monitoring
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn and SENTRY_AVAILABLE:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=1.0,
        environment=os.getenv("ENVIRONMENT", "development"),
    )
    logger.info("Sentry monitoring enabled")

if PROMETHEUS_AVAILABLE:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("Prometheus metrics enabled at /metrics")

# Configure CORS
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
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
    if api_key == API_KEY:
        request.state.api_key_name = "env-super-admin"
        request.state.api_key_role = "admin"
        return await call_next(request)

    # 2. Check against database-backed API keys
    try:
        from backend.database.service import authenticate_api_key

        result = authenticate_api_key(api_key)
        if result is not None:
            request.state.api_key_name = result["name"]
            request.state.api_key_role = result["role"]
            return await call_next(request)
    except Exception:
        pass

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
    standalone = os.getenv("UDR_STANDALONE", "false").lower() == "true"

    optional_env_vars = [
        "REDIS_URL",
        "ALLOWED_ORIGINS",
        "API_KEY",  # For future auth implementation
    ]

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
    for var in optional_env_vars:
        if os.getenv(var):
            logger.info(f"Optional variable {var} is configured")
        else:
            logger.warning(f"Optional variable {var} is not set")

    # Guard: production must have auth enabled
    env = os.getenv("ENV", "development")
    enable_auth = os.getenv("ENABLE_AUTH", "true").lower() == "true"
    if env == "production" and not enable_auth:
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
    redis_url = os.getenv("REDIS_URL")
    if redis_url and not standalone:
        try:
            import redis

            r = redis.from_url(redis_url)
            r.ping()
            logger.info("Redis connection successful")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Falling back to in-memory cache.")


# Shutdown handler for graceful tracer shutdown
@app.on_event("shutdown")
async def shutdown_tracing():
    """Gracefully shut down the OpenTelemetry tracer provider."""
    try:
        from opentelemetry import trace as otel_trace

        provider = otel_trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
        logger.info("OpenTelemetry tracer provider shut down")
    except Exception as e:
        logger.warning(f"Error shutting down tracer: {e}")


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
    return {"status": "ok"}


@app.get("/readyz", tags=["Health"])
async def readyz():
    return {"status": "ok"}


# Health check endpoint with dependency checks
@app.get("/api/v1/health", tags=["General"])
@limiter.limit("30/minute")
async def health_check(request: Request) -> dict:
    """Health check endpoint that verifies all critical dependencies.
    Returns detailed status of each component.
    """
    health_status: dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": __version__,
        "checks": {},
    }

    # Check database with detailed health information
    try:
        from backend.orchestrator.db_service import check_health

        db_health = check_health()
        health_status["checks"]["database"] = db_health
        if db_health["status"] == "unhealthy":
            health_status["status"] = "unhealthy"
    except Exception as e:
        health_status["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "unhealthy"

    # Check Redis if configured
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis

            r = redis.from_url(redis_url)
            r.ping()
            health_status["checks"]["redis"] = {"status": "healthy"}
        except Exception as e:
            health_status["checks"]["redis"] = {"status": "unhealthy", "error": str(e)}
            # Redis is optional, so don't mark overall status as unhealthy

    # Check external APIs — verify at least one upstream registry is reachable
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as hc:
            r = await hc.get("https://pypi.org/pypi/pip/json")
            health_status["checks"]["external_apis"] = {
                "status": "healthy" if r.is_success else "degraded",
                "pypi": r.status_code,
            }
    except Exception as e:
        health_status["checks"]["external_apis"] = {
            "status": "degraded",
            "error": str(e),
        }

    return health_status


# Include routers with versioned prefix
# Register auth router only when auth is enabled (saas mode)
enable_auth = os.getenv("ENABLE_AUTH", "true").lower() == "true"
if enable_auth:
    app.include_router(auth_routes.router, prefix="/api/v1/auth", tags=["Auth"])
else:
    logger.info("Auth endpoints disabled (ENABLE_AUTH=false)")

app.include_router(system.router, prefix="/api/v1/system", tags=["System"])

app.include_router(packages.router, prefix="/api/v1/packages", tags=["Packages"])


app.include_router(scan.router, prefix="/api/v1", tags=["Scan"])
app.include_router(lock_routes.router, prefix="/api/v1", tags=["Lock"])

app.include_router(index_routes.router, prefix="/api/v1/index", tags=["Index"])
app.include_router(completion_routes.router, prefix="/api/v1", tags=["Completion"])


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
        query_params=dict(request.query_params),
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
        reload=os.getenv("ENVIRONMENT", "development") == "development",
    )
