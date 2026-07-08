"""Module docstring."""

import logging
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.data_aggregator import DataAggregator
from backend.core.export_generator import ExportGenerator
from backend.core.system_scanner import SystemScanner
from backend.orchestrator.db_service import CompatibilityDB
from backend.orchestrator.resolve import create_solver

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


def get_conflict_resolver():
    """Get conflict resolver (Z3 or PubGrub based on USE_PUBGRUB_SOLVER)."""
    return create_solver()


def get_export_generator() -> ExportGenerator:
    """Get export generator."""
    return ExportGenerator()


def get_compatibility_db() -> CompatibilityDB:
    """Get compatibility db."""
    return CompatibilityDB()
