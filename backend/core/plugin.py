"""Ecosystem plugin system — abstract interface + registry.

Design
------
Each ecosystem is a class that inherits from ``EcosystemPlugin`` and is
registered via the ``@register_ecosystem`` decorator::

    @register_ecosystem("hex", name="Hex.pm (Elixir/Erlang)")
    class HexPlugin(EcosystemPlugin):
        ...

The plugin bundles everything UDR needs to know about an ecosystem in one
place — manifest patterns, lock-file patterns, parsers, updaters, and the
data-source client.

Plugin discovery
----------------
- **Built-in plugins** are imported eagerly by ``import_builtin_plugins()``.
- **Third-party plugins** (installed via ``pip install udr-hex``) are
  discovered via entry points.
- **Local plugins** placed in a directory (e.g. ``~/.config/udr/plugins/``)
  are discovered at runtime by ``scan_plugin_directory()``.
"""

from __future__ import annotations

import abc
import dataclasses
import importlib.util
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Callable

from backend.data_sources.base_client import BaseDataSourceClient
from backend.settings import CACHE_TTL, get_ecosystem_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PluginManifest:
    """Describes one manifest file pattern supported by an ecosystem plugin.

    Attributes:
        glob: File-name glob pattern (e.g. ``"mix.exs"``, ``"*.cabal"``).
        parser: Method name on the plugin class that parses this manifest.
            The method must accept ``(self, content: str) -> list[dict]``.

    """

    glob: str
    parser: str


@dataclasses.dataclass(frozen=True)
class PluginLockFile:
    """Describes one lock-file pattern supported by an ecosystem plugin.

    Attributes:
        glob: File-name glob pattern (e.g. ``"Cargo.lock"``).
        parser: Method name on the plugin class that parses this lock file
            into a dependency tree.  The method must accept
            ``(self, content: str) -> dict[str, dict]`` where keys are
            package names and values are dicts with at least ``"version"``
            and optionally ``"dependencies"``.

    """

    glob: str
    parser: str


# ---------------------------------------------------------------------------
# Plugin base class
# ---------------------------------------------------------------------------


class EcosystemPlugin(BaseDataSourceClient, abc.ABC):
    """Abstract base for an ecosystem plugin.

    Subclasses **must** define:

    * ``ecosystem`` — the canonical ecosystem identifier (e.g. ``"hex"``).
    * ``get_package_info()`` — the primary data-source method.

    Optional overrides (default ``None`` / ``NotImplementedError``):

    * ``manifests`` — list of ``PluginManifest``.
    * ``lock_files`` — list of ``PluginLockFile``.
    * ``get_package_versions()``
    * ``get_artifact_hash()``
    * ``search_packages()``
    * ``update_manifest()`` — in-place manifest write-back.
    """

    # -- Class-level metadata (override in subclass) -----------------------

    #: Human-readable display name (e.g. ``"Hex.pm (Elixir/Erlang)"``).
    display_name: ClassVar[str] = ""

    #: Manifest file patterns this plugin recognises.
    manifests: ClassVar[list[PluginManifest]] = []

    #: Lock-file patterns this plugin recognises.
    lock_files: ClassVar[list[PluginLockFile]] = []

    #: Environment-variable prefix for auth settings (e.g. ``"HEX"``).
    auth_prefix: ClassVar[str] = ""

    # -- Instance methods --------------------------------------------------

    def __init__(
        self,
        cache_ttl: int | None = None,
        max_retries: int | None = None,
    ):
        """Initialize the EcosystemPlugin."""
        config = get_ecosystem_config(self.ecosystem)
        super().__init__(
            ecosystem=self.ecosystem,
            base_url=config.get("url", self._default_base_url()),
            cache_ttl=cache_ttl or config.get("cache_ttl", CACHE_TTL),
        )

    # -- Subclass hooks (registry metadata) --------------------------------

    @classmethod
    def _default_base_url(cls) -> str:
        """Return the default base URL for this ecosystem.

        Override when the ecosystem config does not provide a ``url`` key.
        """
        return ""

    # -- Required: data-source interface -----------------------------------

    @abc.abstractmethod
    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        """Fetch metadata for *package_name*.

        Returns a dict with at least ``"name"`` and ``"version"`` (latest).
        When *include_versions* is ``True`` the dict should include a
        ``"versions"`` list of ``{"version": str, ...}`` entries.
        """

    # -- Optional: data-source interface -----------------------------------

    async def get_package_versions(
        self,
        package_name: str,
        filters: dict | None = None,
    ) -> list[dict]:
        """Return all known versions of *package_name*.

        The default implementation delegates to ``get_package_info()``.
        Override for ecosystems that have a dedicated versions endpoint.
        """
        info = await self.get_package_info(package_name, include_versions=True)
        return info.get("versions", []) if info else []

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        """Search for packages matching *query*.

        The default raises ``NotImplementedError``.  Override when
        the ecosystem provides a search API.
        """
        raise NotImplementedError

    async def get_artifact_hash(
        self,
        package_name: str,
        version: str,
    ) -> dict | None:
        """Return the integrity hash for *package_name* at *version*.

        Returns ``None`` when the ecosystem does not provide hashes.
        """
        return None

    # -- Optional: manifest interface --------------------------------------

    def update_manifest(
        self,
        content: str,
        package_name: str,
        resolved_version: str,
    ) -> str | None:
        """Update a manifest file's *package_name* to *resolved_version*.

        Receives the raw file *content* and returns the updated content
        (or ``None`` if the package was not found).

        The default returns ``None`` (no write-back support).
        """
        return None

    # -- Optional: lock-file parsing ---------------------------------------

    def parse_lock_tree(self, content: str) -> dict[str, dict[str, Any]]:
        """Parse a lock file into a flat dict of resolved packages.

        The default raises ``NotImplementedError``.  Override when the
        ecosystem has a lock file with a dependency tree.
        """
        raise NotImplementedError

    # -- Lifecycle hooks ---------------------------------------------------

    async def close(self):
        """Release any HTTP sessions or other resources held by this plugin.

        Subclasses with persistent sessions should override this method.
        The base implementation is a no-op.
        """


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_plugin_registry: dict[str, type[EcosystemPlugin]] = {}
_plugin_lock: Any = threading.Lock()


def register_ecosystem(
    ecosystem: str,
    *,
    name: str = "",
    auth_prefix: str = "",
):
    """Register a plugin class for *ecosystem*.

    Usage::

        @register_ecosystem("hex", name="Hex.pm (Elixir/Erlang)")
        class HexPlugin(EcosystemPlugin):
            ecosystem = "hex"
            ...
    """

    def _wrapper(cls: type[EcosystemPlugin]) -> type[EcosystemPlugin]:
        if not issubclass(cls, EcosystemPlugin):
            raise TypeError(f"{cls.__name__} must inherit from EcosystemPlugin")
        cls.ecosystem = ecosystem  # type: ignore[attr-defined]
        if name:
            cls.display_name = name
        if auth_prefix:
            cls.auth_prefix = auth_prefix
        with _plugin_lock:
            if ecosystem in _plugin_registry:
                logger.debug("Plugin %r already registered (skipping duplicate)", ecosystem)
                return cls
            _plugin_registry[ecosystem] = cls
            logger.debug("Registered plugin %s for ecosystem %r", cls.__name__, ecosystem)
        return cls

    return _wrapper


def get_plugin(ecosystem: str) -> type[EcosystemPlugin] | None:
    """Return the registered plugin class for *ecosystem* (or ``None``)."""
    with _plugin_lock:
        return _plugin_registry.get(ecosystem)


def get_all_plugins() -> dict[str, type[EcosystemPlugin]]:
    """Return a thread-safe copy of the plugin registry."""
    with _plugin_lock:
        return dict(_plugin_registry)


def scan_plugin_directory(directory: str) -> list[type[EcosystemPlugin]]:
    """Walk *directory*, import each ``.py`` file, return registered plugin classes.

    Any class that inherits from ``EcosystemPlugin`` (or is registered via
    ``@register_ecosystem``) will be discovered and also added to the global
    registry.
    """
    discovered: list[type[EcosystemPlugin]] = []
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        logger.debug("Plugin directory %s does not exist", root)
        return discovered

    for py_file in sorted(root.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"_udr_plugin_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:
            logger.warning("Failed to import plugin %s: %s", py_file, exc)
            continue

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, EcosystemPlugin)
                and attr is not EcosystemPlugin
            ):
                if attr not in discovered:
                    discovered.append(attr)
                with _plugin_lock:
                    if attr.ecosystem not in _plugin_registry:  # type: ignore[attr-defined]
                        _plugin_registry[attr.ecosystem] = attr  # type: ignore[attr-defined]
                        logger.debug(
                            "Discovered local plugin %s for %s", attr.__name__, attr.ecosystem
                        )

    return discovered


def discover_local_plugins(directory: str | None = None) -> int:
    """Discover plugins from local directory (default ``~/.config/udr/plugins/``).

    Returns the number of plugin classes found.
    """
    if directory is None:
        directory = str(Path.home() / ".config" / "udr" / "plugins")
    plugins = scan_plugin_directory(directory)
    return len(plugins)


# ---------------------------------------------------------------------------
# Constraint handler hooks
# ---------------------------------------------------------------------------

_PLUGIN_CONSTRAINT_HANDLERS: dict[str, Callable[[str, str], str | None]] = {}


def register_constraint_handler(ecosystem: str, handler: Callable[[str, str], str | None]):
    """Register *handler* to normalize constraints for *ecosystem*.

    The handler receives ``(constraint_raw: str, ecosystem: str)`` and should
    return a normalized PEP 440 constraint string, or ``None`` to decline.
    """
    _PLUGIN_CONSTRAINT_HANDLERS[ecosystem] = handler
    logger.debug("Registered constraint handler for ecosystem %r", ecosystem)


def handle_plugin_constraint(constraint: str, ecosystem: str) -> str | None:
    """Run registered constraint handlers for *ecosystem* against *constraint*.

    Returns the normalized constraint string, or ``None`` if no handler
    accepted the constraint.
    """
    handler = _PLUGIN_CONSTRAINT_HANDLERS.get(ecosystem)
    if handler is None:
        return None
    try:
        return handler(constraint, ecosystem)
    except Exception as exc:
        logger.warning("Constraint handler for %s failed: %s", ecosystem, exc)
        return None


def list_plugin_manifests() -> list[tuple[str, str, str]]:
    """Aggregate ``(glob, ecosystem, parser_name)`` triples from all plugins.

    Returns entries suitable for appending to ``MANIFEST_PATTERNS``.
    """
    with _plugin_lock:
        result: list[tuple[str, str, str]] = []
        for eco, cls in _plugin_registry.items():
            for mf in cls.manifests:
                result.append((mf.glob, eco, mf.parser))
        return result


def list_plugin_lock_files() -> list[tuple[str, str, str]]:
    """Aggregate ``(glob, ecosystem, parser_name)`` triples from all plugins."""
    with _plugin_lock:
        result: list[tuple[str, str, str]] = []
        for eco, cls in _plugin_registry.items():
            for lf in cls.lock_files:
                result.append((lf.glob, eco, lf.parser))
        return result


# ---------------------------------------------------------------------------
# Built-in plugin discovery
# ---------------------------------------------------------------------------

# Lazy-import map for built-in plugins keyed by ecosystem.
_BUILTIN_PLUGIN_MODULES: dict[str, str] = {}


def _register_builtin(ecosystem: str, module_path: str):
    """Declare a built-in plugin to be imported on ``import_builtin_plugins()``."""
    _BUILTIN_PLUGIN_MODULES[ecosystem] = module_path


def import_builtin_plugins():
    """Import all built-in plugin modules so their ``@register_ecosystem`` decorators fire."""
    import importlib

    for ecosystem, module_path in list(_BUILTIN_PLUGIN_MODULES.items()):
        if ecosystem not in _plugin_registry:
            try:
                importlib.import_module(module_path)
            except Exception as exc:
                logger.warning(
                    "Failed to load built-in plugin %r from %s: %s",
                    ecosystem,
                    module_path,
                    exc,
                )


def discover_third_party_plugins():
    """Discover third-party plugins via ``udr.plugins`` entry points.

    Any installed package that declares a ``[project.entry-points."udr.plugins"]``
    section will have its plugin class loaded and registered automatically.
    """
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return

    try:
        eps = entry_points(group="udr.plugins")
    except TypeError:
        return

    for ep in eps:
        with _plugin_lock:
            if ep.name in _plugin_registry:
                continue
        try:
            loaded = ep.load()
            if loaded is not None and not (
                isinstance(loaded, type) and issubclass(loaded, EcosystemPlugin)
            ):
                logger.warning(
                    "Third-party plugin %r does not inherit from EcosystemPlugin — rejected",
                    ep.name,
                )
                with _plugin_lock:
                    _plugin_registry.pop(ep.name, None)
        except Exception as exc:
            logger.warning(
                "Failed to load third-party plugin %r: %s",
                ep.name,
                exc,
            )


def discover_all_plugins():
    """Load all plugins — built-in + third-party."""
    import_builtin_plugins()
    discover_third_party_plugins()


# ---------------------------------------------------------------------------
# Register all built-in plugin modules for auto-discovery.
# These populate _BUILTIN_PLUGIN_MODULES so that import_builtin_plugins()
# knows which modules to import.
# ---------------------------------------------------------------------------
_register_builtin("npm", "backend.data_sources.npm_plugin")
_register_builtin("pypi", "backend.data_sources.pypi_plugin")
_register_builtin("crates", "backend.data_sources.crates_plugin")
_register_builtin("hex", "backend.data_sources.hex_plugin")
_register_builtin("haskell", "backend.data_sources.haskell_plugin")
_register_builtin("pub", "backend.data_sources.pub_plugin")
_register_builtin("gradle", "backend.data_sources.gradle_plugin")
_register_builtin("swift", "backend.data_sources.swift_plugin")
_register_builtin("maven", "backend.data_sources.maven_plugin")
_register_builtin("conda", "backend.data_sources.conda_plugin")
_register_builtin("gomodules", "backend.data_sources.gomodules_plugin")
_register_builtin("apt", "backend.data_sources.apt_plugin")
_register_builtin("apk", "backend.data_sources.apk_plugin")
_register_builtin("cocoapods", "backend.data_sources.cocoapods_plugin")
_register_builtin("homebrew", "backend.data_sources.homebrew_plugin")
_register_builtin("nuget", "backend.data_sources.nuget_plugin")
_register_builtin("packagist", "backend.data_sources.packagist_plugin")
_register_builtin("rubygems", "backend.data_sources.rubygems_plugin")
_register_builtin("custom_db", "backend.data_sources.custom_db_plugin")
_register_builtin("nix", "backend.data_sources.nix_plugin")
_register_builtin("guix", "backend.data_sources.guix_plugin")
_register_builtin("vcpkg", "backend.data_sources.vcpkg_plugin")
_register_builtin("conan", "backend.data_sources.conan_plugin")
_register_builtin("docker", "backend.data_sources.docker_plugin")
_register_builtin("helm", "backend.data_sources.helm_plugin")
_register_builtin("terraform", "backend.data_sources.terraform_plugin")


# ---------------------------------------------------------------------------
# Dynamic directory scanner (Item 27: CLI tools register-plugin)
# ---------------------------------------------------------------------------
