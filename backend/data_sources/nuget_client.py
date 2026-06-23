# nuget_client.py
import aiohttp
import asyncio
from typing import Dict, List, Optional, Set, Tuple, Any, Union
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import quote
from backend.core.utils import normalize_package_name, parse_version, run_async
import re
from backend.core.cache import cache_manager, cached, CacheKeys
from enum import Enum
import hashlib
from dataclasses import dataclass
from collections import defaultdict
from backend.settings import (
    NUGET_URL,
    NUGET_API_URL,
    CACHE_TTL,
    CACHE_TTL_SHORT,
    RATE_LIMIT_DELAY,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    CONNECT_TIMEOUT,
    USER_AGENTS,
    RATE_LIMITS,
    RETRY_BACKOFF_FACTOR,
    RETRY_MAX_DELAY,
    ENABLE_CACHE,
    get_ecosystem_config,
)
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    DEPENDENCY = "dependency"
    DEVELOPMENT = "development"


class TargetFramework(Enum):
    NET_FRAMEWORK_48 = "net48"
    NET_FRAMEWORK_472 = "net472"
    NET_FRAMEWORK_461 = "net461"
    NET_STANDARD_20 = "netstandard2.0"
    NET_STANDARD_21 = "netstandard2.1"
    NET_5 = "net5.0"
    NET_6 = "net6.0"
    NET_7 = "net7.0"
    NET_8 = "net8.0"


@dataclass
class NuGetVersionRequirement:
    raw: str
    operator: Optional[str] = None
    major: Optional[int] = None
    minor: Optional[int] = None
    patch: Optional[int] = None
    is_floating: bool = False


class NuGetClient(BaseDataSourceClient):
    def __init__(
        self,
        service_index_url: str = None,
        cache_ttl: int = None,
        max_retries: int = None,
        rate_limit_delay: float = None,
        timeout: int = None,
    ):
        nuget_config = get_ecosystem_config("nuget")

        service_index_url = (
            service_index_url or nuget_config.get("api_url", NUGET_API_URL)
        ).rstrip("/")
        super().__init__(
            ecosystem="nuget",
            base_url=service_index_url,
            cache_ttl=cache_ttl or nuget_config.get("cache_ttl", CACHE_TTL),
            user_agent=USER_AGENTS.get("nuget", USER_AGENTS["default"]),
            rate_limit=nuget_config.get("rate_limit", RATE_LIMITS.get("nuget", 600)),
            timeout=timeout or REQUEST_TIMEOUT,
            max_retries=MAX_RETRIES,
        )

        self.base_url = NUGET_URL
        self.service_index_url = service_index_url
        self.search_url = None
        self.package_base_url = None
        self.registration_base_url = None
        self._version_cache: Dict[str, NuGetVersionRequirement] = {}
        self._service_endpoints: Dict[str, str] = {}

    async def __aenter__(self):
        await self._initialize_service_endpoints()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def _initialize_service_endpoints(self):
        if self._service_endpoints:
            return

        try:
            data = await self._get(self.service_index_url)
            if not data or "resources" not in data:
                self._set_fallback_endpoints()
                return

            for resource in data["resources"]:
                resource_type = resource.get("@type", "")
                resource_id = resource.get("@id", "")

                if "SearchQueryService" in resource_type:
                    self.search_url = resource_id
                elif "PackageBaseAddress" in resource_type:
                    self.package_base_url = resource_id
                elif "RegistrationsBaseUrl" in resource_type:
                    self.registration_base_url = resource_id

            self._service_endpoints = {
                "search": self.search_url,
                "package_base": self.package_base_url,
                "registration_base": self.registration_base_url,
            }

        except Exception as e:
            logger.warning(f"Failed to initialize NuGet service endpoints: {e}")
            self._set_fallback_endpoints()

    def _set_fallback_endpoints(self):
        self.search_url = "https://azuresearch-usnc.nuget.org/query"
        self.package_base_url = "https://api.nuget.org/v3-flatcontainer"
        self.registration_base_url = "https://api.nuget.org/v3/registration5-semver1"

    def package_exists(self, package_name: str) -> bool:
        package_name = normalize_package_name(package_name)
        try:
            import requests

            url = f"{self.package_base_url or 'https://api.nuget.org/v3-flatcontainer'}/{package_name.lower()}/index.json"
            response = requests.head(url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    async def search_packages(
        self,
        query: str,
        limit: int = 20,
        include_prerelease: bool = False,
        target_framework: Optional[str] = None,
    ) -> List[Dict]:
        query = normalize_package_name(query)

        if not self.search_url:
            await self._initialize_service_endpoints()

        params = {
            "q": query,
            "take": min(limit, 1000),
            "prerelease": str(include_prerelease).lower(),
        }

        if target_framework:
            params["supportedFramework"] = target_framework

        data = await self._get(self.search_url, params=params)
        if not data or "data" not in data:
            return []

        results = []
        for package in data["data"]:
            result = {
                "name": package.get("id"),
                "version": package.get("version"),
                "title": package.get("title"),
                "description": package.get("description"),
                "summary": package.get("summary"),
                "authors": package.get("authors", []),
                "owners": package.get("owners", []),
                "tags": package.get("tags", []),
                "project_url": package.get("projectUrl"),
                "license_url": package.get("licenseUrl"),
                "icon_url": package.get("iconUrl"),
                "download_count": package.get("totalDownloads", 0),
                "verified": package.get("verified", False),
                "package_types": package.get("packageTypes", []),
                "versions": self._extract_version_info(package.get("versions", [])),
            }
            results.append(result)

        return results

    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(
        self, package_name: str, include_versions: bool = True
    ) -> Optional[Dict]:
        package_name = normalize_package_name(package_name)

        if not self.registration_base_url:
            await self._initialize_service_endpoints()

        url = f"{self.registration_base_url}/{package_name.lower()}/index.json"
        data = await self._get(url)
        if not data:
            return None

        info = {
            "name": package_name,
            "registration_url": url,
            "count": data.get("count", 0),
            "items": [],
        }

        versions_info = []
        latest_version = None
        latest_data = None

        for item in data.get("items", []):
            if "items" in item:
                for catalog_entry in item["items"]:
                    entry_data = catalog_entry.get("catalogEntry", {})
                    version_info = self._process_catalog_entry(entry_data)
                    if version_info:
                        versions_info.append(version_info)
                        if not latest_version or self._is_newer_version(
                            version_info["version"], latest_version
                        ):
                            latest_version = version_info["version"]
                            latest_data = entry_data
            else:
                page_url = item.get("@id")
                if page_url:
                    page_data = await self._get(page_url)
                    if page_data and "items" in page_data:
                        for catalog_entry in page_data["items"]:
                            entry_data = catalog_entry.get("catalogEntry", {})
                            version_info = self._process_catalog_entry(entry_data)
                            if version_info:
                                versions_info.append(version_info)
                                if not latest_version or self._is_newer_version(
                                    version_info["version"], latest_version
                                ):
                                    latest_version = version_info["version"]
                                    latest_data = entry_data

        versions_info.sort(
            key=lambda x: parse_version(x["version"]) or parse_version("0.0.0"),
            reverse=True,
        )

        if latest_data:
            info.update(
                {
                    "version": latest_version,
                    "title": latest_data.get("title"),
                    "description": latest_data.get("description"),
                    "summary": latest_data.get("summary"),
                    "authors": latest_data.get("authors", "").split(",")
                    if latest_data.get("authors")
                    else [],
                    "owners": latest_data.get("owners", "").split(",")
                    if latest_data.get("owners")
                    else [],
                    "tags": latest_data.get("tags", []),
                    "project_url": latest_data.get("projectUrl"),
                    "license_url": latest_data.get("licenseUrl"),
                    "license_expression": latest_data.get("licenseExpression"),
                    "icon_url": latest_data.get("iconUrl"),
                    "require_license_acceptance": latest_data.get(
                        "requireLicenseAcceptance", False
                    ),
                    "package_types": latest_data.get("packageTypes", []),
                    "repository": self._extract_repository_info(latest_data),
                    "dependencies": self._extract_dependencies(
                        latest_data.get("dependencyGroups", [])
                    ),
                    "system_requirements": self._extract_system_requirements(
                        latest_data
                    ),
                    "versions": versions_info if include_versions else [],
                    "published": latest_data.get("published"),
                    "created": latest_data.get("created"),
                    "last_edited": latest_data.get("lastEdited"),
                }
            )

        return info

    def get_package_info(self, package_name: str) -> Dict:
        package_name = normalize_package_name(package_name)
        return run_async(self.get_package_info_async(package_name))

    async def get_package_version(
        self, package_name: str, version: str
    ) -> Optional[Dict]:
        package_name = normalize_package_name(package_name)

        if not self.registration_base_url:
            await self._initialize_service_endpoints()

        url = f"{self.registration_base_url}/{package_name.lower()}/{version.lower()}.json"
        data = await self._get(url)

        if not data:
            return None

        catalog_entry = data.get("catalogEntry", {})
        return self._process_catalog_entry(catalog_entry)

    async def get_versions(
        self,
        package_name: str,
        include_prereleases: bool = True,
        include_unlisted: bool = False,
    ) -> List[Dict]:
        package_name = normalize_package_name(package_name)

        info = await self.get_package_info_async(package_name, include_versions=True)
        if not info or not info.get("versions"):
            return []

        versions = []
        for v in info["versions"]:
            if not include_prereleases and v.get("is_prerelease", False):
                continue

            if not include_unlisted and not v.get("listed", True):
                continue

            versions.append(v)

        return versions

    async def get_dependencies(
        self,
        package_name: str,
        version: Optional[str] = None,
        target_framework: Optional[str] = None,
    ) -> Dict[str, Any]:
        package_name = normalize_package_name(package_name)

        if version:
            pkg_data = await self.get_package_version(package_name, version)
        else:
            pkg_data = await self.get_package_info_async(
                package_name, include_versions=False
            )

        if not pkg_data:
            return {}

        dependencies = pkg_data.get("dependencies", {})

        if target_framework and target_framework in dependencies:
            return {target_framework: dependencies[target_framework]}

        return dependencies

    def _process_catalog_entry(self, entry: Dict) -> Optional[Dict]:
        if not entry:
            return None

        version = entry.get("version")
        if not version or parse_version(version) is None:
            return None

        return {
            "version": version,
            "title": entry.get("title"),
            "description": entry.get("description"),
            "summary": entry.get("summary"),
            "authors": entry.get("authors", "").split(",")
            if entry.get("authors")
            else [],
            "tags": entry.get("tags", []),
            "project_url": entry.get("projectUrl"),
            "license_url": entry.get("licenseUrl"),
            "license_expression": entry.get("licenseExpression"),
            "icon_url": entry.get("iconUrl"),
            "require_license_acceptance": entry.get("requireLicenseAcceptance", False),
            "is_prerelease": self._is_prerelease(version),
            "listed": entry.get("listed", True),
            "dependencies": self._extract_dependencies(
                entry.get("dependencyGroups", [])
            ),
            "package_types": entry.get("packageTypes", []),
            "published": entry.get("published"),
            "created": entry.get("created"),
            "last_edited": entry.get("lastEdited"),
            "system_requirements": self._extract_system_requirements(entry),
        }

    def _extract_version_info(self, versions: List[Dict]) -> List[Dict]:
        version_info = []
        for v in versions:
            version = v.get("version")
            if version and parse_version(version):
                version_info.append(
                    {
                        "version": version,
                        "download_count": v.get("downloads", 0),
                        "published": v.get("@id"),
                    }
                )

        version_info.sort(
            key=lambda x: parse_version(x["version"]) or parse_version("0.0.0"),
            reverse=True,
        )

        return version_info

    def _extract_dependencies(self, dependency_groups: List[Dict]) -> Dict[str, Dict]:
        dependencies = {}

        for group in dependency_groups:
            target_framework = group.get("targetFramework", "any")
            deps = {}

            for dep in group.get("dependencies", []):
                name = dep.get("id")
                version_range = dep.get("range", "")

                if name:
                    deps[name] = {
                        "version_range": version_range,
                        "exclude": dep.get("exclude", []),
                        "include": dep.get("include", []),
                    }

            if deps:
                dependencies[target_framework] = deps

        return dependencies

    def _extract_system_requirements(self, entry: Dict) -> Dict[str, Any]:
        requirements = {
            "target_frameworks": [],
            "min_client_version": None,
            "development_dependency": False,
            "service_pack": None,
        }

        dependency_groups = entry.get("dependencyGroups", [])
        for group in dependency_groups:
            tf = group.get("targetFramework")
            if tf and tf not in requirements["target_frameworks"]:
                requirements["target_frameworks"].append(tf)

        requirements["min_client_version"] = entry.get("minClientVersion")
        requirements["development_dependency"] = entry.get(
            "developmentDependency", False
        )

        return requirements

    def _extract_repository_info(self, entry: Dict) -> Optional[Dict]:
        repo = entry.get("repository")
        if repo:
            return {
                "type": repo.get("type"),
                "url": repo.get("url"),
                "branch": repo.get("branch"),
                "commit": repo.get("commit"),
            }
        return None

    def _is_prerelease(self, version: str) -> bool:
        return bool(re.search(r"-(alpha|beta|rc|pre|preview)", version.lower()))

    def _is_newer_version(self, version1: str, version2: str) -> bool:
        v1 = parse_version(version1)
        v2 = parse_version(version2)

        if v1 and v2:
            return v1 > v2

        return False

    def _parse_nuget_version_requirement(self, spec: str) -> NuGetVersionRequirement:
        if spec in self._version_cache:
            return self._version_cache[spec]

        req = NuGetVersionRequirement(raw=spec)

        patterns = {
            r"^\[(\d+)\.(\d+)\.(\d+)\]$": lambda m: {
                "operator": "=",
                "major": int(m[1]),
                "minor": int(m[2]),
                "patch": int(m[3]),
            },
            r"^\[(\d+)\.(\d+)\.(\d+),\)$": lambda m: {
                "operator": ">=",
                "major": int(m[1]),
                "minor": int(m[2]),
                "patch": int(m[3]),
            },
            r"^(\d+)\.(\d+)\.\*$": lambda m: {
                "operator": "~",
                "major": int(m[1]),
                "minor": int(m[2]),
                "is_floating": True,
            },
            r"^(\d+)\.\*$": lambda m: {
                "operator": "~",
                "major": int(m[1]),
                "is_floating": True,
            },
        }

        for pattern, handler in patterns.items():
            match = re.match(pattern, spec.strip())
            if match:
                for key, value in handler(match).items():
                    setattr(req, key, value)
                break

        self._version_cache[spec] = req
        return req

    async def check_compatibility(
        self, package_name: str, version: str, system_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        package_name = normalize_package_name(package_name)

        pkg_data = await self.get_package_version(package_name, version)
        if not pkg_data:
            return {
                "compatible": False,
                "errors": ["Package version not found"],
                "warnings": [],
            }

        errors = []
        warnings = []

        target_frameworks = pkg_data.get("system_requirements", {}).get(
            "target_frameworks", []
        )
        system_frameworks = system_info.get("target_frameworks", [])

        if target_frameworks and system_frameworks:
            compatible_frameworks = self._check_framework_compatibility(
                target_frameworks, system_frameworks
            )
            if not compatible_frameworks:
                errors.append(
                    f"No compatible target frameworks. Package supports: {target_frameworks}, System has: {system_frameworks}"
                )

        min_client = pkg_data.get("system_requirements", {}).get("min_client_version")
        if min_client and "nuget_version" in system_info:
            if not self._check_nuget_version_compatibility(
                system_info["nuget_version"], min_client
            ):
                errors.append(f"Requires NuGet client version {min_client} or higher")

        if pkg_data.get("system_requirements", {}).get("development_dependency"):
            warnings.append("This is a development dependency - not needed at runtime")

        return {
            "compatible": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "requirements": pkg_data.get("system_requirements", {}),
            "compatible_frameworks": self._check_framework_compatibility(
                target_frameworks, system_frameworks
            )
            if target_frameworks and system_frameworks
            else [],
        }

    def _check_framework_compatibility(
        self, package_frameworks: List[str], system_frameworks: List[str]
    ) -> List[str]:
        compatible = []

        for sys_fw in system_frameworks:
            for pkg_fw in package_frameworks:
                if self._is_framework_compatible(pkg_fw, sys_fw):
                    compatible.append(pkg_fw)

        return list(set(compatible))

    def _is_framework_compatible(
        self, package_framework: str, system_framework: str
    ) -> bool:
        if package_framework == system_framework:
            return True

        if "netstandard" in package_framework:
            if (
                "net4" in system_framework
                and self._extract_framework_version(system_framework) >= 461
            ):
                return True
            if any(
                fw in system_framework
                for fw in ["netcore", "net5", "net6", "net7", "net8"]
            ):
                return True

        if package_framework.startswith("net") and system_framework.startswith("net"):
            pkg_version = self._extract_framework_version(package_framework)
            sys_version = self._extract_framework_version(system_framework)

            if pkg_version and sys_version:
                return sys_version >= pkg_version

        return False

    def _extract_framework_version(self, framework: str) -> Optional[float]:
        match = re.search(r"(\d+)\.?(\d*)", framework)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2)) if match.group(2) else 0
            return float(f"{major}.{minor}")
        return None

    def _check_nuget_version_compatibility(
        self, system_version: str, required_version: str
    ) -> bool:
        sys_v = parse_version(system_version)
        req_v = parse_version(required_version)

        if sys_v and req_v:
            return sys_v >= req_v

        return True


async def example_usage():
    async with NuGetClient() as client:
        results = await client.search_packages("Newtonsoft.Json", limit=5)

        info = await client.get_package_info_async(
            "Newtonsoft.Json", include_versions=True
        )

        version_info = await client.get_package_version("Newtonsoft.Json", "13.0.3")

        compat = await client.check_compatibility(
            "Newtonsoft.Json",
            "13.0.3",
            {
                "target_frameworks": ["net6.0", "netstandard2.0"],
                "nuget_version": "6.0.0",
            },
        )

        print(f"Package: {info['name']}")
        print(f"Latest version: {info['version']}")
        print(f"Compatible: {compat['compatible']}")


if __name__ == "__main__":
    asyncio.run(example_usage())
