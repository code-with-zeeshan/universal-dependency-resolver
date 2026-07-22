"""RubyGems — EcosystemPlugin adapter delegating to legacy RubyGemsClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("rubygems", name="RubyGems (Ruby)", auth_prefix="RUBYGEMS")
class RubyGemsPlugin(EcosystemPlugin):
    """Plugin for RubyGems — delegates to the existing RubyGemsClient."""

    ecosystem = "rubygems"

    manifests = [
        PluginManifest(glob="Gemfile", parser="parse_gemfile"),
        PluginManifest(glob="Gemfile.lock", parser="parse_gemfile_lock"),
    ]

    @staticmethod
    def parse_gemfile(content: str) -> list[dict]:
        """Parse a Gemfile into a list of dependency dicts."""
        return []

    @staticmethod
    def parse_gemfile_lock(content: str) -> list[dict]:
        """Parse a Gemfile.lock into a list of dependency dicts."""
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .rubygems_client import RubyGemsClient

            self._legacy_client = RubyGemsClient()
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

    async def get_artifact_hash(self, package_name: str, version: str) -> dict | None:
        """Get integrity hash for a specific package version."""
        client = self._get_client()
        return await client.get_artifact_hash(package_name, version)
