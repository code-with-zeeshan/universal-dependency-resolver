"""Module docstring."""

# settings/__init__.py
import logging
import os as _os
import secrets
from typing import Any, Callable

logger = logging.getLogger(__name__)

# =============================================================================
# Static (non-env-var-derived) constants — evaluated once at import time
# =============================================================================

ECOSYSTEM_AUTH_ENV_PREFIXES = {
    "pypi": "PYPI",
    "npm": "NPM",
    "crates": "CRATES",
    "gomodules": "GOMODULES",
    "maven": "MAVEN",
    "nuget": "NUGET",
    "rubygems": "RUBYGEMS",
    "conda": "CONDA",
    "packagist": "PACKAGIST",
    "pub": "PUB",
    "gradle": "GRADLE",
    "swift": "SWIFT",
    "hex": "HEX",
    "haskell": "HASKELL",
    "cocoapods": "COCOAPODS",
    "homebrew": "HOMEBREW",
    "apt": "APT",
    "apk": "APK",
    "vcpkg": "VCPKG",
    "conan": "CONAN",
    "helm": "HELM",
    "terraform": "TERRAFORM",
}

ECOSYSTEMS = [
    "pypi",
    "conda",
    "npm",
    "crates",
    "maven",
    "gomodules",
    "apt",
    "apk",
    "cocoapods",
    "homebrew",
    "nuget",
    "packagist",
    "rubygems",
    "pub",
    "gradle",
    "swift",
    "hex",
    "haskell",
    "nix",
    "guix",
    "docs",
    "custom_db",
]
ACTIVE_ECOSYSTEMS = [e for e in ECOSYSTEMS if e not in ("docs", "custom_db")]
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
    "pub": "Pub (Dart/Flutter)",
    "gradle": "Gradle (Groovy/Kotlin DSL)",
    "swift": "Swift Package Manager",
    "hex": "Hex (Elixir)",
    "haskell": "Haskell (Cabal)",
    "nix": "Nix",
    "guix": "GNU Guix",
    "docs": "Documentation",
    "custom_db": "Custom Database",
}
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
    "build.gradle": {"ecosystem": "gradle", "description": "Gradle build file"},
    "pom.xml": {"ecosystem": "maven", "description": "Maven POM file"},
}

INSTALLERS: dict[str, tuple[str, ...]] = {
    "pypi": ("pip", "install"),
    "npm": ("npm", "install"),
    "crates": ("cargo", "add"),
    "gomodules": ("go", "get"),
    "conda": ("conda", "install"),
    "rubygems": ("gem", "install"),
    "packagist": ("composer", "require"),
    "pub": ("dart", "pub", "add"),
    "nuget": ("dotnet", "add", "package"),
    "cocoapods": ("pod", "install"),
    "maven": ("mvn", "dependency:copy-dependencies"),
    "homebrew": ("brew", "install"),
    "hex": ("mix", "deps.update"),
    "swift": ("swift", "package", "resolve"),
    "gradle": ("gradle", "dependencies"),
    "nix": ("nix-shell", "-p"),
    "guix": ("guix", "install"),
    "apt": ("apt-get", "install"),
    "apk": ("apk", "add"),
    "vcpkg": ("vcpkg", "install"),
    "conan": ("conan", "install"),
    "helm": ("helm", "install"),
    "terraform": ("terraform", "init"),
}

# =============================================================================
# Lazy settings registry — env vars evaluated on first access via __getattr__
# =============================================================================

_LAZY_SETTINGS: dict[str, tuple[str | None, str | None, Callable[[str | None], Any] | None]] = {}


def _register(
    name: str,
    env_var: str | None,
    default: str | None,
    converter: Callable[[str | None], Any] | None = None,
) -> None:
    _LAZY_SETTINGS[name] = (env_var, default, converter)


# --- String settings ---
_register("SECRET_KEY", "SECRET_KEY", "your-secret-key-here-change-in-production")
_register("ALGORITHM", "JWT_ALGORITHM", "HS256")
_register("API_KEY_HEADER", "API_KEY_HEADER", "X-API-Key")
_register("LOCAL_INDEX_DIR", "LOCAL_INDEX_DIR", _os.path.expanduser("~/.cache/udr/indexes"))
_register(
    "LOG_LEVEL",
    "LOG_LEVEL",
    "INFO",
    lambda v: "DEBUG" if _get("ENV") == "development" else v,
)
_register("DATABASE_URL", "DATABASE_URL", "sqlite:///./udr.db")
_register("REDIS_URL", "REDIS_URL", "redis://localhost:6379")
_register("OSV_API_URL", "OSV_API_URL", "https://api.osv.dev/v1/query")
_register("TARGET_OS", "TARGET_OS", "")
_register("TARGET_ARCH", "TARGET_ARCH", "")
_register("TARGET_CUDA", "TARGET_CUDA", "")
_register("ENV", "ENV", "development")

# --- Integer settings ---
_register("ACCESS_TOKEN_EXPIRE_MINUTES", "ACCESS_TOKEN_EXPIRE_MINUTES", "30", int)
_register("REFRESH_TOKEN_EXPIRE_DAYS", "REFRESH_TOKEN_EXPIRE_DAYS", "7", int)
_register("BFS_BATCH_SIZE", "BFS_BATCH_SIZE", "20", int)
_register("LOCAL_INDEX_UPDATE_INTERVAL", "LOCAL_INDEX_UPDATE_INTERVAL", "3600", int)
_register("INDEX_SYNC_AGE_HOURS", "INDEX_SYNC_AGE_HOURS", "24", int)
_register("MAX_RETRIES", "MAX_RETRIES", "3", int)
_register("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5", int)
_register("CIRCUIT_BREAKER_OPEN_TIME", "CIRCUIT_BREAKER_OPEN_TIME", "30", int)
_register("REQUEST_TIMEOUT", "REQUEST_TIMEOUT", "30", int)
_register("DETECT_ECOSYSTEMS_TIMEOUT", "DETECT_ECOSYSTEMS_TIMEOUT", "15", int)
_register("NPM_CONCURRENCY", "NPM_CONCURRENCY", "10", int)
_register("CACHE_TTL", "CACHE_TTL", "3600", int)
_register("CACHE_TTL_SHORT", "CACHE_TTL_SHORT", "300", int)
_register("CACHE_TTL_VERSIONS", "CACHE_TTL_VERSIONS", "600", int)
_register("MAX_REQUEST_SIZE", "MAX_REQUEST_SIZE", str(10 * 1024 * 1024), int)
_register("MAX_MANIFEST_SIZE", "MAX_MANIFEST_SIZE", str(50 * 1024 * 1024), int)  # 50 MB
_register("SOLVER_MAX_VARIABLES", "SOLVER_MAX_VARIABLES", "50000", int)
_register("SOLVER_MAX_VARS", "SOLVER_MAX_VARIABLES", "50000", int)  # alias
_register("SOLVER_MAX_CLUSTERS", "SOLVER_MAX_CLUSTERS", "5", int)
_register("SOLVER_MAX_CLUSTERS_MIN", "SOLVER_MAX_CLUSTERS_MIN", "3", int)
_register("SOLVER_MAX_CLUSTERS_MAX", "SOLVER_MAX_CLUSTERS_MAX", "20", int)
_register("SOLVER_PRERELEASE_PENALTY", "SOLVER_PRERELEASE_PENALTY", "100000", int)
_register("SOLVER_OPTIMIZATION_THRESHOLD", "SOLVER_OPTIMIZATION_THRESHOLD", "500", int)
_register("SOLVER_DFS_MAX_NODES", "SOLVER_DFS_MAX_NODES", "200000", int)
_register("SOLVER_TIMEOUT", "SOLVER_TIMEOUT", "120", int)
_register("SOLVER_API_TIMEOUT", "SOLVER_API_TIMEOUT", "60", int)
_register("SCANNER_MAX_WORKERS", "SCANNER_MAX_WORKERS", "10", int)
_register("AUTO_SOLVER_SMALL_THRESHOLD", "AUTO_SOLVER_SMALL_THRESHOLD", "20", int)
_register("AUTO_SOLVER_LARGE_THRESHOLD", "AUTO_SOLVER_LARGE_THRESHOLD", "500", int)
_register("AUTO_SOLVER_TOP_N", "AUTO_SOLVER_TOP_N", "5", int)

# --- Float settings ---
_register("RETRY_BACKOFF_FACTOR", "RETRY_BACKOFF_FACTOR", "2.0", float)
_register("RETRY_MAX_DELAY", "RETRY_MAX_DELAY", "10.0", float)
_register("SLOW_REQUEST_THRESHOLD", "SLOW_REQUEST_THRESHOLD", "5.0", float)

# --- Boolean settings ---
_bool = lambda v: v.lower() == "true"
_register("GOPROXY_AUTH_TOKEN", "GOPROXY_AUTH_TOKEN", "", str)
_register("GOPROXY_AUTH_BASIC", "GOPROXY_AUTH_BASIC", "", str)
_register("ENABLE_API_KEY_AUTH", "ENABLE_API_KEY_AUTH", "false", _bool)
_register("PIN_INTEGRITY", "PIN_INTEGRITY", "false", _bool)
_register("ENABLE_LOCAL_INDEX", "ENABLE_LOCAL_INDEX", "false", _bool)
_register("INDEX_AUTO_SYNC", "INDEX_AUTO_SYNC", "false", _bool)
_register(
    "ENABLE_REQUEST_LOGGING",
    "ENABLE_REQUEST_LOGGING",
    "false",
    lambda v: True if _get("ENV") == "development" else v.lower() == "true",
)
_register("ENABLE_PERFORMANCE_LOGGING", "ENABLE_PERFORMANCE_LOGGING", "true", _bool)
_register("PROMETHEUS_ENABLED", "PROMETHEUS_ENABLED", "false", _bool)
_register("ENABLE_CACHE", "ENABLE_CACHE", "true", _bool)
_register("USE_PUBGRUB_SOLVER", "USE_PUBGRUB_SOLVER", "false", _bool)
_register("USE_HYBRID_SOLVER", "USE_HYBRID_SOLVER", "false", _bool)
_register("USE_Z3_SOLVER", "USE_Z3_SOLVER", "false", _bool)
_register("SOLVER_REJECT_DEPRECATED", "SOLVER_REJECT_DEPRECATED", "false", _bool)
_register("USE_Z3_OPTIMIZE", "USE_Z3_OPTIMIZE", "false", _bool)
_register("UDR_OFFLINE", "UDR_OFFLINE", "", lambda v: v.lower() in ("1", "true", "yes"))
_register("INCREMENTAL_RESOLUTION", "INCREMENTAL_RESOLUTION", "true", _bool)

# --- Runtime / deployment settings ---
_register("UDR_PORT", "UDR_PORT", "8199", int)
_register("UDR_HOST", "UDR_HOST", "127.0.0.1")
_register("UDR_LOG_LEVEL", "UDR_LOG_LEVEL", "info")
_register("UDR_PROFILE", "UDR_PROFILE", "")
_register("UDR_STANDALONE", "UDR_STANDALONE", "false", _bool)

# --- OpenTelemetry ---
_register("OTEL_ENABLED", "OTEL_ENABLED", "false", _bool)
_register("OTEL_EXPORTER_OTLP_PROTOCOL", "OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
_register("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT", "")
_register("OTEL_EXPORTER_OTLP_HEADERS", "OTEL_EXPORTER_OTLP_HEADERS", "")
_register("OTEL_EXPORTER_OTLP_COMPRESSION", "OTEL_EXPORTER_OTLP_COMPRESSION", "gzip")
_register("OTEL_EXPORTER_OTLP_TIMEOUT", "OTEL_EXPORTER_OTLP_TIMEOUT", "10", int)
_register("OTEL_SAMPLER_TYPE", "OTEL_SAMPLER_TYPE", "parentbased_traceidratio")
_register("OTEL_SAMPLER_ARG", "OTEL_SAMPLER_ARG", "0.1")
_register("OTEL_SERVICE_NAME", "OTEL_SERVICE_NAME", "universal-dependency-resolver")
_register("OTEL_SERVICE_VERSION", "OTEL_SERVICE_VERSION", "1.0.0")
_register("OTEL_RESOURCE_ATTRIBUTES", "OTEL_RESOURCE_ATTRIBUTES", "")

# --- Error reporting / security ---
_register("SENTRY_DSN", "SENTRY_DSN", "")
_register("ENVIRONMENT", "ENVIRONMENT", "development")
_register("ALLOWED_ORIGINS", "ALLOWED_ORIGINS", "http://localhost:3000")
_register("TRUSTED_PROXIES", "TRUSTED_PROXIES", "")
_register("SIGNING_KEY_PASSWORD", "SIGNING_KEY_PASSWORD", "")

# --- Per-ecosystem rate limits (individual overrides for RATE_LIMITS dict) ---
_register("PYPI_RATE_LIMIT", "PYPI_RATE_LIMIT", "600", int)
_register("NPM_RATE_LIMIT", "NPM_RATE_LIMIT", "600", int)
_register("CONDA_RATE_LIMIT", "CONDA_RATE_LIMIT", "300", int)
_register("MAVEN_RATE_LIMIT", "MAVEN_RATE_LIMIT", "300", int)
_register("CRATES_RATE_LIMIT", "CRATES_RATE_LIMIT", "300", int)
_register("GITHUB_RATE_LIMIT", "GITHUB_RATE_LIMIT", "60", int)
_register("RUBYGEMS_RATE_LIMIT", "RUBYGEMS_RATE_LIMIT", "100", int)
_register("NUGET_RATE_LIMIT", "NUGET_RATE_LIMIT", "100", int)
_register("PACKAGIST_RATE_LIMIT", "PACKAGIST_RATE_LIMIT", "100", int)
_register("HOMEBREW_RATE_LIMIT", "HOMEBREW_RATE_LIMIT", "60", int)
_register("COCOAPODS_RATE_LIMIT", "COCOAPODS_RATE_LIMIT", "60", int)
_register("PUB_RATE_LIMIT", "PUB_RATE_LIMIT", "60", int)
_register("GRADLE_RATE_LIMIT", "GRADLE_RATE_LIMIT", "60", int)
_register("SWIFT_RATE_LIMIT", "SWIFT_RATE_LIMIT", "60", int)
_register("HEX_RATE_LIMIT", "HEX_RATE_LIMIT", "60", int)
_register("HASKELL_RATE_LIMIT", "HASKELL_RATE_LIMIT", "60", int)
_register("APT_RATE_LIMIT", "APT_RATE_LIMIT", "300", int)
_register("APK_RATE_LIMIT", "APK_RATE_LIMIT", "300", int)
_register("GOMODULES_RATE_LIMIT", "GOMODULES_RATE_LIMIT", "600", int)
_register("NIX_RATE_LIMIT", "NIX_RATE_LIMIT", "300", int)
_register("GUIX_RATE_LIMIT", "GUIX_RATE_LIMIT", "300", int)
_register("VCPKG_RATE_LIMIT", "VCPKG_RATE_LIMIT", "300", int)
_register("CONAN_RATE_LIMIT", "CONAN_RATE_LIMIT", "300", int)
_register("HELM_RATE_LIMIT", "HELM_RATE_LIMIT", "60", int)
_register("TERRAFORM_RATE_LIMIT", "TERRAFORM_RATE_LIMIT", "60", int)

# --- User-agent overrides ---
_register("DEFAULT_USER_AGENT", "DEFAULT_USER_AGENT", "UniversalDependencyResolver/1.0")
_register("PYPI_USER_AGENT", "PYPI_USER_AGENT", "UniversalDependencyResolver/1.0 (PyPI Client)")
_register("NPM_USER_AGENT", "NPM_USER_AGENT", "UniversalDependencyResolver/1.0 (NPM Client)")
_register("DOC_USER_AGENT", "DOC_USER_AGENT", "Mozilla/5.0 (compatible; DocScraper/1.0)")

# --- Feature flags ---
_register("ENABLE_METRICS", "ENABLE_METRICS", "true", _bool)
_register("ENABLE_RESPONSE_COMPRESSION", "ENABLE_RESPONSE_COMPRESSION", "true", _bool)
_register("ENABLE_CSRF", "ENABLE_CSRF", "true", _bool)
_register("ENABLE_AUTH", "ENABLE_AUTH", "true", _bool)

# --- Special: API_KEY (generated with caching) ---
_API_KEY_CACHE: str | None = None


def _api_key(_unused: str | None = None) -> str:
    global _API_KEY_CACHE
    if _API_KEY_CACHE is not None:
        return _API_KEY_CACHE
    env_val = _os.getenv("API_KEY")
    if env_val:
        _API_KEY_CACHE = env_val
    else:
        _API_KEY_CACHE = f"udr_{secrets.token_urlsafe(32)}"
        logger.info("Generated random API key for this session (set API_KEY env var to persist)")
    return _API_KEY_CACHE


_register("API_KEY", None, None, _api_key)


# --- Special: RATE_LIMITS dict ---
def _rate_limits(_unused: str | None = None) -> dict[str, int]:
    return {
        "pypi": _get("PYPI_RATE_LIMIT"),
        "npm": _get("NPM_RATE_LIMIT"),
        "conda": _get("CONDA_RATE_LIMIT"),
        "maven": _get("MAVEN_RATE_LIMIT"),
        "crates": _get("CRATES_RATE_LIMIT"),
        "github": _get("GITHUB_RATE_LIMIT"),
        "rubygems": _get("RUBYGEMS_RATE_LIMIT"),
        "nuget": _get("NUGET_RATE_LIMIT"),
        "packagist": _get("PACKAGIST_RATE_LIMIT"),
        "homebrew": _get("HOMEBREW_RATE_LIMIT"),
        "cocoapods": _get("COCOAPODS_RATE_LIMIT"),
        "pub": _get("PUB_RATE_LIMIT"),
        "gradle": _get("GRADLE_RATE_LIMIT"),
        "swift": _get("SWIFT_RATE_LIMIT"),
        "hex": _get("HEX_RATE_LIMIT"),
        "haskell": _get("HASKELL_RATE_LIMIT"),
        "apt": _get("APT_RATE_LIMIT"),
        "apk": _get("APK_RATE_LIMIT"),
        "gomodules": _get("GOMODULES_RATE_LIMIT"),
        "nix": _get("NIX_RATE_LIMIT"),
        "guix": _get("GUIX_RATE_LIMIT"),
        "vcpkg": _get("VCPKG_RATE_LIMIT"),
        "conan": _get("CONAN_RATE_LIMIT"),
        "helm": _get("HELM_RATE_LIMIT"),
        "terraform": _get("TERRAFORM_RATE_LIMIT"),
    }


_register("RATE_LIMITS", None, None, _rate_limits)


# --- Special: USER_AGENTS dict ---
def _user_agents(_unused: str | None = None) -> dict[str, str]:
    return {
        "default": _get("DEFAULT_USER_AGENT"),
        "pypi": _get("PYPI_USER_AGENT"),
        "npm": _get("NPM_USER_AGENT"),
        "documentation": _get("DOC_USER_AGENT"),
    }


_register("USER_AGENTS", None, None, _user_agents)


# --- Special: FEATURES dict ---
def _features(_unused: str | None = None) -> dict[str, bool]:
    return {
        "ENABLE_CACHE": _get("ENABLE_CACHE"),
        "ENABLE_METRICS": _get("ENABLE_METRICS"),
        "ENABLE_AUTH": _get("ENABLE_AUTH"),
        "ENABLE_RESPONSE_COMPRESSION": _get("ENABLE_RESPONSE_COMPRESSION"),
        "ENABLE_CSRF": _get("ENABLE_CSRF"),
    }


_register("FEATURES", None, None, _features)


def __getattr__(name: str) -> Any:
    if name in _LAZY_SETTINGS:
        env_var, default, converter = _LAZY_SETTINGS[name]
        val = _os.getenv(env_var, default) if env_var is not None else None
        return converter(val) if converter is not None else val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def reload() -> None:
    """Clear cached setting values so they are re-read on next access."""
    global _API_KEY_CACHE
    _API_KEY_CACHE = None


# =============================================================================
# Settings validation and helpers
# =============================================================================


# NOTE: These functions use _get() helper instead of bare-name references
# because bare names inside module-level functions don't trigger __getattr__.
def _get(key: str) -> Any:
    return __getattr__(key)


def validate_settings() -> list[str]:
    """Validate critical settings and return a list of configuration warnings."""
    warnings: list[str] = []

    if _get("SECRET_KEY") == "your-secret-key-here-change-in-production":
        if _get("ENV") == "production":
            raise RuntimeError(
                "SECRET_KEY is still the default value — set a strong random secret in production"
            )
        warnings.append(
            "SECRET_KEY is still the default value — rotate it immediately in production"
        )

    if _get("ENV") == "production" and not _get("FEATURES").get("ENABLE_AUTH"):
        warnings.append("ENABLE_AUTH is false in production — authentication is disabled")

    if _get("DATABASE_URL").startswith("sqlite"):
        warnings.append(
            f"Using SQLite ({_get('DATABASE_URL')}) — not suitable for production workloads"
        )

    for w in warnings:
        logger.warning(f"Config: {w}")
    return warnings


def get_ecosystem_config(ecosystem: str) -> dict[str, Any]:
    """Get ecosystem config."""
    _cache_ttl = _get("CACHE_TTL")
    _rate_limits = _get("RATE_LIMITS")
    configs = {
        "pypi": {
            "url": "https://pypi.org",
            "api_url": "https://pypi.org/pypi",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("pypi", 600),
        },
        "npm": {
            "url": "https://registry.npmjs.org",
            "api_url": "https://registry.npmjs.org",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("npm", 600),
        },
        "rubygems": {
            "url": "https://rubygems.org",
            "api_url": "https://rubygems.org/api/v1",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("rubygems", 600),
        },
        "nuget": {
            "url": "https://www.nuget.org",
            "api_url": "https://api.nuget.org/v3/index.json",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("nuget", 600),
        },
        "packagist": {
            "url": "https://packagist.org",
            "api_url": "https://repo.packagist.org/p2",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("packagist", 600),
        },
        "homebrew": {
            "url": "https://brew.sh",
            "api_url": "https://formulae.brew.sh/api",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("homebrew", 600),
        },
        "conda": {
            "url": "https://repo.anaconda.com/pkgs/main",
            "channels": {
                "defaults": "https://repo.anaconda.com/pkgs/main",
                "conda-forge": "https://conda.anaconda.org/conda-forge",
            },
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("conda", 300),
        },
        "maven": {
            "url": "https://repo1.maven.org/maven2",
            "search_url": "https://search.maven.org/solrsearch/select",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("maven", 300),
        },
        "crates": {
            "url": "https://crates.io/api/v1",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("crates", 300),
        },
        "gomodules": {
            "url": "https://proxy.golang.org",
            "sum_db_url": "https://sum.golang.org",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("gomodules", 600),
        },
        "apt": {
            "repositories": ["http://deb.debian.org/debian", "http://archive.ubuntu.com/ubuntu"],
            "distributions": ["stable", "testing", "unstable"],
            "cache_ttl": _cache_ttl * 2,
            "rate_limit": _rate_limits.get("apt", 300),
        },
        "apk": {
            "repositories": ["https://dl-cdn.alpinelinux.org/alpine/v3.18/main"],
            "branches": ["v3.18", "v3.17", "edge"],
            "cache_ttl": _cache_ttl * 2,
            "rate_limit": _rate_limits.get("apk", 300),
        },
        "cocoapods": {
            "url": "https://trunk.cocoapods.org/api/v1",
            "specs_url": "https://cdn.cocoapods.org",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("cocoapods", 600),
        },
        "gradle": {
            "url": "https://plugins.gradle.org/api",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("gradle", 300),
        },
        "swift": {
            "url": "https://api.github.com",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("swift", 60),
            "note": "Uses GitHub API by default (60 req/hr). Set SWIFT_REGISTRY_URL env var for SE-0292 registry.",
        },
        "hex": {
            "url": "https://hex.pm/api",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("hex", 300),
        },
        "haskell": {
            "url": "https://hackage.haskell.org",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("haskell", 300),
        },
        "pub": {
            "url": "https://pub.dev/api",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("pub", 600),
        },
        "nix": {
            "url": "",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("nix", 300),
        },
        "guix": {
            "url": "",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("guix", 300),
        },
        "docker": {
            "url": "https://registry-1.docker.io/v2",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("docker", 60),
        },
        "helm": {
            "url": "https://artifacthub.io",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("helm", 60),
        },
        "terraform": {
            "url": "https://registry.terraform.io/v1",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("terraform", 60),
        },
        "vcpkg": {
            "url": "https://raw.githubusercontent.com/microsoft/vcpkg/master/ports",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("vcpkg", 300),
        },
        "conan": {
            "url": "https://center.conan.io",
            "cache_ttl": _cache_ttl,
            "rate_limit": _rate_limits.get("conan", 60),
        },
        "custom_db": {
            "url": "",
            "cache_ttl": _cache_ttl,
            "rate_limit": 0,
        },
    }
    return configs.get(ecosystem, {})
