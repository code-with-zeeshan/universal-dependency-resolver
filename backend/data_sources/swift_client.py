"""Swift Package Manager client."""

import logging
from typing import Any

from ..core.utils import normalize_package_name
from ..settings import CACHE_TTL, get_ecosystem_config
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class SwiftClient(BaseDataSourceClient):
    """Client for the Swift Package Index (swiftpackageindex.com)."""

    def __init__(
        self,
        cache_ttl: int | None = None,
        max_retries: int | None = None,
        rate_limit_delay: float | None = None,
    ):
        config = get_ecosystem_config("swift")
        super().__init__(
            ecosystem="swift",
            base_url=config.get("url", "https://swiftpackageindex.com/api"),
            cache_ttl=cache_ttl or config.get("cache_ttl", CACHE_TTL),
        )

    async def get_package_info(
        self, package_name: str, include_dependencies: bool = True, include_versions: bool = True
    ) -> dict[str, Any] | None:
        pkg = normalize_package_name(package_name)
        try:
            owner, repo = ([*pkg.split("/", 1), ""])[:2]
            if not repo:
                repo = owner
            data = await self._get(f"{self.base_url}/packages/{owner}/{repo}")
            if not data:
                return None
            versions = [
                {"version": v.get("version", v) if isinstance(v, dict) else v}
                for v in data.get("versions", [])
            ]
            return {
                "name": pkg,
                "version": versions[0]["version"] if versions else "unknown",
                "versions": versions,
                "dependencies": {"dependencies": data.get("dependencies", {})},
            }
        except Exception as e:
            logger.error(f"Swift error for {package_name}: {e}")
            return None

    async def get_package_versions(
        self, package_name: str, filters: dict | None = None
    ) -> list[dict]:
        info = await self.get_package_info(package_name, include_versions=True)
        return info.get("versions", []) if info else []
