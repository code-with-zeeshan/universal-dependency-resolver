# settings/__init__.py
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# =============================================================================
# Authentication & Security
# =============================================================================
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")
ENABLE_API_KEY_AUTH = os.getenv("ENABLE_API_KEY_AUTH", "false").lower() == "true"

# =============================================================================
# HTTP Client Configuration
# =============================================================================
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_BACKOFF_FACTOR = float(os.getenv("RETRY_BACKOFF_FACTOR", 2.0))
RETRY_MAX_DELAY = float(os.getenv("RETRY_MAX_DELAY", 60.0))
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(
    os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
)
CIRCUIT_BREAKER_OPEN_TIME = int(os.getenv("CIRCUIT_BREAKER_OPEN_TIME", "30"))

RATE_LIMITS = {
    "pypi": int(os.getenv("PYPI_RATE_LIMIT", 600)),
    "npm": int(os.getenv("NPM_RATE_LIMIT", 600)),
    "conda": int(os.getenv("CONDA_RATE_LIMIT", 300)),
    "maven": int(os.getenv("MAVEN_RATE_LIMIT", 300)),
    "crates": int(os.getenv("CRATES_RATE_LIMIT", 300)),
    "github": int(os.getenv("GITHUB_RATE_LIMIT", 60)),
}

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 30))

USER_AGENTS = {
    "default": os.getenv("DEFAULT_USER_AGENT", "UniversalDependencyResolver/1.0"),
    "pypi": os.getenv("PYPI_USER_AGENT", "UniversalDependencyResolver/1.0 (PyPI Client)"),
    "npm": os.getenv("NPM_USER_AGENT", "UniversalDependencyResolver/1.0 (NPM Client)"),
    "documentation": os.getenv("DOC_USER_AGENT", "Mozilla/5.0 (compatible; DocScraper/1.0)"),
}

# =============================================================================
# Logging Configuration
# =============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENABLE_REQUEST_LOGGING = os.getenv("ENABLE_REQUEST_LOGGING", "false").lower() == "true"
ENABLE_PERFORMANCE_LOGGING = (
    os.getenv("ENABLE_PERFORMANCE_LOGGING", "true").lower() == "true"
)
SLOW_REQUEST_THRESHOLD = float(os.getenv("SLOW_REQUEST_THRESHOLD", 5.0))

# =============================================================================
# Database Configuration
# =============================================================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./udr.db")

# =============================================================================
# Redis Configuration
# =============================================================================
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# =============================================================================
# Cache Configuration
# =============================================================================
CACHE_TTL = int(os.getenv("CACHE_TTL", 3600))
CACHE_TTL_SHORT = int(os.getenv("CACHE_TTL_SHORT", 300))
MAX_REQUEST_SIZE = int(os.getenv("MAX_REQUEST_SIZE", 10 * 1024 * 1024))
PROMETHEUS_ENABLED = os.getenv("PROMETHEUS_ENABLED", "false").lower() == "true"

# =============================================================================
# Supported Ecosystems & Export Formats
# =============================================================================
ECOSYSTEMS = [
    "pypi", "conda", "npm", "crates", "maven",
    "gomodules", "apt", "apk", "cocoapods",
    "homebrew", "nuget", "packagist", "rubygems",
    "docs", "custom_db",
]
ECOSYSTEM_NAMES = {
    "pypi": "PyPI (Python)", "conda": "Conda", "npm": "NPM (Node.js)",
    "crates": "Crates.io (Rust)", "maven": "Maven (Java)", "gomodules": "Go Modules",
    "apt": "APT (Debian)", "apk": "APK (Alpine)", "cocoapods": "CocoaPods (iOS)",
    "homebrew": "Homebrew (macOS)", "nuget": "NuGet (.NET)", "packagist": "Packagist (PHP)",
    "rubygems": "RubyGems", "docs": "Documentation", "custom_db": "Custom Database",
}
EXPORT_FORMAT_METADATA = {
    "requirements.txt": {"ecosystem": "pypi", "description": "Python pip requirements"},
    "package.json": {"ecosystem": "npm", "description": "Node.js NPM manifest"},
    "environment.yml": {"ecosystem": "conda", "description": "Conda environment file"},
    "pyproject.toml": {"ecosystem": "pypi", "description": "Python Poetry/PEP 517 config"},
    "Dockerfile": {"ecosystem": "multi", "description": "Docker container definition"},
    "docker-compose.yml": {"ecosystem": "multi", "description": "Docker Compose config"},
    "install.sh": {"ecosystem": "multi", "description": "Shell installation script"},
    "install.bat": {"ecosystem": "multi", "description": "Windows batch script"},
    "CMakeLists.txt": {"ecosystem": "conan", "description": "CMake build configuration"},
    "Cargo.toml": {"ecosystem": "crates", "description": "Rust Cargo manifest"},
    "build.gradle": {"ecosystem": "maven", "description": "Gradle build file"},
    "pom.xml": {"ecosystem": "maven", "description": "Maven POM file"},
}

OSV_API_URL = os.getenv("OSV_API_URL", "https://api.osv.dev/v1/query")

# =============================================================================
# Feature Flags
# =============================================================================
ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() == "true"
FEATURES = {
    "ENABLE_CACHE": ENABLE_CACHE,
    "ENABLE_METRICS": os.getenv("ENABLE_METRICS", "true").lower() == "true",
    "ENABLE_AUTH": os.getenv("ENABLE_AUTH", "false").lower() == "true",
    "ENABLE_RESPONSE_COMPRESSION": os.getenv("ENABLE_RESPONSE_COMPRESSION", "true").lower() == "true",
    "ENABLE_CSRF": os.getenv("ENABLE_CSRF", "true").lower() == "true",
}

ENV = os.getenv("ENV", "development")

if os.getenv("DEBUG", "false").lower() == "true" or ENV == "development":
    LOG_LEVEL = "DEBUG"
    ENABLE_REQUEST_LOGGING = True


def validate_settings() -> list[str]:
    """Validate critical settings and return a list of configuration warnings."""
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
        warnings.append("ENABLE_AUTH is false in production — authentication is disabled")

    if DATABASE_URL.startswith("sqlite"):
        warnings.append(f"Using SQLite ({DATABASE_URL}) — not suitable for production workloads")

    for w in warnings:
        logger.warning(f"Config: {w}")
    return warnings


def get_ecosystem_config(ecosystem: str) -> Dict[str, Any]:
    configs = {
        "pypi": {
            "url": "https://pypi.org", "api_url": "https://pypi.org/pypi",
            "cache_ttl": CACHE_TTL, "rate_limit": RATE_LIMITS.get("pypi", 600),
        },
        "npm": {
            "url": "https://registry.npmjs.org", "api_url": "https://registry.npmjs.org",
            "cache_ttl": CACHE_TTL, "rate_limit": RATE_LIMITS.get("npm", 600),
        },
        "rubygems": {
            "url": "https://rubygems.org", "api_url": "https://rubygems.org/api/v1",
            "cache_ttl": CACHE_TTL, "rate_limit": RATE_LIMITS.get("rubygems", 600),
        },
        "nuget": {
            "url": "https://www.nuget.org", "api_url": "https://api.nuget.org/v3/index.json",
            "cache_ttl": CACHE_TTL, "rate_limit": RATE_LIMITS.get("nuget", 600),
        },
        "packagist": {
            "url": "https://packagist.org", "api_url": "https://repo.packagist.org/p2",
            "cache_ttl": CACHE_TTL, "rate_limit": RATE_LIMITS.get("packagist", 600),
        },
        "homebrew": {
            "url": "https://brew.sh", "api_url": "https://formulae.brew.sh/api",
            "cache_ttl": CACHE_TTL, "rate_limit": RATE_LIMITS.get("homebrew", 600),
        },
        "conda": {
            "url": "https://repo.anaconda.com/pkgs/main", "channels": {
                "defaults": "https://repo.anaconda.com/pkgs/main",
                "conda-forge": "https://conda.anaconda.org/conda-forge",
            },
            "cache_ttl": CACHE_TTL, "rate_limit": RATE_LIMITS.get("conda", 300),
        },
        "maven": {
            "url": "https://repo1.maven.org/maven2", "search_url": "https://search.maven.org/solrsearch/select",
            "cache_ttl": CACHE_TTL, "rate_limit": RATE_LIMITS.get("maven", 300),
        },
        "crates": {
            "url": "https://crates.io/api/v1",
            "cache_ttl": CACHE_TTL, "rate_limit": RATE_LIMITS.get("crates", 300),
        },
        "gomodules": {
            "url": "https://proxy.golang.org", "sum_db_url": "https://sum.golang.org",
            "cache_ttl": CACHE_TTL, "rate_limit": 600,
        },
        "apt": {
            "repositories": "http://deb.debian.org/debian,http://archive.ubuntu.com/ubuntu".split(","),
            "distributions": "stable,testing,unstable".split(","),
            "cache_ttl": CACHE_TTL * 2, "rate_limit": 300,
        },
        "apk": {
            "repositories": "https://dl-cdn.alpinelinux.org/alpine/v3.18/main".split(","),
            "branches": "v3.18,v3.17,edge".split(","),
            "cache_ttl": CACHE_TTL * 2, "rate_limit": 300,
        },
        "cocoapods": {
            "url": "https://trunk.cocoapods.org/api/v1", "specs_url": "https://cdn.cocoapods.org",
            "cache_ttl": CACHE_TTL, "rate_limit": 600,
        },
    }
    return configs.get(ecosystem, {})
