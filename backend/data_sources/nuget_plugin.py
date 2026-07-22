"""NuGet (.NET) — EcosystemPlugin adapter delegating to legacy NuGetClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("nuget", name="NuGet (.NET)", auth_prefix="NUGET")
class NuGetPlugin(EcosystemPlugin):
    """Plugin for NuGet — delegates to the existing NuGetClient."""

    ecosystem = "nuget"

    manifests = [
        PluginManifest(glob="packages.config", parser="parse_nuget"),
    ]

    @staticmethod
    def parse_nuget(content: str) -> list[dict]:
        """Parse a NuGet packages.config into a list of dependency dicts."""
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .nuget_client import NuGetClient

            self._legacy_client = NuGetClient()
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
