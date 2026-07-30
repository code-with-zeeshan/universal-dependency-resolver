"""Hackage (Haskell) package client."""

import logging
from typing import Any

from ..core.concurrency import get_semaphore
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
        self._sem = get_semaphore("haskell", concurrency=10)

    async def get_package_info(
        self, package_name: str, include_dependencies: bool = True, include_versions: bool = True
    ) -> dict[str, Any] | None:
        """Get package info."""
        pkg = normalize_package_name(package_name)
        try:
            async with self._sem:
                data = await self._get(f"{self.base_url}/package/{pkg}.json")
            if not data:
                return None

            versions = []
            deps: dict[str, dict[str, str]] = {"dependencies": {}}
            if isinstance(data, dict):
                # Hackage returns {"version": {...deps...}, ...} keyed by version
                for ver_str in data:
                    versions.append({"version": ver_str})
                    # Parse dependencies from the first (latest) version only
                    if include_dependencies and ver_str == next(iter(data.keys())):
                        ver_data = data[ver_str]
                        if isinstance(ver_data, dict):
                            raw_deps = ver_data.get("dependencies", [])
                            if isinstance(raw_deps, list):
                                for dep_entry in raw_deps:
                                    dep = (
                                        dep_entry.get("dependency", {})
                                        if isinstance(dep_entry, dict)
                                        else {}
                                    )
                                    dep_name = dep.get("package", {}).get("name", "")
                                    dep_ver = dep.get("version", "*")
                                    if dep_name:
                                        deps["dependencies"][dep_name] = dep_ver
                            elif isinstance(raw_deps, dict):
                                for dep_name, dep_ver in raw_deps.items():
                                    if isinstance(dep_ver, dict):
                                        dep_ver = dep_ver.get("version", "*")
                                    deps["dependencies"][dep_name] = str(dep_ver)
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
                "dependencies": deps,
            }
        except Exception as e:
            logger.error("Haskell error for %s: %s", package_name, e)
            return None

    async def get_package_versions(
        self, package_name: str, filters: dict | None = None
    ) -> list[dict]:
        """Get package versions."""
        info = await self.get_package_info(package_name, include_versions=True)
        return info.get("versions", []) if info else []
