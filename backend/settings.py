# settings.py
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# NEW: API Configuration
# =============================================================================
API_VERSION = os.getenv("API_VERSION", "v1")
API_TITLE = os.getenv("API_TITLE", "Universal Dependency Resolver API")
API_DESCRIPTION = os.getenv(
    "API_DESCRIPTION",
    "A comprehensive API for resolving dependencies across multiple package ecosystems",
)

# CORS Configuration
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:8080,http://localhost:3000"
).split(",")
ALLOW_CREDENTIALS = os.getenv("ALLOW_CREDENTIALS", "true").lower() == "true"
ALLOW_METHODS = os.getenv("ALLOW_METHODS", "GET,POST,PUT,DELETE,OPTIONS").split(",")
ALLOW_HEADERS = (
    os.getenv("ALLOW_HEADERS", "*").split(",")
    if os.getenv("ALLOW_HEADERS") != "*"
    else ["*"]
)

# =============================================================================
# NEW: Authentication & Security
# =============================================================================
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

# API Key Configuration (for service-to-service auth)
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")
ENABLE_API_KEY_AUTH = os.getenv("ENABLE_API_KEY_AUTH", "false").lower() == "true"

# =============================================================================
# NEW: Rate Limiting Configuration (API Level)
# =============================================================================
API_RATE_LIMIT_ENABLED = os.getenv("API_RATE_LIMIT_ENABLED", "true").lower() == "true"
_raw_rate_limit = os.getenv("API_RATE_LIMIT_PER_MINUTE", "60")
try:
    API_RATE_LIMIT_PER_MINUTE = int(_raw_rate_limit)
except ValueError:
    API_RATE_LIMIT_PER_MINUTE = 60
    logger.warning(
        f"Invalid API_RATE_LIMIT_PER_MINUTE '{_raw_rate_limit}', falling back to 60"
    )
API_RATE_LIMIT_PER_HOUR = int(os.getenv("API_RATE_LIMIT_PER_HOUR", 1000))
API_RATE_LIMIT_BURST = int(os.getenv("API_RATE_LIMIT_BURST", 10))

# Endpoint-specific rate limits
ENDPOINT_RATE_LIMITS = {
    "/api/v1/packages/resolve": os.getenv("RESOLVE_RATE_LIMIT", "10/minute"),
    "/api/v1/packages/export": os.getenv("EXPORT_RATE_LIMIT", "20/minute"),
    "/api/v1/system/benchmarks": os.getenv("BENCHMARK_RATE_LIMIT", "5/minute"),
    "/api/v1/health": os.getenv("HEALTH_RATE_LIMIT", "30/minute"),
}

# =============================================================================
# NEW: Monitoring & Observability
# =============================================================================
# Prometheus
PROMETHEUS_ENABLED = os.getenv("PROMETHEUS_ENABLED", "false").lower() == "true"
PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", 9090))

# Sentry
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", os.getenv("ENV", "development"))
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", 0.1))

# OpenTelemetry
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
OTEL_EXPORTER_OTLP_PROTOCOL = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
OTEL_EXPORTER_OTLP_HEADERS = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
OTEL_EXPORTER_OTLP_COMPRESSION = os.getenv("OTEL_EXPORTER_OTLP_COMPRESSION", "gzip")
OTEL_EXPORTER_OTLP_TIMEOUT = int(os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT", "10"))
OTEL_SAMPLER_TYPE = os.getenv("OTEL_SAMPLER_TYPE", "parentbased_traceidratio")
OTEL_SAMPLER_ARG = os.getenv("OTEL_SAMPLER_ARG", "0.1")
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "universal-dependency-resolver")
OTEL_SERVICE_VERSION = os.getenv("OTEL_SERVICE_VERSION", "1.0.0")
OTEL_RESOURCE_ATTRIBUTES = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")

# =============================================================================
# NEW: File Upload Configuration
# =============================================================================
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))  # 10MB default
ALLOWED_UPLOAD_EXTENSIONS = os.getenv(
    "ALLOWED_UPLOAD_EXTENSIONS", ".txt,.json,.yml,.yaml,.toml,.lock"
).split(",")
UPLOAD_TEMP_DIR = os.getenv("UPLOAD_TEMP_DIR", "/tmp/uploads")

# =============================================================================
# NEW: Background Tasks Configuration
# =============================================================================
CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379")
)
CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://localhost:6379")
)
CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", 300))  # 5 minutes
CELERY_TASK_SOFT_TIME_LIMIT = int(
    os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", 240)
)  # 4 minutes
CELERY_WORKER_CONCURRENCY = int(os.getenv("CELERY_WORKER_CONCURRENCY", 4))

# =============================================================================
# NEW: Email Configuration (for notifications)
# =============================================================================
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@depresolver.com")

# =============================================================================
# NEW: Webhook Configuration
# =============================================================================
WEBHOOK_ENABLED = os.getenv("WEBHOOK_ENABLED", "false").lower() == "true"
WEBHOOK_TIMEOUT = int(os.getenv("WEBHOOK_TIMEOUT", 10))
WEBHOOK_MAX_RETRIES = int(os.getenv("WEBHOOK_MAX_RETRIES", 3))


# =============================================================================
# NEW: Database Migration Configuration
# =============================================================================
AUTO_MIGRATE_ON_STARTUP = (
    os.getenv("AUTO_MIGRATE_ON_STARTUP", "false").lower() == "true"
)
MIGRATION_TIMEOUT = int(os.getenv("MIGRATION_TIMEOUT", 300))  # 5 minutes

# =============================================================================
# NEW: Health Check Configuration
# =============================================================================
HEALTH_CHECK_INCLUDE_DETAILS = (
    os.getenv("HEALTH_CHECK_INCLUDE_DETAILS", "true").lower() == "true"
)
HEALTH_CHECK_CACHE_TTL = int(os.getenv("HEALTH_CHECK_CACHE_TTL", 10))  # 10 seconds

# =============================================================================
# Database Configuration
# =============================================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://user:password@localhost:5432/depresolver"
)
_raw_pool_size = os.getenv("DATABASE_POOL_SIZE", "10")
try:
    DATABASE_POOL_SIZE = int(_raw_pool_size)
except ValueError:
    DATABASE_POOL_SIZE = 10
    logger.warning(f"Invalid DATABASE_POOL_SIZE '{_raw_pool_size}', falling back to 10")
DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", 20))
_raw_pool_timeout = os.getenv("DATABASE_POOL_TIMEOUT", "30")
try:
    DATABASE_POOL_TIMEOUT = int(_raw_pool_timeout)
except ValueError:
    DATABASE_POOL_TIMEOUT = 30
    logger.warning(
        f"Invalid DATABASE_POOL_TIMEOUT '{_raw_pool_timeout}', falling back to 30"
    )

# =============================================================================
# Redis Configuration
# =============================================================================
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", 50))
REDIS_DECODE_RESPONSES = os.getenv("REDIS_DECODE_RESPONSES", "true").lower() == "true"

# =============================================================================
# API Configurations - Package Registries
# =============================================================================
# PyPI
PYPI_URL = os.getenv("PYPI_URL", "https://pypi.org")
PYPI_SIMPLE_URL = os.getenv("PYPI_SIMPLE_URL", "https://pypi.org/simple")
PYPI_JSON_URL = os.getenv("PYPI_JSON_URL", "https://pypi.org/pypi")
PYPI_XMLRPC_URL = os.getenv("PYPI_XMLRPC_URL", "https://pypi.org/pypi")
PYPI_MIRROR_URLS = (
    os.getenv("PYPI_MIRROR_URLS", "").split(",")
    if os.getenv("PYPI_MIRROR_URLS")
    else []
)

# Conda
CONDA_URL = os.getenv("CONDA_URL", "https://repo.anaconda.com/pkgs/main")
CONDA_FORGE_URL = os.getenv("CONDA_FORGE_URL", "https://conda.anaconda.org/conda-forge")
CONDA_CHANNELS = {
    "defaults": os.getenv("CONDA_DEFAULTS_URL", "https://repo.anaconda.com/pkgs/main"),
    "conda-forge": os.getenv(
        "CONDA_FORGE_URL", "https://conda.anaconda.org/conda-forge"
    ),
    "pytorch": os.getenv("CONDA_PYTORCH_URL", "https://conda.anaconda.org/pytorch"),
    "nvidia": os.getenv("CONDA_NVIDIA_URL", "https://conda.anaconda.org/nvidia"),
    "bioconda": os.getenv("CONDA_BIOCONDA_URL", "https://conda.anaconda.org/bioconda"),
    "r": os.getenv("CONDA_R_URL", "https://conda.anaconda.org/r"),
}

# NPM
NPM_URL = os.getenv("NPM_URL", "https://registry.npmjs.org")
NPM_SEARCH_URL = os.getenv("NPM_SEARCH_URL", "https://registry.npmjs.org/-/v1/search")
NPM_DOWNLOADS_API = os.getenv("NPM_DOWNLOADS_API", "https://api.npmjs.org/downloads")
NPM_MIRROR_URLS = (
    os.getenv("NPM_MIRROR_URLS", "").split(",") if os.getenv("NPM_MIRROR_URLS") else []
)

# Maven
MAVEN_CENTRAL_URL = os.getenv("MAVEN_CENTRAL_URL", "https://repo1.maven.org/maven2")
MAVEN_SEARCH_URL = os.getenv(
    "MAVEN_SEARCH_URL", "https://search.maven.org/solrsearch/select"
)
MAVEN_ARTIFACT_URL = os.getenv(
    "MAVEN_ARTIFACT_URL", "https://search.maven.org/artifact"
)
MAVEN_ADDITIONAL_REPOS = (
    os.getenv("MAVEN_ADDITIONAL_REPOS", "").split(",")
    if os.getenv("MAVEN_ADDITIONAL_REPOS")
    else []
)

# Crates.io
CRATES_URL = os.getenv("CRATES_URL", "https://crates.io/api/v1")
CRATES_INDEX_URL = os.getenv(
    "CRATES_INDEX_URL", "https://github.com/rust-lang/crates.io-index"
)
CRATES_DL_URL = os.getenv("CRATES_DL_URL", "https://crates.io/api/v1/crates")

# RubyGems Configuration
RUBYGEMS_URL = os.getenv("RUBYGEMS_URL", "https://rubygems.org")
RUBYGEMS_API_URL = os.getenv("RUBYGEMS_API_URL", "https://rubygems.org/api/v1")

# NuGet Configuration
NUGET_URL = os.getenv("NUGET_URL", "https://www.nuget.org")
NUGET_API_URL = os.getenv("NUGET_API_URL", "https://api.nuget.org/v3/index.json")

# Packagist Configuration
PACKAGIST_URL = os.getenv("PACKAGIST_URL", "https://packagist.org")
PACKAGIST_API_URL = os.getenv("PACKAGIST_API_URL", "https://repo.packagist.org/p2")

# Homebrew Configuration
HOMEBREW_URL = os.getenv("HOMEBREW_URL", "https://brew.sh")
HOMEBREW_API_URL = os.getenv("HOMEBREW_API_URL", "https://formulae.brew.sh/api")

# Go Modules configuration
GOMODULES_PROXY_URL = os.getenv("GOMODULES_PROXY_URL", "https://proxy.golang.org")
GOMODULES_SUM_DB_URL = os.getenv("GOMODULES_SUM_DB_URL", "https://sum.golang.org")

# APT configuration
APT_REPOSITORIES = os.getenv(
    "APT_REPOSITORIES", "http://deb.debian.org/debian,http://archive.ubuntu.com/ubuntu"
).split(",")
APT_DISTRIBUTIONS = os.getenv("APT_DISTRIBUTIONS", "stable,testing,unstable").split(",")

# APK configuration
APK_REPOSITORIES = os.getenv(
    "APK_REPOSITORIES", "https://dl-cdn.alpinelinux.org/alpine/v3.18/main"
).split(",")
APK_BRANCHES = os.getenv("APK_BRANCHES", "v3.18,v3.17,edge").split(",")

# CocoaPods configuration
COCOAPODS_API_URL = os.getenv("COCOAPODS_API_URL", "https://trunk.cocoapods.org/api/v1")
COCOAPODS_SPECS_URL = os.getenv("COCOAPODS_SPECS_URL", "https://cdn.cocoapods.org")

# =============================================================================
# Cache Configuration
# =============================================================================
CACHE_TTL = int(os.getenv("CACHE_TTL", 3600))  # 1 hour default
CACHE_TTL_SHORT = int(
    os.getenv("CACHE_TTL_SHORT", 300)
)  # 5 minutes for frequently changing data
CACHE_TTL_LONG = int(os.getenv("CACHE_TTL_LONG", 86400))  # 24 hours for stable data
CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", 1000))
CACHE_EVICTION_POLICY = os.getenv("CACHE_EVICTION_POLICY", "LRU")  # LRU, LFU, FIFO

# Specific cache TTLs
PACKAGE_INFO_CACHE_TTL = int(os.getenv("PACKAGE_INFO_CACHE_TTL", CACHE_TTL))
VERSION_LIST_CACHE_TTL = int(os.getenv("VERSION_LIST_CACHE_TTL", CACHE_TTL_SHORT))
SEARCH_CACHE_TTL = int(os.getenv("SEARCH_CACHE_TTL", CACHE_TTL_SHORT))
DEPENDENCY_CACHE_TTL = int(os.getenv("DEPENDENCY_CACHE_TTL", CACHE_TTL))
COMPATIBILITY_CACHE_TTL = int(os.getenv("COMPATIBILITY_CACHE_TTL", CACHE_TTL_LONG))

# =============================================================================
# Rate Limiting Configuration
# =============================================================================
MAX_REQUEST_SIZE = int(os.getenv("MAX_REQUEST_SIZE", 10 * 1024 * 1024))  # 10MB default
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_DELAY = float(os.getenv("RATE_LIMIT_DELAY", 0.1))  # Seconds between requests
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_BACKOFF_FACTOR = float(os.getenv("RETRY_BACKOFF_FACTOR", 2.0))
RETRY_MAX_DELAY = float(os.getenv("RETRY_MAX_DELAY", 60.0))

# Circuit Breaker Configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(
    os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
)
CIRCUIT_BREAKER_OPEN_TIME = int(os.getenv("CIRCUIT_BREAKER_OPEN_TIME", "30"))

# Per-service rate limits (requests per minute)
RATE_LIMITS = {
    "pypi": int(os.getenv("PYPI_RATE_LIMIT", 600)),
    "npm": int(os.getenv("NPM_RATE_LIMIT", 600)),
    "conda": int(os.getenv("CONDA_RATE_LIMIT", 300)),
    "maven": int(os.getenv("MAVEN_RATE_LIMIT", 300)),
    "crates": int(os.getenv("CRATES_RATE_LIMIT", 300)),
    "github": int(os.getenv("GITHUB_RATE_LIMIT", 60)),
}

# =============================================================================
# HTTP Client Configuration
# =============================================================================
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 30))
CONNECT_TIMEOUT = int(os.getenv("CONNECT_TIMEOUT", 10))
READ_TIMEOUT = int(os.getenv("READ_TIMEOUT", 30))
MAX_CONNECTIONS = int(os.getenv("MAX_CONNECTIONS", 100))
MAX_KEEPALIVE_CONNECTIONS = int(os.getenv("MAX_KEEPALIVE_CONNECTIONS", 20))
HTTP_CLIENT_TIMEOUT = int(os.getenv("HTTP_CLIENT_TIMEOUT", 30))
HTTP_CLIENT_MAX_REDIRECTS = int(os.getenv("HTTP_CLIENT_MAX_REDIRECTS", 5))
HTTP_CLIENT_RETRY_DELAY = int(os.getenv("HTTP_CLIENT_RETRY_DELAY", 5))
HTTP_CLIENT_RETRY_COUNT = int(os.getenv("HTTP_CLIENT_RETRY_COUNT", 3))

# User agents for different services
USER_AGENTS = {
    "default": os.getenv("DEFAULT_USER_AGENT", "UniversalDependencyResolver/1.0"),
    "pypi": os.getenv(
        "PYPI_USER_AGENT", "UniversalDependencyResolver/1.0 (PyPI Client)"
    ),
    "npm": os.getenv("NPM_USER_AGENT", "UniversalDependencyResolver/1.0 (NPM Client)"),
    "documentation": os.getenv(
        "DOC_USER_AGENT", "Mozilla/5.0 (compatible; DocScraper/1.0)"
    ),
}

# =============================================================================
# Logging Configuration
# =============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv(
    "LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOG_DATE_FORMAT = os.getenv("LOG_DATE_FORMAT", "%Y-%m-%d %H:%M:%S")
LOG_FILE = os.getenv("LOG_FILE", None)
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 10485760))  # 10MB
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))

# Enable/disable specific loggers
ENABLE_REQUEST_LOGGING = os.getenv("ENABLE_REQUEST_LOGGING", "false").lower() == "true"
ENABLE_CACHE_LOGGING = os.getenv("ENABLE_CACHE_LOGGING", "false").lower() == "true"
ENABLE_PERFORMANCE_LOGGING = (
    os.getenv("ENABLE_PERFORMANCE_LOGGING", "true").lower() == "true"
)

# =============================================================================
# Supported Ecosystems
# =============================================================================
ECOSYSTEMS = [
    "pypi", "conda", "npm", "crates", "maven",
    "gomodules", "apt", "apk", "cocoapods",
    "homebrew", "nuget", "packagist", "rubygems",
    "docs", "custom_db",
]
ENABLED_ECOSYSTEMS = os.getenv("ENABLED_ECOSYSTEMS", ",".join(ECOSYSTEMS)).split(",")

# Ecosystem display names
ECOSYSTEM_NAMES = {
    "pypi": "PyPI (Python)",
    "conda": "Conda",
    "npm": "NPM (Node.js)",
    "crates": "Crates.io (Rust)",
    "maven": "Maven (Java)",
    "gomodules": "Go Modules",
    "apt": "APT (Debian)",
    "apk": "APK (Alpine)",
    "cocoapods": "CocoaPods (iOS)",
    "homebrew": "Homebrew (macOS)",
    "nuget": "NuGet (.NET)",
    "packagist": "Packagist (PHP)",
    "rubygems": "RubyGems",
    "docs": "Documentation",
    "custom_db": "Custom Database",
}

# =============================================================================
# Export Formats Configuration
# =============================================================================
EXPORT_FORMATS = [
    "requirements.txt",
    "package.json",
    "environment.yml",
    "pyproject.toml",
    "Dockerfile",
    "docker-compose.yml",
    "install.sh",
    "install.bat",
    "CMakeLists.txt",
    "Cargo.toml",
    "build.gradle",
    "pom.xml",

]

ENABLED_EXPORT_FORMATS = os.getenv(
    "ENABLED_EXPORT_FORMATS", ",".join(EXPORT_FORMATS)
).split(",")

# Export format metadata
EXPORT_FORMAT_METADATA = {
    "requirements.txt": {"ecosystem": "pypi", "description": "Python pip requirements"},
    "package.json": {"ecosystem": "npm", "description": "Node.js NPM manifest"},
    "environment.yml": {"ecosystem": "conda", "description": "Conda environment file"},
    "pyproject.toml": {
        "ecosystem": "pypi",
        "description": "Python Poetry/PEP 517 config",
    },
    "Dockerfile": {"ecosystem": "multi", "description": "Docker container definition"},
    "docker-compose.yml": {
        "ecosystem": "multi",
        "description": "Docker Compose config",
    },
    "install.sh": {"ecosystem": "multi", "description": "Shell installation script"},
    "install.bat": {"ecosystem": "multi", "description": "Windows batch script"},
    "CMakeLists.txt": {
        "ecosystem": "conan",
        "description": "CMake build configuration",
    },
    "Cargo.toml": {"ecosystem": "crates", "description": "Rust Cargo manifest"},
    "build.gradle": {"ecosystem": "maven", "description": "Gradle build file"},
    "pom.xml": {"ecosystem": "maven", "description": "Maven POM file"},
}

# =============================================================================
# Security Configuration
# =============================================================================
ENABLE_SECURITY_SCANNING = (
    os.getenv("ENABLE_SECURITY_SCANNING", "true").lower() == "true"
)
VULNERABILITY_CHECK_ENABLED = (
    os.getenv("VULNERABILITY_CHECK_ENABLED", "true").lower() == "true"
)
LICENSE_CHECK_ENABLED = os.getenv("LICENSE_CHECK_ENABLED", "true").lower() == "true"

# Allowed/blocked licenses
ALLOWED_LICENSES = os.getenv(
    "ALLOWED_LICENSES", "MIT,Apache-2.0,BSD-3-Clause,BSD-2-Clause,ISC,GPL-3.0"
).split(",")
BLOCKED_LICENSES = (
    os.getenv("BLOCKED_LICENSES", "").split(",")
    if os.getenv("BLOCKED_LICENSES")
    else []
)

# Security API endpoints
VULNERABILITY_DB_URL = os.getenv(
    "VULNERABILITY_DB_URL", "https://nvd.nist.gov/feeds/json/cve/1.1"
)
OSV_API_URL = os.getenv("OSV_API_URL", "https://api.osv.dev/v1/query")

# =============================================================================
# Performance Configuration
# =============================================================================
ENABLE_PERFORMANCE_MONITORING = (
    os.getenv("ENABLE_PERFORMANCE_MONITORING", "true").lower() == "true"
)
SLOW_REQUEST_THRESHOLD = float(os.getenv("SLOW_REQUEST_THRESHOLD", 5.0))  # Seconds
ENABLE_QUERY_OPTIMIZATION = (
    os.getenv("ENABLE_QUERY_OPTIMIZATION", "true").lower() == "true"
)

# Parallel processing
MAX_PARALLEL_REQUESTS = int(os.getenv("MAX_PARALLEL_REQUESTS", 10))
MAX_PARALLEL_DOWNLOADS = int(os.getenv("MAX_PARALLEL_DOWNLOADS", 5))
THREAD_POOL_SIZE = int(os.getenv("THREAD_POOL_SIZE", 20))

# =============================================================================
# Feature Flags
# =============================================================================
ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() == "true"
FEATURES = {
    "ENABLE_CACHE": ENABLE_CACHE,
    "ENABLE_ASYNC": os.getenv("ENABLE_ASYNC", "true").lower() == "true",
    "ENABLE_METRICS": os.getenv("ENABLE_METRICS", "true").lower() == "true",
    "ENABLE_PROFILING": os.getenv("ENABLE_PROFILING", "false").lower() == "true",
    "ENABLE_DEBUG_MODE": os.getenv("ENABLE_DEBUG_MODE", "false").lower() == "true",
    "ENABLE_EXPERIMENTAL_FEATURES": os.getenv(
        "ENABLE_EXPERIMENTAL_FEATURES", "false"
    ).lower()
    == "true",
    "ENABLE_DEPENDENCY_GRAPH": os.getenv("ENABLE_DEPENDENCY_GRAPH", "true").lower()
    == "true",
    "ENABLE_AUTO_UPDATE": os.getenv("ENABLE_AUTO_UPDATE", "false").lower() == "true",
    "ENABLE_TELEMETRY": os.getenv("ENABLE_TELEMETRY", "false").lower() == "true",
    "ENABLE_AUTH": os.getenv("ENABLE_AUTH", "false").lower() == "true",
    "ENABLE_WEBHOOKS": os.getenv("ENABLE_WEBHOOKS", "false").lower() == "true",
    "ENABLE_EMAIL_NOTIFICATIONS": os.getenv(
        "ENABLE_EMAIL_NOTIFICATIONS", "false"
    ).lower()
    == "true",
    "ENABLE_BACKGROUND_TASKS": os.getenv("ENABLE_BACKGROUND_TASKS", "true").lower()
    == "true",
    "ENABLE_FILE_UPLOADS": os.getenv("ENABLE_FILE_UPLOADS", "true").lower() == "true",
    "ENABLE_API_VERSIONING": os.getenv("ENABLE_API_VERSIONING", "true").lower()
    == "true",
    "ENABLE_RESPONSE_COMPRESSION": os.getenv(
        "ENABLE_RESPONSE_COMPRESSION", "true"
    ).lower()
    == "true",
    "ENABLE_CSRF": os.getenv("ENABLE_CSRF", "true").lower() == "true",
}

# =============================================================================
# System Scanner Configuration
# =============================================================================
SYSTEM_SCAN_TIMEOUT = int(os.getenv("SYSTEM_SCAN_TIMEOUT", 60))
ENABLE_GPU_DETECTION = os.getenv("ENABLE_GPU_DETECTION", "true").lower() == "true"
ENABLE_CONTAINER_DETECTION = (
    os.getenv("ENABLE_CONTAINER_DETECTION", "true").lower() == "true"
)
ENABLE_PACKAGE_SCANNING = os.getenv("ENABLE_PACKAGE_SCANNING", "true").lower() == "true"

# =============================================================================
# Default Values
# =============================================================================
DEFAULT_PYTHON_VERSION = os.getenv("DEFAULT_PYTHON_VERSION", "3.9")
DEFAULT_NODE_VERSION = os.getenv("DEFAULT_NODE_VERSION", "18")
DEFAULT_JAVA_VERSION = os.getenv("DEFAULT_JAVA_VERSION", "17")
DEFAULT_RUST_VERSION = os.getenv("DEFAULT_RUST_VERSION", "stable")

# =============================================================================
# API Response Configuration
# =============================================================================
MAX_RESPONSE_SIZE = int(os.getenv("MAX_RESPONSE_SIZE", 10485760))  # 10MB
PAGINATION_DEFAULT_LIMIT = int(os.getenv("PAGINATION_DEFAULT_LIMIT", 20))
PAGINATION_MAX_LIMIT = int(os.getenv("PAGINATION_MAX_LIMIT", 100))

# =============================================================================
# WebSocket Configuration
# =============================================================================
WEBSOCKET_ENABLED = os.getenv("WEBSOCKET_ENABLED", "true").lower() == "true"
SOCKETIO_ENABLED = os.getenv("SOCKETIO_ENABLED", "true").lower() == "true"
REALTIME_MAX_CONNECTIONS = int(os.getenv("REALTIME_MAX_CONNECTIONS", 100))

# =============================================================================
# Documentation Scraper Configuration
# =============================================================================
DOC_SCRAPER_ENABLED = os.getenv("DOC_SCRAPER_ENABLED", "true").lower() == "true"
DOC_SCRAPER_TIMEOUT = int(os.getenv("DOC_SCRAPER_TIMEOUT", 30))
DOC_SCRAPER_MAX_PAGES = int(os.getenv("DOC_SCRAPER_MAX_PAGES", 10))
DOC_SCRAPER_FOLLOW_REDIRECTS = (
    os.getenv("DOC_SCRAPER_FOLLOW_REDIRECTS", "true").lower() == "true"
)

# Known documentation URLs - COMPLETE LIST
KNOWN_DOC_URLS = {
    "tensorflow": os.getenv(
        "TENSORFLOW_DOCS_URL", "https://www.tensorflow.org/install"
    ),
    "pytorch": os.getenv(
        "PYTORCH_DOCS_URL", "https://pytorch.org/get-started/locally/"
    ),
    "tensorrt": os.getenv(
        "TENSORRT_DOCS_URL",
        "https://docs.nvidia.com/deeplearning/tensorrt/install-guide/index.html",
    ),
    "opencv": os.getenv(
        "OPENCV_DOCS_URL",
        "https://docs.opencv.org/master/d7/d9f/tutorial_linux_install.html",
    ),
    "cuda": os.getenv(
        "CUDA_DOCS_URL",
        "https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html",
    ),
    "numpy": os.getenv("NUMPY_DOCS_URL", "https://numpy.org/install/"),
    "pandas": os.getenv(
        "PANDAS_DOCS_URL", "https://pandas.pydata.org/docs/getting_started/install.html"
    ),
    "scikit-learn": os.getenv(
        "SKLEARN_DOCS_URL", "https://scikit-learn.org/stable/install.html"
    ),
    "keras": os.getenv("KERAS_DOCS_URL", "https://keras.io/getting_started/"),
    "mxnet": os.getenv(
        "MXNET_DOCS_URL", "https://mxnet.apache.org/versions/1.9.1/get_started"
    ),
    "jax": os.getenv("JAX_DOCS_URL", "https://github.com/google/jax#installation"),
    "transformers": os.getenv(
        "TRANSFORMERS_DOCS_URL", "https://huggingface.co/docs/transformers/installation"
    ),
    "fastai": os.getenv("FASTAI_DOCS_URL", "https://docs.fast.ai/#Installing"),
    "lightgbm": os.getenv(
        "LIGHTGBM_DOCS_URL",
        "https://lightgbm.readthedocs.io/en/latest/Installation-Guide.html",
    ),
    "xgboost": os.getenv(
        "XGBOOST_DOCS_URL", "https://xgboost.readthedocs.io/en/stable/install.html"
    ),
}

# Additional documentation URLs that can be added
ADDITIONAL_DOC_URLS = {
    "scipy": os.getenv("SCIPY_DOCS_URL", "https://scipy.org/install/"),
    "matplotlib": os.getenv(
        "MATPLOTLIB_DOCS_URL",
        "https://matplotlib.org/stable/users/installing/index.html",
    ),
    "seaborn": os.getenv(
        "SEABORN_DOCS_URL", "https://seaborn.pydata.org/installing.html"
    ),
    "plotly": os.getenv(
        "PLOTLY_DOCS_URL", "https://plotly.com/python/getting-started/"
    ),
    "spacy": os.getenv("SPACY_DOCS_URL", "https://spacy.io/usage"),
    "nltk": os.getenv("NLTK_DOCS_URL", "https://www.nltk.org/install.html"),
    "gensim": os.getenv(
        "GENSIM_DOCS_URL", "https://radimrehurek.com/gensim/install.html"
    ),
    "opencv-python": os.getenv(
        "OPENCV_PYTHON_DOCS_URL", "https://pypi.org/project/opencv-python/"
    ),
    "pillow": os.getenv(
        "PILLOW_DOCS_URL", "https://pillow.readthedocs.io/en/stable/installation.html"
    ),
    "requests": os.getenv(
        "REQUESTS_DOCS_URL", "https://requests.readthedocs.io/en/latest/user/install/"
    ),
    "flask": os.getenv(
        "FLASK_DOCS_URL", "https://flask.palletsprojects.com/en/2.3.x/installation/"
    ),
    "django": os.getenv(
        "DJANGO_DOCS_URL", "https://docs.djangoproject.com/en/stable/topics/install/"
    ),
    "fastapi": os.getenv("FASTAPI_DOCS_URL", "https://fastapi.tiangolo.com/tutorial/"),
    "streamlit": os.getenv(
        "STREAMLIT_DOCS_URL",
        "https://docs.streamlit.io/library/get-started/installation",
    ),
    "gradio": os.getenv("GRADIO_DOCS_URL", "https://www.gradio.app/guides/quickstart"),
}

# Merge additional URLs if needed
if os.getenv("INCLUDE_ADDITIONAL_DOC_URLS", "false").lower() == "true":
    KNOWN_DOC_URLS.update(ADDITIONAL_DOC_URLS)

# =============================================================================
# Error Messages
# =============================================================================
ERROR_MESSAGES = {
    "PACKAGE_NOT_FOUND": "Package {package} not found in {ecosystem}",
    "VERSION_NOT_FOUND": "Version {version} not found for package {package}",
    "ECOSYSTEM_NOT_SUPPORTED": "Ecosystem {ecosystem} is not supported",
    "RATE_LIMIT_EXCEEDED": "Rate limit exceeded for {service}. Please try again later.",
    "INVALID_VERSION_SPEC": "Invalid version specification: {spec}",
    "DEPENDENCY_RESOLUTION_FAILED": "Failed to resolve dependencies for {package}",
    "EXPORT_FORMAT_NOT_SUPPORTED": "Export format {format} is not supported",
}

# =============================================================================
# Development/Production Settings
# =============================================================================
ENV = os.getenv("ENV", "development")
DEBUG = os.getenv("DEBUG", "false").lower() == "true" or ENV == "development"
TESTING = os.getenv("TESTING", "false").lower() == "true"

if DEBUG:
    LOG_LEVEL = "DEBUG"
    ENABLE_REQUEST_LOGGING = True
    ENABLE_CACHE_LOGGING = True

# =============================================================================
# Settings namespace for backward-compatible imports
# =============================================================================
settings = {k: v for k, v in globals().items() if k.isupper()}


def validate_settings() -> list[str]:
    """Validate critical settings and return a list of configuration warnings.

    Catches common misconfigurations that would otherwise surface as
    cryptic runtime errors. Call this at startup.
    """
    warnings: list[str] = []

    if SECRET_KEY == "your-secret-key-here-change-in-production":
        if ENV == "production":
            raise RuntimeError(
                "SECRET_KEY is still the default value — set a strong random secret in production"
            )
        warnings.append(
            "SECRET_KEY is still the default value — rotate it immediately in production"
        )

    if ENV == "production" and not FEATURES.get("ENABLE_AUTH"):
        warnings.append(
            "ENABLE_AUTH is false in production — authentication is disabled"
        )

    if DATABASE_URL.startswith("sqlite"):
        warnings.append(
            f"Using SQLite ({DATABASE_URL}) — not suitable for production workloads"
        )

    if OTEL_EXPORTER_OTLP_ENDPOINT and not OTEL_EXPORTER_OTLP_ENDPOINT.startswith(
        ("http://", "https://")
    ):
        warnings.append(
            f"OTEL_EXPORTER_OTLP_ENDPOINT does not look like a URL: {OTEL_EXPORTER_OTLP_ENDPOINT}"
        )

    try:
        rate = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "60"))
        if rate < 1:
            warnings.append(f"API_RATE_LIMIT_PER_MINUTE is {rate} — must be >= 1")
    except (ValueError, TypeError):
        warnings.append(
            f"API_RATE_LIMIT_PER_MINUTE is not a valid integer: {os.getenv('API_RATE_LIMIT_PER_MINUTE')}"
        )

    try:
        pool = int(os.getenv("DATABASE_POOL_SIZE", "10"))
        if pool < 1:
            warnings.append(f"DATABASE_POOL_SIZE is {pool} — must be >= 1")
    except (ValueError, TypeError):
        warnings.append(
            f"DATABASE_POOL_SIZE is not a valid integer: {os.getenv('DATABASE_POOL_SIZE')}"
        )

    for w in warnings:
        logger.warning(f"Config: {w}")

    return warnings


# =============================================================================
# Helper Functions
# =============================================================================
def get_cache_key(prefix: str, *args) -> str:
    """Generate a cache key from prefix and arguments"""
    parts = [prefix] + [str(arg) for arg in args]
    return ":".join(parts)


def get_ecosystem_config(ecosystem: str) -> Dict[str, Any]:
    """Get configuration for a specific ecosystem"""
    configs = {
        "pypi": {
            "url": PYPI_URL,
            "api_url": PYPI_JSON_URL,
            "cache_ttl": PACKAGE_INFO_CACHE_TTL,
            "rate_limit": RATE_LIMITS.get("pypi", 600),
        },
        "npm": {
            "url": NPM_URL,
            "api_url": NPM_URL,
            "cache_ttl": PACKAGE_INFO_CACHE_TTL,
            "rate_limit": RATE_LIMITS.get("npm", 600),
        },
        "rubygems": {
            "url": RUBYGEMS_URL,
            "api_url": RUBYGEMS_API_URL,
            "cache_ttl": CACHE_TTL,
            "rate_limit": RATE_LIMITS.get("rubygems", 600),
        },
        "nuget": {
            "url": NUGET_URL,
            "api_url": NUGET_API_URL,
            "cache_ttl": CACHE_TTL,
            "rate_limit": RATE_LIMITS.get("nuget", 600),
        },
        "packagist": {
            "url": PACKAGIST_URL,
            "api_url": PACKAGIST_API_URL,
            "cache_ttl": CACHE_TTL,
            "rate_limit": RATE_LIMITS.get("packagist", 600),
        },
        "homebrew": {
            "url": HOMEBREW_URL,
            "api_url": HOMEBREW_API_URL,
            "cache_ttl": CACHE_TTL,
            "rate_limit": RATE_LIMITS.get("homebrew", 600),
        },
        "conda": {
            "url": CONDA_URL,
            "channels": CONDA_CHANNELS,
            "cache_ttl": PACKAGE_INFO_CACHE_TTL,
            "rate_limit": RATE_LIMITS.get("conda", 300),
        },
        "maven": {
            "url": MAVEN_CENTRAL_URL,
            "search_url": MAVEN_SEARCH_URL,
            "cache_ttl": PACKAGE_INFO_CACHE_TTL,
            "rate_limit": RATE_LIMITS.get("maven", 300),
        },
        "crates": {
            "url": CRATES_URL,
            "cache_ttl": PACKAGE_INFO_CACHE_TTL,
            "rate_limit": RATE_LIMITS.get("crates", 300),
        },
        "gomodules": {
            "url": GOMODULES_PROXY_URL,
            "sum_db_url": GOMODULES_SUM_DB_URL,
            "cache_ttl": CACHE_TTL,
            "rate_limit": 600,
        },
        "apt": {
            "repositories": APT_REPOSITORIES,
            "distributions": APT_DISTRIBUTIONS,
            "cache_ttl": CACHE_TTL * 2,  # Longer cache for system packages
            "rate_limit": 300,
        },
        "apk": {
            "repositories": APK_REPOSITORIES,
            "branches": APK_BRANCHES,
            "cache_ttl": CACHE_TTL * 2,
            "rate_limit": 300,
        },
        "cocoapods": {
            "url": COCOAPODS_API_URL,
            "specs_url": COCOAPODS_SPECS_URL,
            "cache_ttl": CACHE_TTL,
            "rate_limit": 600,
        },
    }
    return configs.get(ecosystem, {})
