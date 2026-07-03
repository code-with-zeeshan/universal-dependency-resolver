"""Hackage (Haskell) package client."""
from typing import Dict, List, Optional, Any
import logging
from ..core.utils import normalize_package_name
from ..settings import CACHE_TTL, get_ecosystem_config
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class HaskellClient(BaseDataSourceClient):
    """Client for Hackage (hackage.haskell.org)."""

    def __init__(
        self,
        cache_ttl: Optional[int] = None,
        max_retries: Optional[int] = None,
        rate_limit_delay: Optional[float] = None,
    ):
        config = get_ecosystem_config("haskell")
        super().__init__(
            ecosystem="haskell",
            base_url=config.get("url", "https://hackage.haskell.org"),
            cache_ttl=cache_ttl or config.get("cache_ttl", CACHE_TTL),
        )

    async def get_package_info(
        self, package_name: str, include_dependencies: bool = True, include_versions: bool = True
    ) -> Optional[Dict[str, Any]]:
        pkg = normalize_package_name(package_name)
        try:
            data = await self._get(
                f"{self.base_url}/package/{pkg}/preferred"
            )
            if not data:
                return None
            versions_data = await self._get(
                f"{self.base_url}/package/{pkg}/preferred"
            )
            versions = []
            if versions_data:
                vs = versions_data if isinstance(versions_data, list) else []
                for v in vs:
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
        self, package_name: str, filters: Optional[Dict] = None
    ) -> List[Dict]:
        info = await self.get_package_info(package_name, include_versions=True)
        return info.get("versions", []) if info else []
