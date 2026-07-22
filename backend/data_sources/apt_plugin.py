"""APT (Debian) — EcosystemPlugin adapter delegating to legacy APTClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("apt", name="APT (Debian/Ubuntu)", auth_prefix="APT")
class AptPlugin(EcosystemPlugin):
    """Plugin for APT packages — delegates to the existing APTClient."""

    ecosystem = "apt"

    manifests = [
        PluginManifest(glob="apt-packages.txt", parser="parse_simple"),
    ]

    @staticmethod
    def parse_simple(content: str) -> list[dict]:
        """Parse a simple package list into a list of dependency dicts."""
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .apt_client import APTClient

            self._legacy_client = APTClient()
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
