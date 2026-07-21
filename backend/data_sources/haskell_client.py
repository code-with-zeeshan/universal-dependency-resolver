"""Hackage (Haskell) package client."""

import logging
from typing import Any

from ..core.utils import normalize_package_name
from ..settings import CACHE_TTL, get_ecosystem_config
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class HaskellClient(BaseDataSourceClient):
    """Client for Hackage (hackage.haskell.org)."""

    def __init__(
        self,
        cache_ttl: int | None = None,
        max_retries: int | None = None,
    ):
        """Initialize."""
        config = get_ecosystem_config("haskell")
        super().__init__(
            ecosystem="haskell",
            base_url=config.get("url", "https://hackage.haskell.org"),
            cache_ttl=cache_ttl or config.get("cache_ttl", CACHE_TTL),
        )

    async def get_package_info(
        self, package_name: str, include_dependencies: bool = True, include_versions: bool = True
    ) -> dict[str, Any] | None:
        """Get package info."""
        pkg = normalize_package_name(package_name)
        try:
            data = await self._get(f"{self.base_url}/package/{pkg}.json")
            if not data:
                return None
            versions = []
            if isinstance(data, dict):
                # Hackage returns {"version": {...deps...}, ...}
                for ver_str in data:
                    versions.append({"version": ver_str})
            elif isinstance(data, list):
                for v in data:
                    if isinstance(v, dict):
                        versions.append({"version": v.get("version", "")})
                    elif isinstance(v, str):
                        versions.append({"version": v})
            return {
                "name": pkg,
                "version": versions[0]["version"] if versions else "unknown",
                "versions": versions,
                "dependencies": {"dependencies": {}},
            }
        except Exception as e:
            logger.error(f"Haskell error for {package_name}: {e}")
            return None

    async def get_package_versions(
        self, package_name: str, filters: dict | None = None
    ) -> list[dict]:
        """Get package versions."""
        info = await self.get_package_info(package_name, include_versions=True)
        return info.get("versions", []) if info else []
