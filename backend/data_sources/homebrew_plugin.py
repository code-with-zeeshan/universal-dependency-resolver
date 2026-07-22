"""Homebrew — EcosystemPlugin adapter delegating to legacy HomebrewClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("homebrew", name="Homebrew (macOS/Linux)", auth_prefix="HOMEBREW")
class HomebrewPlugin(EcosystemPlugin):
    """Plugin for Homebrew — delegates to the existing HomebrewClient."""

    ecosystem = "homebrew"

    manifests = [
        PluginManifest(glob="Brewfile", parser="parse_homebrew"),
        PluginManifest(glob="Brewfile.lock.json", parser="parse_homebrew"),
    ]

    @staticmethod
    def parse_homebrew(content: str) -> list[dict]:
        """Parse a Brewfile into a list of dependency dicts."""
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .homebrew_client import HomebrewClient

            self._legacy_client = HomebrewClient()
        return self._legacy_client

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        """Fetch package metadata from the registry."""
        client = self._get_client()
        return await client.get_package_info_async(package_name)

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        """Search for packages matching the query."""
        client = self._get_client()
        return await client.search_packages(query, limit=limit)
