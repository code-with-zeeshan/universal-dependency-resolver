# backend/__init__.py
"""Universal Dependency Resolver Backend Package."""

import importlib
import logging
import typing

from .settings import get_ecosystem_config

try:
    from importlib.metadata import version as _v

    __version__ = _v("ud-resolver")
except Exception:
    __version__ = "0.0.0"

if typing.TYPE_CHECKING:
    from .core import ConflictResolver, DataAggregator, ExportGenerator, SystemScanner
    from .manifest_detector import ManifestDetector

_LAZY_IMPORTS: dict[str, tuple[str, str, str]] = {
    "ConflictResolver": ("backend.core", "ConflictResolver"),
    "DataAggregator": ("backend.core", "DataAggregator"),
    "ExportGenerator": ("backend.core", "ExportGenerator"),
    "SystemScanner": ("backend.core", "SystemScanner"),
    "ManifestDetector": ("backend.manifest_detector", "ManifestDetector"),
}


def __getattr__(name: str):
    entry = _LAZY_IMPORTS.get(name)
    if entry is not None:
        mod = importlib.import_module(entry[0])
        attr = getattr(mod, entry[1])
        setattr(__import__(__name__), name, attr)
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__) if __all__ else list(_LAZY_IMPORTS)


__all__ = [
    "ConflictResolver",
    "DataAggregator",
    "ExportGenerator",
    "ManifestDetector",
    "SystemScanner",
    "__version__",
    "get_ecosystem_config",
]

logging.getLogger(__name__).addHandler(logging.NullHandler())
