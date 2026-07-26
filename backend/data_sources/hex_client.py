"""Hex.pm (Elixir) package client."""

import logging
from typing import Any

from ..core.concurrency import get_semaphore
from ..core.utils import normalize_package_name
from ..settings import CACHE_TTL, get_ecosystem_config
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class HexClient(BaseDataSourceClient):
    """Client for hex.pm (Elixir/Erlang package registry)."""

    def __init__(
        self,
        cache_ttl: int | None = None,
        max_retries: int | None = None,
    ):
        """Initialize."""
        config = get_ecosystem_config("hex")
        super().__init__(
            ecosystem="hex",
            base_url=config.get("url", "https://hex.pm/api"),
            cache_ttl=cache_ttl or config.get("cache_ttl", CACHE_TTL),
        )
        self._sem = get_semaphore("hex", concurrency=10)

    async def get_package_info(
        self, package_name: str, include_dependencies: bool = True, include_versions: bool = True
    ) -> dict[str, Any] | None:
        """Get package info."""
        pkg = normalize_package_name(package_name)
        try:
            async with self._sem:
                data = await self._get(f"{self.base_url}/packages/{pkg}")
            if not data:
                return None
            releases = data.get("releases", [])
            versions = []
            for r in releases:
                v = r.get("version", "") if isinstance(r, dict) else str(r)
                versions.append({"version": v})
            latest = versions[0]["version"] if versions else "unknown"

            deps: dict[str, dict[str, str]] = {"dependencies": {}}
            if include_dependencies and versions:
                try:
                    async with self._sem:
                        release_data = await self._get(
                            f"{self.base_url}/packages/{pkg}/releases/{latest}"
                        )
                    if release_data and "requirements" in release_data:
                        for dep_name, dep_info in release_data["requirements"].items():
                            req = (
                                dep_info.get("requirement", "*")
                                if isinstance(dep_info, dict)
                                else "*"
                            )
                            deps["dependencies"][dep_name] = req
                except Exception:
                    logger.debug("Could not fetch dependencies for %s", pkg, exc_info=True)

            return {
                "name": pkg,
                "version": latest,
                "versions": versions,
                "dependencies": deps,
            }
        except Exception as e:
            logger.error("Hex error for %s: %s", package_name, e)
            return None

    async def get_package_versions(
        self, package_name: str, filters: dict | None = None
    ) -> list[dict]:
        """Get package versions."""
        info = await self.get_package_info(package_name, include_versions=True)
        return info.get("versions", []) if info else []
