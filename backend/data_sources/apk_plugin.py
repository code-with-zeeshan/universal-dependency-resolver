"""APK (Alpine) — EcosystemPlugin adapter delegating to legacy APKClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("apk", name="APK (Alpine Linux)", auth_prefix="APK")
class ApkPlugin(EcosystemPlugin):
    """Plugin for Alpine APK packages — delegates to the existing APKClient."""

    ecosystem = "apk"

    manifests = [
        PluginManifest(glob="apk-packages.txt", parser="parse_simple"),
    ]

    @staticmethod
    def parse_simple(content: str) -> list[dict]:
        """Parse a simple package list into a list of dependency dicts."""
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .apk_client import APKClient

            self._legacy_client = APKClient()
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
