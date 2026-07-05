"""Swift Package Manager client."""

import logging
import os
from typing import Any
from urllib.parse import quote

from ..core.utils import normalize_package_name
from ..settings import CACHE_TTL, get_ecosystem_config
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class SwiftClient(BaseDataSourceClient):
    """Client for the Swift Package Index (swiftpackageindex.com).

    Requires a SWIFT_API_KEY environment variable (or swift.api_key config)
    to authenticate with the Swift Package Index API.

    To obtain an API key:
        1. Go to https://swiftpackageindex.com
        2. Sign up / Sign in
        3. Profile → Settings → API Keys → Generate New Key
        4. Set SWIFT_API_KEY=<generated_key> in your .env file
    """

    def __init__(
        self,
        cache_ttl: int | None = None,
        max_retries: int | None = None,
        rate_limit_delay: float | None = None,
    ):
        config = get_ecosystem_config("swift")
        base_url = config.get("url", "https://swiftpackageindex.com").rstrip("/")
        self.api_key = config.get("api_key") or os.environ.get("SWIFT_API_KEY", "")
        if not self.api_key:
            logger.warning(
                "No SWIFT_API_KEY configured. Swift resolution requires an API key. "
                "See https://swiftpackageindex.com → Settings → API Keys"
            )
        super().__init__(
            ecosystem="swift",
            base_url=base_url,
            cache_ttl=cache_ttl or config.get("cache_ttl", CACHE_TTL),
        )

    async def get_package_info_async(
        self,
        package_name: str,
        include_dependencies: bool = True,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        """Standard async interface used by DataAggregator."""
        return await self.get_package_info(
            package_name,
            include_dependencies=include_dependencies,
            include_versions=include_versions,
        )

    def _get_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _search_package(self, name: str) -> dict | None:
        """Search for a package by name on Swift Package Index."""
        try:
            data = await self._get(
                f"{self.base_url}/api/search",
                params={"query": name, "page": "1", "pageSize": "5"},
                headers=self._get_headers(),
            )
            if not data:
                return None
            results = data.get("data", []) or data.get("results", [])
            for result in results:
                pkg_id = result.get("package", {}).get("id", "") or result.get("id", "")
                repo_name = result.get("repository", {}).get("name", "") or pkg_id
                if name.lower() in repo_name.lower():
                    owner_repo = result.get("package", {}).get("url", pkg_id)
                    parts = owner_repo.rstrip("/").rstrip(".git").split("/")
                    if len(parts) >= 2:
                        return {"owner": parts[-2], "repo": parts[-1]}
            return None
        except Exception as e:
            logger.debug("Swift search error for %s: %s", name, e)
            return None

    async def get_package_info(
        self, package_name: str, include_dependencies: bool = True, include_versions: bool = True
    ) -> dict[str, Any] | None:
        pkg = normalize_package_name(package_name)
        try:
            owner, repo = ([*pkg.split("/", 1), ""])[:2]
            if not repo:
                found = await self._search_package(owner)
                if found:
                    owner, repo = found["owner"], found["repo"]
                else:
                    repo = owner
            encoded_owner = quote(owner, safe="")
            encoded_repo = quote(repo, safe="")
            data = await self._get(
                f"{self.base_url}/api/packages/{encoded_owner}/{encoded_repo}",
                headers=self._get_headers(),
            )
            if not data:
                return None
            versions_raw = data.get("versions", [])
            if isinstance(versions_raw, list):
                versions = [
                    {"version": v.get("version", v) if isinstance(v, dict) else str(v)}
                    for v in versions_raw
                ]
            elif isinstance(versions_raw, dict):
                versions = [{"version": v} for v in versions_raw]
            else:
                versions = []
            version = versions[0]["version"] if versions else "unknown"
            deps = {}
            dep_data = data.get("dependencies", {}) or data.get("package", {}).get(
                "dependencies", {}
            )
            if isinstance(dep_data, dict):
                deps["dependencies"] = dep_data
            elif isinstance(dep_data, list):
                deps["dependencies"] = {}
            return {
                "name": pkg,
                "version": version,
                "versions": versions,
                "dependencies": deps,
            }
        except Exception as e:
            logger.error("Swift error for %s: %s", package_name, e)
            return None

    async def get_package_versions(
        self, package_name: str, filters: dict | None = None
    ) -> list[dict]:
        info = await self.get_package_info(package_name, include_versions=True)
        return info.get("versions", []) if info else []
