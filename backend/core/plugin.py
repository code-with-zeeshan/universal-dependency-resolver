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
"""

from __future__ import annotations

import abc
import dataclasses
import logging
from typing import Any, ClassVar

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


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_plugin_registry: dict[str, type[EcosystemPlugin]] = {}


def register_ecosystem(
    ecosystem: str,
    *,
    name: str = "",
    auth_prefix: str = "",
):
    """Decorator that registers a plugin class for *ecosystem*.

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
        if ecosystem in _plugin_registry:
            logger.warning("Overriding existing plugin for ecosystem %r", ecosystem)
        _plugin_registry[ecosystem] = cls
        logger.debug("Registered plugin %s for ecosystem %r", cls.__name__, ecosystem)
        return cls

    return _wrapper


def get_plugin(ecosystem: str) -> type[EcosystemPlugin] | None:
    """Return the registered plugin class for *ecosystem* (or ``None``)."""
    return _plugin_registry.get(ecosystem)


def get_all_plugins() -> dict[str, type[EcosystemPlugin]]:
    """Return a copy of the plugin registry."""
    return dict(_plugin_registry)


def list_plugin_manifests() -> list[tuple[str, str, str]]:
    """Aggregate ``(glob, ecosystem, parser_name)`` triples from all plugins.

    Returns entries suitable for appending to ``MANIFEST_PATTERNS``.
    """
    result: list[tuple[str, str, str]] = []
    for eco, cls in _plugin_registry.items():
        for mf in cls.manifests:
            result.append((mf.glob, eco, mf.parser))
    return result


def list_plugin_lock_files() -> list[tuple[str, str, str]]:
    """Aggregate ``(glob, ecosystem, parser_name)`` triples from all plugins."""
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
    """Import all built-in plugin modules so their ``@register_ecosystem``
    decorators fire.  Safe to call multiple times.
    """
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
