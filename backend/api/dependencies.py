"""Module docstring."""
import os
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.system_scanner import SystemScanner
from backend.core.data_aggregator import DataAggregator
from backend.core.conflict_resolver import ConflictResolver
from backend.core.export_generator import ExportGenerator
from backend.orchestrator.db_service import CompatibilityDB

logger = logging.getLogger(__name__)

redis_url = os.getenv("REDIS_URL")
if redis_url:
    limiter = Limiter(key_func=get_remote_address, storage_uri=redis_url)
else:
    limiter = Limiter(key_func=get_remote_address)


def get_system_scanner() -> SystemScanner:
    """Get system scanner."""
    return SystemScanner()


def get_data_aggregator() -> DataAggregator:
    """Get data aggregator."""
    return DataAggregator()


def get_conflict_resolver() -> ConflictResolver:
    """Get conflict resolver."""
    return ConflictResolver()


def get_export_generator() -> ExportGenerator:
    """Get export generator."""
    return ExportGenerator()


def get_compatibility_db() -> CompatibilityDB:
    """Get compatibility db."""
    return CompatibilityDB()
