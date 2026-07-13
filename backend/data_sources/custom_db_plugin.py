"""Custom DB (Compatibility Database) — EcosystemPlugin adapter.

This plugin wraps ``CompatibilityDB`` (synced from ``backend.database``)
and exposes it through the plugin interface.  It has no file-based
manifests — it only provides ``get_package_info`` for looking up
compatibility rules stored in the local database.
"""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("custom_db", name="Compatibility Database", auth_prefix="CUSTOM_DB")
class CustomDbPlugin(EcosystemPlugin):
    """Plugin for the local compatibility database — wraps CompatibilityDB."""

    ecosystem = "custom_db"

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from ..database.compatibility_db import CompatibilityDB

            self._legacy_client = CompatibilityDB()
        return self._legacy_client

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        import asyncio

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, client.get_compatibility_rules, package_name)
        return result if result else None
