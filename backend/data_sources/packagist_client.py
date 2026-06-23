# packagist_client.py
import asyncio
from typing import Dict, List, Optional, Set, Tuple, Any, Union
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
    PACKAGIST_URL,
    PACKAGIST_API_URL,
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
    REQUIRE = "require"
    REQUIRE_DEV = "require-dev"
    CONFLICT = "conflict"
    REPLACE = "replace"
    PROVIDE = "provide"
    SUGGEST = "suggest"


@dataclass
class ComposerVersionRequirement:
    raw: str
    operator: Optional[str] = None
    major: Optional[int] = None
    minor: Optional[int] = None
    patch: Optional[int] = None


class PackagistClient(BaseDataSourceClient):
    def __init__(
        self,
        api_url: str = None,
        cache_ttl: int = None,
        max_retries: int = None,
        rate_limit_delay: float = None,
        timeout: int = None,
    ):
        packagist_config = get_ecosystem_config("packagist")

        api_url = (
            api_url or packagist_config.get("api_url", PACKAGIST_API_URL)
        ).rstrip("/")
        super().__init__(
            ecosystem="packagist",
            base_url=api_url,
            cache_ttl=cache_ttl or packagist_config.get("cache_ttl", CACHE_TTL),
            user_agent=USER_AGENTS.get("packagist", USER_AGENTS["default"]),
            rate_limit=packagist_config.get(
                "rate_limit", RATE_LIMITS.get("packagist", 600)
            ),
            timeout=timeout or REQUEST_TIMEOUT,
            max_retries=MAX_RETRIES,
        )

        self.base_url = PACKAGIST_URL
        self.search_url = f"{PACKAGIST_URL}/search.json"
        self._version_cache: Dict[str, ComposerVersionRequirement] = {}

    def package_exists(self, package_name: str) -> bool:
        package_name = normalize_package_name(package_name)
        try:
            import requests

            response = requests.head(
                f"{self.base_url}/packages/{package_name}.json", timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False

    async def search_packages(
        self,
        query: str,
        limit: int = 20,
        package_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Dict]:
        query = normalize_package_name(query)

        params = {"q": query, "per_page": min(limit, 100)}

        if package_type:
            params["type"] = package_type

        if tags:
            params["tags"] = ",".join(tags)

        data = await self._get(self.search_url, params=params)
        if not data or "results" not in data:
            return []

        results = []
        for package in data["results"]:
            result = {
                "name": package.get("name"),
                "description": package.get("description"),
                "url": package.get("url"),
                "repository": package.get("repository"),
                "downloads": package.get("downloads"),
                "favers": package.get("favers"),
                "abandoned": package.get("abandoned", False),
                "replacement": package.get("replacement"),
            }
            results.append(result)

        return results

    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(
        self, package_name: str, include_versions: bool = True
    ) -> Optional[Dict]:
        package_name = normalize_package_name(package_name)

        url = f"{self.base_url}/packages/{package_name}.json"
        data = await self._get(url)
        if not data or "package" not in data:
            return None

        package_data = data["package"]

        versions_info = []
        latest_version = None
        latest_data = None

        for version, version_data in package_data.get("versions", {}).items():
            if self._is_valid_version(version):
                version_info = self._process_version_data(version_data)
                if version_info:
                    versions_info.append(version_info)
                    if not latest_version or self._is_newer_version(
                        version, latest_version
                    ):
                        latest_version = version
                        latest_data = version_data

        versions_info.sort(
            key=lambda x: parse_version(x["version"]) or parse_version("0.0.0"),
            reverse=True,
        )

        downloads = await self._get_download_stats(package_name)

        info = {
            "name": package_data.get("name"),
            "description": package_data.get("description"),
            "type": package_data.get("type", "library"),
            "repository": package_data.get("repository"),
            "homepage": package_data.get("homepage"),
            "language": package_data.get("language"),
            "abandoned": package_data.get("abandoned", False),
            "replacement": package_data.get("replacement"),
            "downloads": downloads,
            "dependents": package_data.get("dependents", 0),
            "suggesters": package_data.get("suggesters", 0),
            "github_stars": package_data.get("github_stars"),
            "github_watchers": package_data.get("github_watchers"),
            "github_forks": package_data.get("github_forks"),
            "github_open_issues": package_data.get("github_open_issues"),
            "versions": versions_info if include_versions else [],
        }

        if latest_data:
            info.update(
                {
                    "version": latest_version,
                    "time": latest_data.get("time"),
                    "authors": latest_data.get("authors", []),
                    "keywords": latest_data.get("keywords", []),
                    "license": latest_data.get("license", []),
                    "support": latest_data.get("support", {}),
                    "funding": latest_data.get("funding", []),
                    "dependencies": self._extract_dependencies(latest_data),
                    "system_requirements": self._extract_system_requirements(
                        latest_data
                    ),
                    "autoload": latest_data.get("autoload", {}),
                    "bin": latest_data.get("bin", []),
                    "scripts": latest_data.get("scripts", {}),
                    "extra": latest_data.get("extra", {}),
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

        info = await self.get_package_info_async(package_name, include_versions=True)
        if not info or not info.get("versions"):
            return None

        for v in info["versions"]:
            if v.get("version") == version:
                return v

        return None

    async def get_versions(
        self,
        package_name: str,
        include_dev: bool = True,
        include_abandoned: bool = False,
    ) -> List[Dict]:
        package_name = normalize_package_name(package_name)

        info = await self.get_package_info_async(package_name, include_versions=True)
        if not info or not info.get("versions"):
            return []

        versions = []
        for v in info["versions"]:
            if not include_dev and self._is_dev_version(v.get("version", "")):
                continue

            versions.append(v)

        return versions

    async def get_dependencies(
        self, package_name: str, version: Optional[str] = None, include_dev: bool = True
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

        if not include_dev and "require-dev" in dependencies:
            del dependencies["require-dev"]

        return dependencies

    async def _get_download_stats(self, package_name: str) -> Dict[str, int]:
        package_name = normalize_package_name(package_name)
        try:
            url = f"{self.base_url}/downloads/{package_name}.json"
            data = await self._get(url)
            if data and "package" in data:
                return data["package"]
        except Exception:
            pass
        return {"daily": 0, "monthly": 0, "total": 0}

    def _process_version_data(self, version_data: Dict) -> Optional[Dict]:
        version = version_data.get("version")
        if not version or not self._is_valid_version(version):
            return None

        return {
            "version": version,
            "version_normalized": version_data.get("version_normalized"),
            "stability": version_data.get("stability"),
            "time": version_data.get("time"),
            "description": version_data.get("description"),
            "keywords": version_data.get("keywords", []),
            "license": version_data.get("license", []),
            "authors": version_data.get("authors", []),
            "support": version_data.get("support", {}),
            "funding": version_data.get("funding", []),
            "dependencies": self._extract_dependencies(version_data),
            "system_requirements": self._extract_system_requirements(version_data),
            "autoload": version_data.get("autoload", {}),
            "bin": version_data.get("bin", []),
            "notification_url": version_data.get("notification-url"),
            "source": version_data.get("source", {}),
            "dist": version_data.get("dist", {}),
        }

    def _extract_dependencies(self, version_data: Dict) -> Dict[str, Dict]:
        dependencies = {}

        dep_types = [
            "require",
            "require-dev",
            "conflict",
            "replace",
            "provide",
            "suggest",
        ]

        for dep_type in dep_types:
            if dep_type in version_data:
                dependencies[dep_type] = version_data[dep_type]

        return dependencies

    def _extract_system_requirements(self, version_data: Dict) -> Dict[str, Any]:
        requirements = {"php": None, "extensions": [], "platform": {}, "composer": None}

        require = version_data.get("require", {})
        if "php" in require:
            requirements["php"] = require["php"]

        for req_name, req_version in require.items():
            if req_name.startswith("ext-"):
                ext_name = req_name[4:]
                requirements["extensions"].append(
                    {"name": ext_name, "version": req_version}
                )

        platform_requires = {}
        for req_name, req_version in require.items():
            if req_name in [
                "lib-openssl",
                "lib-pcre",
                "lib-iconv",
                "lib-icu",
                "lib-libxml",
            ]:
                platform_requires[req_name] = req_version

        requirements["platform"] = platform_requires

        if "composer" in require:
            requirements["composer"] = require["composer"]

        return requirements

    def _is_valid_version(self, version: str) -> bool:
        if not version:
            return False

        if version.startswith("dev-"):
            return False

        return parse_version(version) is not None

    def _is_dev_version(self, version: str) -> bool:
        return version.startswith("dev-") or "-dev" in version

    def _is_newer_version(self, version1: str, version2: str) -> bool:
        v1 = parse_version(version1)
        v2 = parse_version(version2)

        if v1 and v2:
            return v1 > v2

        return False

    def _parse_composer_version_requirement(
        self, spec: str
    ) -> ComposerVersionRequirement:
        if spec in self._version_cache:
            return self._version_cache[spec]

        req = ComposerVersionRequirement(raw=spec)

        patterns = {
            r"^\^(\d+)\.(\d+)\.(\d+)": lambda m: {
                "operator": "^",
                "major": int(m[1]),
                "minor": int(m[2]),
                "patch": int(m[3]),
            },
            r"^~(\d+)\.(\d+)\.(\d+)": lambda m: {
                "operator": "~",
                "major": int(m[1]),
                "minor": int(m[2]),
                "patch": int(m[3]),
            },
            r"^>=(\d+)\.(\d+)\.(\d+)": lambda m: {
                "operator": ">=",
                "major": int(m[1]),
                "minor": int(m[2]),
                "patch": int(m[3]),
            },
            r"^(\d+)\.(\d+)\.(\d+)$": lambda m: {
                "major": int(m[1]),
                "minor": int(m[2]),
                "patch": int(m[3]),
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

        php_requirement = pkg_data.get("system_requirements", {}).get("php")
        if php_requirement and "php_version" in system_info:
            if not self._check_php_compatibility(
                system_info["php_version"], php_requirement
            ):
                errors.append(
                    f"Requires PHP {php_requirement}, but system has {system_info['php_version']}"
                )

        required_extensions = pkg_data.get("system_requirements", {}).get(
            "extensions", []
        )
        system_extensions = system_info.get("php_extensions", [])

        for ext in required_extensions:
            ext_name = ext["name"]
            if ext_name not in system_extensions:
                errors.append(f"Required PHP extension missing: {ext_name}")

        composer_requirement = pkg_data.get("system_requirements", {}).get("composer")
        if composer_requirement and "composer_version" in system_info:
            if not self._check_composer_compatibility(
                system_info["composer_version"], composer_requirement
            ):
                warnings.append(f"Recommends Composer {composer_requirement}")

        if pkg_data.get("abandoned", False):
            replacement = pkg_data.get("replacement")
            if replacement:
                warnings.append(
                    f"Package is abandoned. Consider using {replacement} instead."
                )
            else:
                warnings.append(
                    "Package is abandoned and has no recommended replacement."
                )

        return {
            "compatible": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "requirements": pkg_data.get("system_requirements", {}),
        }

    def _check_php_compatibility(self, system_version: str, required: str) -> bool:
        req = self._parse_composer_version_requirement(required)
        system_v = parse_version(system_version)

        if not system_v or not req.major:
            return True

        if req.operator == "^":
            min_v = parse_version(f"{req.major}.{req.minor}.{req.patch}")
            max_v = parse_version(f"{req.major + 1}.0.0")
            return min_v <= system_v < max_v
        elif req.operator == "~":
            min_v = parse_version(f"{req.major}.{req.minor}.{req.patch}")
            max_v = parse_version(f"{req.major}.{req.minor + 1}.0")
            return min_v <= system_v < max_v
        elif req.operator == ">=":
            min_v = parse_version(f"{req.major}.{req.minor}.{req.patch}")
            return system_v >= min_v
        else:
            exact_v = parse_version(f"{req.major}.{req.minor}.{req.patch}")
            return system_v == exact_v

    def _check_composer_compatibility(self, system_version: str, required: str) -> bool:
        return self._check_php_compatibility(system_version, required)


async def example_usage():
    async with PackagistClient() as client:
        results = await client.search_packages("symfony", limit=5)

        info = await client.get_package_info_async(
            "symfony/console", include_versions=True
        )

        version_info = await client.get_package_version("symfony/console", "v6.0.0")

        compat = await client.check_compatibility(
            "symfony/console",
            "v6.0.0",
            {
                "php_version": "8.1.0",
                "php_extensions": ["json", "mbstring", "ctype"],
                "composer_version": "2.4.0",
            },
        )

        print(f"Package: {info['name']}")
        print(f"Latest version: {info['version']}")
        print(f"Compatible: {compat['compatible']}")


if __name__ == "__main__":
    asyncio.run(example_usage())
