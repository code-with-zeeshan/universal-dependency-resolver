"""Gradle Plugin Portal client."""

import logging
from typing import Any

from ..core.utils import normalize_package_name
from ..settings import CACHE_TTL, get_ecosystem_config
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class GradleClient(BaseDataSourceClient):
    """Client for the Gradle Plugin Portal (plugins.gradle.org)."""

    def __init__(
        self,
        cache_ttl: int | None = None,
        max_retries: int | None = None,
        rate_limit_delay: float | None = None,
    ):
        config = get_ecosystem_config("gradle")
        super().__init__(
            ecosystem="gradle",
            base_url=config.get("url", "https://plugins.gradle.org/api"),
            cache_ttl=cache_ttl or config.get("cache_ttl", CACHE_TTL),
        )

    async def get_package_info(
        self, package_name: str, include_dependencies: bool = True, include_versions: bool = True
    ) -> dict[str, Any] | None:
        pkg = normalize_package_name(package_name)
        try:
            group, artifact = pkg.split(":", 1) if ":" in pkg else (pkg, pkg)
            data = await self._get(f"{self.base_url}/g/{group}/a/{artifact}")
            if not data:
                return None
            versions = data.get("versions", [])
            return {
                "name": pkg,
                "version": versions[0] if versions else "unknown",
                "versions": [{"version": v} for v in versions],
                "dependencies": {"dependencies": {}},
            }
        except Exception as e:
            logger.error(f"Gradle error for {package_name}: {e}")
            return None

    async def get_package_versions(
        self, package_name: str, filters: dict | None = None
    ) -> list[dict]:
        info = await self.get_package_info(package_name, include_versions=True)
        return info.get("versions", []) if info else []
