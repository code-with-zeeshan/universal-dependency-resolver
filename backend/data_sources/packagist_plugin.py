"""Packagist (PHP) — EcosystemPlugin adapter delegating to legacy PackagistClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("packagist", name="Packagist (PHP)", auth_prefix="PACKAGIST")
class PackagistPlugin(EcosystemPlugin):
    """Plugin for Packagist — delegates to the existing PackagistClient."""

    ecosystem = "packagist"

    manifests = [
        PluginManifest(glob="composer.json", parser="parse_composer_json"),
        PluginManifest(glob="composer.lock", parser="parse_composer_lock"),
    ]

    @staticmethod
    def parse_composer_json(content: str) -> list[dict]:
        """Parse a composer.json file into a list of dependency dicts."""
        return []

    @staticmethod
    def parse_composer_lock(content: str) -> list[dict]:
        """Parse a composer.lock file into a list of dependency dicts."""
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .packagist_client import PackagistClient

            self._legacy_client = PackagistClient()
        return self._legacy_client

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        """Fetch package metadata from the registry."""
        client = self._get_client()
        return await client.get_package_info_async(package_name, include_versions=include_versions)

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        """Search for packages matching the query."""
        client = self._get_client()
        return await client.search_packages(query, limit=limit)
