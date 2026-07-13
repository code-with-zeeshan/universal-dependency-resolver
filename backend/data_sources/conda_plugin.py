"""Conda — EcosystemPlugin adapter delegating to legacy CondaClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("conda", name="Conda (Anaconda)", auth_prefix="CONDA")
class CondaPlugin(EcosystemPlugin):
    """Plugin for the Conda package manager — delegates to the existing CondaClient."""

    ecosystem = "conda"

    manifests = [
        PluginManifest(glob="environment.yml", parser="parse_conda_env"),
        PluginManifest(glob="environment.yaml", parser="parse_conda_env"),
    ]

    @staticmethod
    def parse_conda_env(content: str) -> list[dict]:
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .conda_client import CondaClient

            self._legacy_client = CondaClient()
        return self._legacy_client

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        return await client.get_package_info_async(package_name)
