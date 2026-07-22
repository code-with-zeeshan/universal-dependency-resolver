"""Module docstring — lazy-loaded exports.

All heavy imports (SystemScanner, DataAggregator, ConflictResolver, etc.) are
deferred via ``__getattr__`` so that importing ``backend.core`` itself is fast.
The first access to any named export triggers the real import.
"""

import typing

if typing.TYPE_CHECKING:
    from .conflict_resolver import ConflictResolver  # noqa: F401
    from .data_aggregator import DataAggregator  # noqa: F401
    from .export_generator import ExportGenerator  # noqa: F401
    from .plugin import (  # noqa: F401
        EcosystemPlugin,
        PluginLockFile,
        PluginManifest,
        discover_all_plugins,
        discover_local_plugins,
        get_all_plugins,
        get_plugin,
        handle_plugin_constraint,
        import_builtin_plugins,
        register_constraint_handler,
        register_ecosystem,
        scan_plugin_directory,
    )
    from .pubgrub_core import ResolutionError  # noqa: F401
    from .resolution_result import ResolutionResult  # noqa: F401
    from .system_scanner import SystemScanner  # noqa: F401
    from .test_matrix import MatrixGenerator, PackageSpec  # noqa: F401


_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "ConflictResolver": (".conflict_resolver", "ConflictResolver"),
    "DataAggregator": (".data_aggregator", "DataAggregator"),
    "ExportGenerator": (".export_generator", "ExportGenerator"),
    "EcosystemPlugin": (".plugin", "EcosystemPlugin"),
    "PluginLockFile": (".plugin", "PluginLockFile"),
    "PluginManifest": (".plugin", "PluginManifest"),
    "ResolutionError": (".pubgrub_core", "ResolutionError"),
    "ResolutionResult": (".resolution_result", "ResolutionResult"),
    "discover_all_plugins": (".plugin", "discover_all_plugins"),
    "discover_local_plugins": (".plugin", "discover_local_plugins"),
    "get_all_plugins": (".plugin", "get_all_plugins"),
    "get_plugin": (".plugin", "get_plugin"),
    "handle_plugin_constraint": (".plugin", "handle_plugin_constraint"),
    "import_builtin_plugins": (".plugin", "import_builtin_plugins"),
    "register_constraint_handler": (".plugin", "register_constraint_handler"),
    "register_ecosystem": (".plugin", "register_ecosystem"),
    "scan_plugin_directory": (".plugin", "scan_plugin_directory"),
    "SystemScanner": (".system_scanner", "SystemScanner"),
    "MatrixGenerator": (".test_matrix", "MatrixGenerator"),
    "PackageSpec": (".test_matrix", "PackageSpec"),
}


def __getattr__(name: str):
    entry = _LAZY_IMPORTS.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    mod = importlib.import_module(entry[0], package=__package__)
    attr = getattr(mod, entry[1])
    setattr(__import__(__name__), name, attr)
    return attr


def __dir__() -> list[str]:
    return sorted(__all__) if __all__ else list(_LAZY_IMPORTS)


__all__ = sorted(_LAZY_IMPORTS)  # noqa: PLE0605
