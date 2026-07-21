"""Module docstring."""

import logging

from slowapi import Limiter

from backend.core.data_aggregator import DataAggregator
from backend.core.export_generator import ExportGenerator
from backend.core.system_scanner import SystemScanner
from backend.orchestrator.db_service import CompatibilityDB
from backend.orchestrator.resolve import create_solver
from backend.settings import REDIS_URL

logger = logging.getLogger(__name__)


def _rate_limit_key(request):
    """Rate limit key function that uses secure client IP resolution.

    Respects X-Forwarded-For / X-Real-IP only from trusted proxies
    (private IPs or explicitly configured TRUSTED_PROXIES).
    """
    return request.client.host if request.client else "unknown"


redis_url = REDIS_URL
if redis_url:
    limiter = Limiter(key_func=_rate_limit_key, storage_uri=redis_url)
else:
    limiter = Limiter(key_func=_rate_limit_key)


def get_system_scanner() -> SystemScanner:
    """Get system scanner."""
    return SystemScanner()


def get_data_aggregator() -> DataAggregator:
    """Get data aggregator."""
    return DataAggregator()


def get_conflict_resolver():
    """Get conflict resolver (Z3 or PubGrub based on USE_PUBGRUB_SOLVER)."""
    return create_solver()


def get_export_generator() -> ExportGenerator:
    """Get export generator."""
    return ExportGenerator()


def get_compatibility_db() -> CompatibilityDB:
    """Get compatibility db."""
    return CompatibilityDB()
