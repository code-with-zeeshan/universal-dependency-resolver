"""Maven — EcosystemPlugin adapter delegating to legacy MavenClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("maven", name="Maven Central", auth_prefix="MAVEN")
class MavenPlugin(EcosystemPlugin):
    """Plugin for Maven Central — delegates to the existing MavenClient."""

    ecosystem = "maven"

    manifests = [
        PluginManifest(glob="pom.xml", parser="parse_maven"),
    ]

    @staticmethod
    def parse_maven(content: str) -> list[dict]:
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .maven.client import MavenClient

            self._legacy_client = MavenClient()
        return self._legacy_client

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        return await client.get_package_info_async(
            package_name,
            include_dependencies=include_dependencies,
            include_versions=include_versions,
        )

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        client = self._get_client()
        return await client.search_packages(query, limit=limit)
