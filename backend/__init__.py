# backend/__init__.py
"""
Universal Dependency Resolver Backend Package
"""

from .settings import get_ecosystem_config
from .core import DataAggregator, ConflictResolver, SystemScanner, ExportGenerator
from .manifest_detector import ManifestDetector

try:
    from importlib.metadata import version as _v
    __version__ = _v("ud-resolver")
except Exception:
    __version__ = "0.0.0"

__all__ = [
    "get_ecosystem_config",
    "DataAggregator",
    "ConflictResolver",
    "SystemScanner",
    "ExportGenerator",
    "ManifestDetector",
    "__version__",
]

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
