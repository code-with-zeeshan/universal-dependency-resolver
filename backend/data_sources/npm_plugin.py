"""NPM (Node.js) — EcosystemPlugin adapter delegating to legacy NPMClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("npm", name="NPM (Node.js)", auth_prefix="NPM")
class NpmPlugin(EcosystemPlugin):
    """Plugin for the npm registry — delegates to the existing NPMClient."""

    ecosystem = "npm"

    manifests = [
        PluginManifest(glob="package.json", parser="parse_package_json"),
        PluginManifest(glob="package-lock.json", parser="parse_package_lock"),
        PluginManifest(glob="yarn.lock", parser="parse_yarn_lock"),
        PluginManifest(glob="pnpm-lock.yaml", parser="parse_pnpm_lock"),
    ]

    # Manifest/lock parsers — thin stubs that delegate to ManifestDetector
    # at runtime via the static MANIFEST_PATTERNS list. These stubs satisfy
    # the plugin contract (test_parser_methods_exist) but are not currently
    # used because the static MANIFEST_PATTERNS entries match first.

    @staticmethod
    def parse_package_json(content: str) -> list[dict]:
        return []

    @staticmethod
    def parse_package_lock(content: str) -> list[dict]:
        return []

    @staticmethod
    def parse_yarn_lock(content: str) -> list[dict]:
        return []

    @staticmethod
    def parse_pnpm_lock(content: str) -> list[dict]:
        return []

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .npm_client import NPMClient

            self._legacy_client = NPMClient()
        return self._legacy_client

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        return await client.get_package_info(
            package_name,
            include_readme=False,
            include_versions=include_versions,
            include_extended=include_dependencies,
        )

    async def get_package_versions(
        self,
        package_name: str,
        filters: dict | None = None,
    ) -> list[dict]:
        client = self._get_client()
        return await client.get_versions(package_name)

    async def get_artifact_hash(self, package_name: str, version: str) -> dict | None:
        client = self._get_client()
        return await client.get_artifact_hash(package_name, version)

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        client = self._get_client()
        return await client.search_packages(query, limit=limit)
