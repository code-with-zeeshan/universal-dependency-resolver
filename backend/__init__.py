# backend/__init__.py
"""Universal Dependency Resolver Backend Package."""

from .core import ConflictResolver, DataAggregator, ExportGenerator, SystemScanner
from .manifest_detector import ManifestDetector
from .settings import get_ecosystem_config

try:
    from importlib.metadata import version as _v

    __version__ = _v("ud-resolver")
except Exception:
    __version__ = "0.0.0"

__all__ = [
    "ConflictResolver",
    "DataAggregator",
    "ExportGenerator",
    "ManifestDetector",
    "SystemScanner",
    "__version__",
    "get_ecosystem_config",
]

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
