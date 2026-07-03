# models.py
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.event import listen
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, validates

# Add parent directory to path for direct execution
_sys_path_appended = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _sys_path_appended not in sys.path:
    sys.path.insert(0, _sys_path_appended)

Base: type = declarative_base()


class Package(Base):
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    ecosystem = Column(String(50), nullable=False)  # pypi, npm, conda, etc.
    latest_version = Column(String(50))
    description = Column(Text)
    homepage = Column(String(500))
    repository = Column(String(500))
    license = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    versions = relationship(
        "PackageVersion", back_populates="package", cascade="all, delete-orphan"
    )
    compatibility_reports = relationship("CompatibilityReport", back_populates="package")
    conflicts = relationship(
        "ConflictRule",
        foreign_keys="ConflictRule.package1_id",
        back_populates="package1",
    )

    __table_args__ = (
        UniqueConstraint("name", "ecosystem", name="_name_ecosystem_uc"),
        Index("idx_package_name", "name"),
        Index("idx_package_ecosystem", "ecosystem"),
        Index("idx_package_name_ecosystem", "name", "ecosystem"),
    )


class PackageVersion(Base):
    __tablename__ = "package_versions"

    id = Column(Integer, primary_key=True)
    package_id = Column(Integer, ForeignKey("packages.id"), nullable=False)
    version = Column(String(50), nullable=False)
    release_date = Column(DateTime)
    python_requires = Column(String(100))
    size_bytes = Column(Integer)
    download_count = Column(Integer)

    # System requirements as JSON
    system_requirements = Column(JSON)  # {gpu: {...}, python: {...}, os: {...}}

    # Dependencies as JSON
    dependencies = Column(JSON)  # {required: {...}, optional: {...}, dev: {...}}

    # Metadata
    metadata_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    package = relationship("Package", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("package_id", "version", name="_package_version_uc"),
        Index("idx_version_package_id", "package_id"),
        Index("idx_version_version", "version"),
        Index("idx_version_release_date", "release_date"),
        Index("idx_version_download_count", "download_count"),
    )

    @validates("version")
    def validate_version(self, key, version):
        """Validate version format."""
        # Import here to avoid circular imports
        from core.utils import parse_version

        if not version:
            raise ValueError("Version cannot be empty")

        parsed = parse_version(version)
        if not parsed:
            raise ValueError(f"Invalid version format: {version}")

        return version


class CompatibilityReport(Base):
    __tablename__ = "compatibility_reports"

    id = Column(Integer, primary_key=True)
    package_id = Column(Integer, ForeignKey("packages.id"), nullable=False)
    version = Column(String(50), nullable=False)

    # System information
    os_name = Column(String(50))
    os_version = Column(String(50))
    cpu_architecture = Column(String(50))
    gpu_name = Column(String(255))
    cuda_version = Column(String(20))
    cudnn_version = Column(String(20))
    python_version = Column(String(20))

    # Full system info as JSON
    system_info = Column(JSON)

    # Report details
    works = Column(Boolean, nullable=False)
    notes = Column(Text)
    user_id = Column(String(100))  # Optional user identifier

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    package = relationship("Package", back_populates="compatibility_reports")

    __table_args__ = (
        Index("idx_report_package_version", "package_id", "version"),
        Index("idx_report_created", "created_at"),
    )


class ConflictRule(Base):
    __tablename__ = "conflict_rules"

    id = Column(Integer, primary_key=True)
    package1_id = Column(Integer, ForeignKey("packages.id"), nullable=False)
    package1_version_spec = Column(String(100))  # e.g., ">=2.0.0"
    package2_id = Column(Integer, ForeignKey("packages.id"), nullable=False)
    package2_version_spec = Column(String(100))

    conflict_type = Column(String(50))  # 'version', 'system', 'dependency'
    description = Column(Text)
    severity = Column(String(20))  # 'error', 'warning', 'info'

    # Resolution suggestions
    resolution = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    verified = Column(Boolean, default=False)

    # Relationships
    package1 = relationship("Package", foreign_keys=[package1_id], back_populates="conflicts")
    package2 = relationship("Package", foreign_keys=[package2_id])

    __table_args__ = (Index("idx_conflict_packages", "package1_id", "package2_id"),)


class VerifiedCombination(Base):
    __tablename__ = "verified_combinations"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Package combination as JSON
    packages = Column(JSON, nullable=False)  # [{name, version, ecosystem}, ...]

    # System requirements
    system_requirements = Column(JSON)

    # Verification details
    verified_by = Column(String(100))
    verification_date = Column(DateTime)
    test_results = Column(JSON)

    # Usage statistics
    usage_count = Column(Integer, default=0)
    success_rate = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_combination_name", "name"),
        Index("idx_combination_created", "created_at"),
    )


class SystemBenchmark(Base):
    __tablename__ = "system_benchmarks"

    id = Column(Integer, primary_key=True)
    system_hash = Column(String(64), unique=True)  # Hash of system configuration

    # System specs
    os_name = Column(String(50))
    os_version = Column(String(50))
    cpu_model = Column(String(255))
    cpu_cores = Column(Integer)
    ram_gb = Column(Float)
    gpu_model = Column(String(255))
    gpu_memory_gb = Column(Float)

    # Full system info
    system_info = Column(JSON)

    # Benchmark results
    benchmarks = Column(JSON)  # {cpu_score: ..., gpu_score: ..., etc}

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_benchmark_hash", "system_hash"),)


class ResolutionCache(Base):
    __tablename__ = "resolution_cache"

    id = Column(Integer, primary_key=True)
    request_hash = Column(String(64), unique=True)  # Hash of resolution request

    # Request details
    packages = Column(JSON)  # List of requested packages
    system_info = Column(JSON)
    constraints = Column(JSON)

    # Resolution result
    resolution = Column(JSON)  # Resolved package versions
    resolution_time_ms = Column(Integer)
    success = Column(Boolean)

    # Cache metadata
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)

    __table_args__ = (
        Index("idx_resolution_hash", "request_hash"),
        Index("idx_resolution_expires", "expires_at"),
        Index("idx_resolution_created", "created_at"),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)

    # Scopes/permissions
    scopes = Column(JSON, default=list)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)

    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_user_username", "username"),
        Index("idx_user_email", "email"),
    )


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    key = Column(String(255), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Permissions
    scopes = Column(JSON, default=list)

    # Status
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime)
    last_used_at = Column(DateTime)
    usage_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="api_keys")

    __table_args__ = (
        Index("idx_api_key", "key"),
        Index("idx_api_key_user", "user_id"),
        Index("idx_api_key_active", "is_active"),
    )


# Event listeners for normalization
@event.listens_for(Package, "before_insert")
@event.listens_for(Package, "before_update")
def normalize_package_fields(mapper, connection, target):
    """Normalize package fields before saving."""
    try:
        from core.utils import normalize_package_name, sanitize_ecosystem_name

        if target.name:
            target.name = normalize_package_name(target.name)

        if target.ecosystem:
            target.ecosystem = sanitize_ecosystem_name(target.ecosystem)
    except ImportError:
        # If utils not available, skip normalization
        pass


# Database connection with connection pooling and health checks
from pathlib import Path

from backend.settings import DATABASE_URL

ALEMBIC_CONFIG_PATH = str(Path(__file__).parent.parent.parent / "alembic.ini")

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        kwargs: dict[str, Any] = {"echo": False}
        if DATABASE_URL.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs.update(
                pool_size=10,
                max_overflow=20,
                pool_timeout=30,
                pool_recycle=3600,
                pool_pre_ping=True,
            )
        _engine = create_engine(DATABASE_URL, **kwargs)
        if DATABASE_URL.startswith("sqlite"):
            listen(_engine, "connect", _enable_sqlite_fk)
    return _engine


def _enable_sqlite_fk(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, expire_on_commit=False, bind=get_engine()
        )
    return _SessionLocal


# Backward-compatible aliases — delegate to lazy getters
def __getattr__(name):
    if name == "engine":
        return get_engine()
    if name == "SessionLocal":
        return get_session_local()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def run_migrations(db_url: str | None = None) -> None:
    """Run Alembic migrations programmatically.

    Accepts an optional db_url override for testing with
    engine patching.  Defaults to DATABASE_URL from settings.
    """
    from alembic.config import Config

    from alembic import command

    target_url = db_url or DATABASE_URL

    alembic_cfg = Config(ALEMBIC_CONFIG_PATH)
    alembic_cfg.set_main_option("sqlalchemy.url", target_url)
    command.upgrade(alembic_cfg, "head")


def init_db():
    """Initialize database tables via Alembic migrations."""
    run_migrations()


def check_db_health() -> dict[str, Any]:
    """Check database connection health and pool status."""
    try:
        e = get_engine()
        s = get_session_local()
        db = s()
        from sqlalchemy import text

        db.execute(text("SELECT 1"))
        db.close()

        pool = e.pool
        return {
            "status": "healthy",
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "message": "Database connection is healthy",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "message": f"Database health check failed: {e!s}",
        }


def get_db():
    """Get database session."""
    s = get_session_local()
    db = s()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session():
    """Provide a transactional scope for database operations."""
    s = get_session_local()
    session = s()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
