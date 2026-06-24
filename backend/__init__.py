# backend/__init__.py
"""
Universal Dependency Resolver Backend Package
"""

from .settings import get_ecosystem_config
from .core import DataAggregator, ConflictResolver, SystemScanner, ExportGenerator
from .manifest_detector import ManifestDetector

__all__ = [
    "get_ecosystem_config",
    "DataAggregator",
    "ConflictResolver",
    "SystemScanner",
    "ExportGenerator",
    "ManifestDetector",
]

import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
