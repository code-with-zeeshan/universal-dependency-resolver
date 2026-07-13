"""Crates.io (Rust) — EcosystemPlugin adapter delegating to legacy CratesClient."""

import logging
from typing import Any

from ..core.plugin import (
    EcosystemPlugin,
    PluginLockFile,
    PluginManifest,
    register_ecosystem,
)

logger = logging.getLogger(__name__)


@register_ecosystem("crates", name="Crates.io (Rust)", auth_prefix="CRATES")
class CratesPlugin(EcosystemPlugin):
    """Plugin for crates.io — delegates to the existing CratesClient."""

    ecosystem = "crates"

    manifests = [
        PluginManifest(glob="Cargo.toml", parser="parse_cargo_toml"),
    ]

    lock_files = [
        PluginLockFile(glob="Cargo.lock", parser="parse_cargo_lock"),
    ]

    # Manifest/lock parsers — thin stubs that delegate to ManifestDetector
    # at runtime via the static MANIFEST_PATTERNS list.

    @staticmethod
    def parse_cargo_toml(content: str) -> list[dict]:
        return []

    @staticmethod
    def parse_cargo_lock(content: str) -> dict[str, dict]:
        return {}

    _legacy_client = None

    def _get_client(self):
        if self._legacy_client is None:
            from .crates_client import CratesClient

            self._legacy_client = CratesClient()
        return self._legacy_client

    async def get_package_info(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        try:
            data = await client.get_package_info(package_name)
            return data
        except Exception:
            logger.exception("Crates plugin info error for %s", package_name)
            return None

    async def get_package_versions(
        self,
        package_name: str,
        filters: dict | None = None,
    ) -> list[dict]:
        client = self._get_client()
        try:
            return await client.get_package_versions(package_name, filters=filters)
        except Exception:
            logger.exception("Crates plugin versions error for %s", package_name)
            return []

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        client = self._get_client()
        try:
            return await client.search_packages(query, limit=limit)
        except Exception:
            logger.exception("Crates plugin search error for %s", query)
            return []

    async def get_artifact_hash(self, package_name: str, version: str) -> dict | None:
        client = self._get_client()
        return await client.get_artifact_hash(package_name, version)
