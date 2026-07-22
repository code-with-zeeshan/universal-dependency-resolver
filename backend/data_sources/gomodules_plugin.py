"""Go Modules — EcosystemPlugin adapter delegating to legacy GoModulesClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("gomodules", name="Go Modules", auth_prefix="GOMODULES")
class GoModulesPlugin(EcosystemPlugin):
    """Plugin for Go modules — delegates to the existing GoModulesClient."""

    ecosystem = "gomodules"

    manifests = [
        PluginManifest(glob="go.mod", parser="parse_go_mod"),
    ]

    @staticmethod
    def parse_go_mod(content: str) -> list[dict]:
        """Parse a go.mod file into a list of dependency dicts."""
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .gomodules_client import GoModulesClient

            self._legacy_client = GoModulesClient()
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
