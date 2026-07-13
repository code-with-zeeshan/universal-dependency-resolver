"""CocoaPods — EcosystemPlugin adapter delegating to legacy CocoaPodsClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("cocoapods", name="CocoaPods (Objective-C/Swift)", auth_prefix="COCOAPODS")
class CocoaPodsPlugin(EcosystemPlugin):
    """Plugin for CocoaPods — delegates to the existing CocoaPodsClient."""

    ecosystem = "cocoapods"

    manifests = [
        PluginManifest(glob="Podfile", parser="parse_cocoapods"),
        PluginManifest(glob="Podfile.lock", parser="parse_cocoapods"),
    ]

    @staticmethod
    def parse_cocoapods(content: str) -> list[dict]:
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .cocoapods_client import CocoaPodsClient

            self._legacy_client = CocoaPodsClient()
        return self._legacy_client

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        return await client.get_package_info_async(package_name)

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        client = self._get_client()
        return await client.search_packages(query, limit=limit)
