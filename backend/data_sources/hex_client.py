"""Hex.pm (Elixir) package client."""
from typing import Dict, List, Optional, Any
import logging
from ..core.utils import normalize_package_name
from ..settings import CACHE_TTL, get_ecosystem_config
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class HexClient(BaseDataSourceClient):
    """Client for hex.pm (Elixir/Erlang package registry)."""

    def __init__(
        self,
        cache_ttl: Optional[int] = None,
        max_retries: Optional[int] = None,
        rate_limit_delay: Optional[float] = None,
    ):
        config = get_ecosystem_config("hex")
        super().__init__(
            ecosystem="hex",
            base_url=config.get("url", "https://hex.pm/api"),
            cache_ttl=cache_ttl or config.get("cache_ttl", CACHE_TTL),
        )

    async def get_package_info(
        self, package_name: str, include_dependencies: bool = True, include_versions: bool = True
    ) -> Optional[Dict[str, Any]]:
        pkg = normalize_package_name(package_name)
        try:
            data = await self._get(f"{self.base_url}/packages/{pkg}")
            if not data:
                return None
            releases = data.get("releases", [])
            versions = []
            for r in releases:
                v = r.get("version", "") if isinstance(r, dict) else str(r)
                versions.append({"version": v})
            latest = versions[0]["version"] if versions else "unknown"
            return {
                "name": pkg,
                "version": latest,
                "versions": versions,
                "dependencies": {"dependencies": {}},
            }
        except Exception as e:
            logger.error(f"Hex error for {package_name}: {e}")
            return None

    async def get_package_versions(
        self, package_name: str, filters: Optional[Dict] = None
    ) -> List[Dict]:
        info = await self.get_package_info(package_name, include_versions=True)
        return info.get("versions", []) if info else []
