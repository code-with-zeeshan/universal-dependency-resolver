"""Module docstring."""

# data_sources/gomodules_client.py
import asyncio
import logging
import re
from typing import Any

import aiohttp

from backend.core.cache import cached
from backend.core.utils import (
    normalize_package_name,
    parse_version_key,
    run_async,
)
from backend.settings import (
    CACHE_TTL,
    RETRY_BACKOFF_FACTOR,
    get_ecosystem_config,
)

from ..core._json import loads
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


# Rate limiter: shared across all Go client instances
_GO_SEMAPHORE = asyncio.Semaphore(8)


def _strip_v(version: str) -> str:
    """Strip leading 'v' prefix from Go version strings for PEP 440 compatibility."""
    """Strip leading 'v' prefix from Go version strings for PEP 440 compatibility."""
    if version.startswith("v") and len(version) > 1 and version[1].isdigit():
        return version[1:]
    return version


class GoModulesClient(BaseDataSourceClient):
    """GoModulesClient."""
    def __init__(self):
        """Initialize."""
        go_config = get_ecosystem_config("gomodules")

        super().__init__(
            ecosystem="gomodules",
            base_url=go_config.get("url", "https://proxy.golang.org"),
        )

        self.sum_db_url = go_config.get("sum_db_url", "https://sum.golang.org")
        self.pkg_dev_url = "https://pkg.go.dev"

    async def package_exists(self, package_name: str) -> bool:
        """async package exists."""
        """async package exists."""
        package_name = self._normalize_go_module_path(package_name)
        try:
            session = self._get_session()
            async with _GO_SEMAPHORE:
                response = await session.head(f"{self.base_url}/{package_name}/@v/list")
            return response.status == 200
        except Exception:
            return False

    async def search_packages(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """async search packages."""
        """async search packages."""
        query = normalize_package_name(query)

        try:
            logger.warning("Go package search not fully implemented - requires web scraping")
            return []
        except Exception as e:
            logger.error(f"Error searching Go packages: {e}")
            return []

    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(self, package_name: str) -> dict[str, Any] | None:
        """async get package info async."""
        """async get package info async."""
        package_name = self._normalize_go_module_path(package_name)

        versions_data = await self._get_versions_list(package_name)
        if not versions_data:
            return None

        latest_version = await self._get_latest_version(package_name)
        if not latest_version:
            return None

        module_info = await self._get_module_info(package_name, latest_version)  # type: ignore[arg-type]
        if not module_info:
            return None

        dependencies = await self._parse_go_mod(module_info)

        info = {
            "name": package_name,
            "version": _strip_v(latest_version),
            "versions": [_strip_v(v) for v in versions_data],
            "description": f"Go module: {package_name}",
            "homepage": f"https://pkg.go.dev/{package_name}",
            "repository": f"https://{package_name}",
            "license": "See repository",
            "dependencies": dependencies,
            "system_requirements": {"go": {"min_version": self._extract_go_version(module_info)}},
            "ecosystem": "gomodules",
        }

        return info

    def get_package_info(self, package_name: str) -> dict[str, Any] | None:
        """get package info."""
        """get package info."""
        package_name = self._normalize_go_module_path(package_name)
        return run_async(self.get_package_info_async(package_name))

    async def get_package_version(self, package_name: str, version: str) -> dict[str, Any] | None:
        """async get package version."""
        """async get package version."""
        package_name = self._normalize_go_module_path(package_name)

        if not version.startswith("v") and not version.startswith("0"):
            version = f"v{version}"

        module_info = await self._get_module_info(package_name, version)
        if not module_info:
            return None

        dependencies = await self._parse_go_mod(module_info)

        return {
            "name": package_name,
            "version": _strip_v(version),
            "dependencies": dependencies,
            "system_requirements": {"go": {"min_version": self._extract_go_version(module_info)}},
        }

    async def get_versions(self, package_name: str) -> list[dict[str, Any]]:
        """async get versions."""
        """async get versions."""
        package_name = self._normalize_go_module_path(package_name)
        versions_data = await self._get_versions_list(package_name)

        if not versions_data:
            return []

        versions: list[Any] = []
        for ver in versions_data:
            clean = _strip_v(ver)
            ver_info = {
                "version": clean,
                "stable": not ("-" in ver or "+incompatible" in ver),
                "upload_time": None,
            }
            versions.append(ver_info)

        versions.sort(
            key=lambda x: parse_version_key(x["version"]),
            reverse=True,
        )

        return versions

    async def get_dependencies(
        self, package_name: str, version: str | None = None
    ) -> dict[str, Any]:
        """get dependencies."""
        package_name = self._normalize_go_module_path(package_name)

        if not version:
            version = await self._get_latest_version(package_name)
        elif not version.startswith("v"):
            version = f"v{version}"

        module_info = await self._get_module_info(package_name, version)  # type: ignore[arg-type]
        if not module_info:
            return {}

        return await self._parse_go_mod(module_info)

    async def _get_versions_list(self, package_name: str) -> list[str] | None:
        url = f"{self.base_url}/{package_name}/@v/list"
        data = await self._make_request(url)

        if data and isinstance(data, str):
            versions = [v.strip() for v in data.strip().split("\n") if v.strip()]
            return versions
        return None

    async def _get_latest_version(self, package_name: str) -> str | None:
        url = f"{self.base_url}/{package_name}/@latest"
        data = await self._make_request(url)

        if data and isinstance(data, dict):
            return data.get("Version")
        return None

    async def _get_module_info(self, package_name: str, version: str) -> dict[str, Any] | None:
        info_url = f"{self.base_url}/{package_name}/@v/{version}.info"
        info_data = await self._make_request(info_url)

        mod_url = f"{self.base_url}/{package_name}/@v/{version}.mod"
        mod_data = await self._make_request(mod_url)

        if info_data and mod_data:
            return {
                "info": info_data if isinstance(info_data, dict) else loads(info_data),
                "go_mod": mod_data if isinstance(mod_data, str) else "",
            }
        return None

    async def _make_request(  # type: ignore[override]
        self, url: str, params: dict[str, Any] | None = None
    ) -> Any | None:
        await self._throttle()
        session = self._get_session()
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with (
                    _GO_SEMAPHORE,
                    session.get(
                        url,
                        params=params,
                        headers=self._auth_headers or None,
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ) as response,
                ):
                    if response.status == 404:
                        return None
                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            wait = int(retry_after) if retry_after.isdigit() else 5
                        else:
                            wait = RETRY_BACKOFF_FACTOR**attempt
                        if attempt < self.max_retries - 1:
                            logger.debug(
                                f"429 from {url}, retrying in {wait}s (attempt {attempt + 1})"
                            )
                            await asyncio.sleep(wait)
                            continue
                        logger.error(f"429 from {url} after {self.max_retries} retries")
                        return None
                    if response.status >= 500 and attempt < self.max_retries - 1:
                        wait = RETRY_BACKOFF_FACTOR**attempt
                        logger.debug(f"{response.status} from {url}, retrying in {wait}s")
                        await asyncio.sleep(wait)
                        continue
                    if response.status != 200:
                        logger.error(f"HTTP {response.status} from {url}")
                        return None
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        return await response.json()
                    return await response.text()
            except (TimeoutError, aiohttp.ClientError) as e:
                last_error = e
                if attempt == self.max_retries - 1:
                    logger.error(f"Request error for {url} after {self.max_retries} retries: {e}")
                    return None
                await asyncio.sleep(RETRY_BACKOFF_FACTOR**attempt)
        if last_error:
            logger.error(f"Request error for {url}: {last_error}")
        return None

    async def _parse_go_mod(self, module_info: dict[str, Any]) -> dict[str, Any]:
        dependencies: dict[str, Any] = {"required": {}, "indirect": {}, "replace": {}}

        go_mod_content = module_info.get("go_mod", "")
        if not go_mod_content:
            return dependencies

        require_block = False
        for line in go_mod_content.split("\n"):
            line = line.strip()

            if line.startswith("require ("):
                require_block = True
                continue
            if line == ")" and require_block:
                require_block = False
                continue

            if require_block or line.startswith("require "):
                match = re.match(r"(?:require\s+)?([^\s]+)\s+([^\s]+)(?:\s+//\s+indirect)?", line)
                if match:
                    dep_name = match.group(1)
                    dep_version = match.group(2)

                    if "// indirect" in line:
                        dependencies["indirect"][dep_name] = dep_version
                    else:
                        dependencies["required"][dep_name] = dep_version

            if line.startswith("replace "):
                match = re.match(
                    r"replace\s+([^\s]+)(?:\s+[^\s]+)?\s+=>\s+([^\s]+)\s+([^\s]+)", line
                )
                if match:
                    old_path = match.group(1)
                    new_path = match.group(2)
                    new_version = match.group(3)
                    dependencies["replace"][old_path] = f"{new_path}@{new_version}"

        return dependencies

    def _extract_go_version(self, module_info: dict[str, Any]) -> str | None:
        go_mod_content = module_info.get("go_mod", "")

        match = re.search(r"^\s*go\s+(\d+\.\d+(?:\.\d+)?)", go_mod_content, re.MULTILINE)
        if match:
            return match.group(1)
        return None

    def _normalize_go_module_path(self, path: str) -> str:
        path = path.strip()
        if path.startswith(("github.com/", "golang.org/")):
            return path

        if "/" not in path:
            return f"github.com/{path}/{path}"

        return path
