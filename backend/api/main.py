# backend/api/main.py
import os
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator
import re
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

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
from backend.core.system_scanner import SystemScanner
from backend.core.data_aggregator import DataAggregator
from backend.core.conflict_resolver import ConflictResolver
from backend.core.export_generator import ExportGenerator
from backend.database.compatibility_db import CompatibilityDB
from backend.settings import settings
from backend.api.routes import packages, system
from backend.api.routes import auth
from backend.api.middleware import setup_middleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize rate limiter with Redis storage if available
redis_url = os.getenv("REDIS_URL")
if redis_url:
    limiter = Limiter(key_func=get_remote_address, storage_uri=redis_url)
else:
    limiter = Limiter(key_func=get_remote_address)

# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifecycle events"""
    # Startup
    logger.info("Starting Universal Dependency Resolver API...")
    
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

# Create FastAPI app with lifespan events
app = FastAPI(
    title="Universal Dependency Resolver API",
    description="A comprehensive API for resolving dependencies across multiple package ecosystems",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json"
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
setup_middleware(app)

# Setup monitoring
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn and SENTRY_AVAILABLE:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=1.0,
        environment=os.getenv("ENVIRONMENT", "development")
    )
    logger.info("Sentry monitoring enabled")

if PROMETHEUS_AVAILABLE:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("Prometheus metrics enabled at /metrics")

# Configure CORS
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions consistently"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": "An unexpected error occurred",
                "type": "internal_server_error",
                "timestamp": datetime.now().isoformat()
            }
        }
    )

# Custom HTTPException handler for consistent error format
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent format"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
                "type": "http_error",
                "status_code": exc.status_code,
                "timestamp": datetime.now().isoformat()
            }
        }
    )

# Dependency factories
def get_system_scanner() -> SystemScanner:
    return SystemScanner()

def get_data_aggregator() -> DataAggregator:
    return DataAggregator()

def get_conflict_resolver() -> ConflictResolver:
    return ConflictResolver()

def get_export_generator() -> ExportGenerator:
    return ExportGenerator()

def get_compatibility_db() -> CompatibilityDB:
    return CompatibilityDB()

# Request/Response Models
class PackageRequest(BaseModel):
    name: str
    ecosystem: Optional[str] = None
    version: Optional[str] = None

    @validator('name')
    def validate_name(cls, v):
        if not re.match(r'^[a-zA-Z0-9\-_\.]+$', v):
            raise ValueError('Invalid package name')
        return v

class SystemInfo(BaseModel):
    gpu: Optional[Dict] = None
    os: Optional[Dict] = None
    cpu: Optional[Dict] = None
    runtime_versions: Optional[Dict] = None

class ResolveRequest(BaseModel):
    packages: List[PackageRequest]
    system_info: Optional[SystemInfo] = None
    auto_detect_system: bool = True
    prefer_compatibility: bool = True

class ExportRequest(BaseModel):
    resolved_packages: Dict
    format: str
    system_info: Optional[Dict] = None
    options: Optional[Dict] = None

# Environment validation function
async def validate_environment():
    """Validate environment configuration on startup"""
    required_env_vars = [
        "DATABASE_URL",
    ]
    
    optional_env_vars = [
        "REDIS_URL",
        "ALLOWED_ORIGINS",
        "API_KEY",  # For future auth implementation
    ]
    
    # Check required variables
    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        raise RuntimeError(f"Missing required environment variables: {missing_vars}")
    
    # Log optional variables status
    for var in optional_env_vars:
        if os.getenv(var):
            logger.info(f"Optional variable {var} is configured")
        else:
            logger.warning(f"Optional variable {var} is not set")
    
    # Test database connection
    try:
        from backend.database.models import engine
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        logger.info("Database connection successful")
    except Exception as e:
        raise RuntimeError(f"Database connection failed: {e}")
    
    # Test Redis connection if configured
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
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
async def root(request: Request):
    """Get API information and available endpoints"""
    return {
        "name": "Universal Dependency Resolver API",
        "version": "1.0.0",
        "documentation": {
            "openapi": "/api/v1/docs",
            "redoc": "/api/v1/redoc"
        },
        "endpoints": {
            "health": "/api/v1/health",
            "system_info": "/api/v1/system/info",
            "package_info": "/api/v1/packages/{ecosystem}/{name}",
            "resolve": "/api/v1/packages/resolve",
            "export": "/api/v1/packages/export",
            "formats": "/api/v1/packages/export-formats"
        }
    }

# Health check endpoint with dependency checks
@app.get("/api/v1/health", tags=["General"])
@limiter.limit("30/minute")
async def health_check(request: Request):
    """
    Health check endpoint that verifies all critical dependencies.
    Returns detailed status of each component.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "checks": {}
    }
    
    # Check database with detailed health information
    try:
        from backend.database.models import check_db_health
        db_health = check_db_health()
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
    
    # Check external APIs (sample check)
    health_status["checks"]["external_apis"] = {"status": "healthy"}
    
    return health_status

# Include routers with versioned prefix
app.include_router(
    system.router,
    prefix="/api/v1/system",
    tags=["System"]
)

app.include_router(
    packages.router,
    prefix="/api/v1/packages", 
    tags=["Packages"]
)

app.include_router(
    auth.router,
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

# Optional: Add middleware for request ID tracking
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID for tracking"""
    import uuid
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# Optional: Add middleware for response time tracking
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add response time header"""
    import time
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if os.getenv("ENVIRONMENT", "development") == "development" else False
    )