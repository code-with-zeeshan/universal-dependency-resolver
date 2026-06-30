# data_sources/gomodules_client.py
from typing import Dict, List, Optional, Any
import json
import logging
import re
from backend.core.cache import cached
from backend.core.utils import (
    normalize_package_name,
    parse_version_key,
    run_async,
)
from backend.settings import (
    CACHE_TTL,
    get_ecosystem_config,
)
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class GoModulesClient(BaseDataSourceClient):
    def __init__(self):
        go_config = get_ecosystem_config("gomodules")

        super().__init__(
            ecosystem="gomodules",
            base_url=go_config.get("url", "https://proxy.golang.org"),
        )

        self.sum_db_url = go_config.get("sum_db_url", "https://sum.golang.org")
        self.pkg_dev_url = "https://pkg.go.dev"

    async def package_exists(self, package_name: str) -> bool:
        package_name = self._normalize_go_module_path(package_name)
        try:
            session = self._get_session()
            response = await session.head(f"{self.base_url}/{package_name}/@v/list")
            return response.status == 200
        except Exception:
            return False

    async def search_packages(
        self, query: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        query = normalize_package_name(query)

        try:
            logger.warning(
                "Go package search not fully implemented - requires web scraping"
            )
            return []
        except Exception as e:
            logger.error(f"Error searching Go packages: {e}")
            return []

    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(
        self, package_name: str
    ) -> Optional[Dict[str, Any]]:
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
            "version": latest_version,
            "versions": versions_data,
            "description": f"Go module: {package_name}",
            "homepage": f"https://pkg.go.dev/{package_name}",
            "repository": f"https://{package_name}",
            "license": "See repository",
            "dependencies": dependencies,
            "system_requirements": {
                "go": {"min_version": self._extract_go_version(module_info)}
            },
            "ecosystem": "gomodules",
        }

        return info

    def get_package_info(self, package_name: str) -> Optional[Dict[str, Any]]:
        package_name = self._normalize_go_module_path(package_name)
        return run_async(self.get_package_info_async(package_name))

    async def get_package_version(
        self, package_name: str, version: str
    ) -> Optional[Dict[str, Any]]:
        package_name = self._normalize_go_module_path(package_name)

        if not version.startswith("v"):
            version = f"v{version}"

        module_info = await self._get_module_info(package_name, version)
        if not module_info:
            return None

        dependencies = await self._parse_go_mod(module_info)

        return {
            "name": package_name,
            "version": version,
            "dependencies": dependencies,
            "system_requirements": {
                "go": {"min_version": self._extract_go_version(module_info)}
            },
        }

    async def get_versions(self, package_name: str) -> List[Dict[str, Any]]:
        package_name = self._normalize_go_module_path(package_name)
        versions_data = await self._get_versions_list(package_name)

        if not versions_data:
            return []

        versions: List[Any] = []
        for ver in versions_data:
            ver_info = {
                "version": ver,
                "stable": not ("-" in ver or "+incompatible" in ver),
                "upload_time": None,
            }
            versions.append(ver_info)

        versions.sort(
            key=lambda x: parse_version_key(x["version"].lstrip("v")),
            reverse=True,
        )

        return versions

    async def get_dependencies(
        self, package_name: str, version: Optional[str] = None
    ) -> Dict[str, Any]:
        package_name = self._normalize_go_module_path(package_name)

        if not version:
            version = await self._get_latest_version(package_name)
        elif not version.startswith("v"):
            version = f"v{version}"

        module_info = await self._get_module_info(package_name, version)  # type: ignore[arg-type]
        if not module_info:
            return {}

        return await self._parse_go_mod(module_info)

    async def _get_versions_list(self, package_name: str) -> Optional[List[str]]:
        url = f"{self.base_url}/{package_name}/@v/list"
        data = await self._make_request(url)

        if data and isinstance(data, str):
            versions = [v.strip() for v in data.strip().split("\n") if v.strip()]
            return versions
        return None

    async def _get_latest_version(self, package_name: str) -> Optional[str]:
        url = f"{self.base_url}/{package_name}/@latest"
        data = await self._make_request(url)

        if data and isinstance(data, dict):
            return data.get("Version")
        return None

    async def _get_module_info(
        self, package_name: str, version: str
    ) -> Optional[Dict[str, Any]]:
        info_url = f"{self.base_url}/{package_name}/@v/{version}.info"
        info_data = await self._make_request(info_url)

        mod_url = f"{self.base_url}/{package_name}/@v/{version}.mod"
        mod_data = await self._make_request(mod_url)

        if info_data and mod_data:
            return {
                "info": info_data
                if isinstance(info_data, dict)
                else json.loads(info_data),
                "go_mod": mod_data if isinstance(mod_data, str) else "",
            }
        return None

    async def _make_request(  # type: ignore[override]
        self, url: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Any]:
        session = self._get_session()
        try:
            async with session.get(url, params=params) as response:
                if response.status == 404:
                    return None

                if response.status != 200:
                    logger.error(f"HTTP {response.status} from {url}")
                    return None

                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return await response.json()
                else:
                    return await response.text()
        except Exception as e:
            logger.error(f"Request error for {url}: {e}")
            return None

    async def _parse_go_mod(self, module_info: Dict[str, Any]) -> Dict[str, Any]:
        dependencies: Dict[str, Any] = {"required": {}, "indirect": {}, "replace": {}}

        go_mod_content = module_info.get("go_mod", "")
        if not go_mod_content:
            return dependencies

        require_block = False
        for line in go_mod_content.split("\n"):
            line = line.strip()

            if line.startswith("require ("):
                require_block = True
                continue
            elif line == ")" and require_block:
                require_block = False
                continue

            if require_block or line.startswith("require "):
                match = re.match(
                    r"(?:require\s+)?([^\s]+)\s+([^\s]+)(?:\s+//\s+indirect)?", line
                )
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

    def _extract_go_version(self, module_info: Dict[str, Any]) -> Optional[str]:
        go_mod_content = module_info.get("go_mod", "")

        match = re.search(
            r"^\s*go\s+(\d+\.\d+(?:\.\d+)?)", go_mod_content, re.MULTILINE
        )
        if match:
            return match.group(1)
        return None

    def _normalize_go_module_path(self, path: str) -> str:
        path = path.strip()
        if path.startswith("github.com/") or path.startswith("golang.org/"):
            return path

        if "/" not in path:
            return f"github.com/{path}/{path}"

        return path
