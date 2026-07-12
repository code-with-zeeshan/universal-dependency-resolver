"""Module docstring."""

# rubygems_client.py
import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.core.cache import cached
from backend.core.utils import (
    normalize_package_name,
    parse_version,
    parse_version_key,
    run_async,
)
from backend.settings import (
    CACHE_TTL,
    get_ecosystem_config,
)

from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """DependencyType."""

    RUNTIME = "runtime"
    DEVELOPMENT = "development"


@dataclass
class RubyVersionRequirement:
    """RubyVersionRequirement."""

    """RubyVersionRequirement."""
    raw: str
    operator: str | None = None
    major: int | None = None
    minor: int | None = None
    patch: int | None = None


class RubyGemsClient(BaseDataSourceClient):
    """RubyGemsClient."""

    def __init__(
        self,
        api_url: str | None = None,
        cache_ttl: int | None = None,
        max_retries: int | None = None,
        rate_limit_delay: float | None = None,
        timeout: int | None = None,
    ):
        """Initialize."""
        rubygems_config = get_ecosystem_config("rubygems")

        api_url = (api_url or rubygems_config.get("api_url", "https://rubygems.org/api/v1")).rstrip(
            "/"
        )
        super().__init__(
            ecosystem="rubygems",
            base_url=api_url,
            cache_ttl=cache_ttl or rubygems_config.get("cache_ttl", CACHE_TTL),
        )

        self._version_cache: dict[str, RubyVersionRequirement] = {}

    async def package_exists(self, package_name: str) -> bool:
        """async package exists."""
        """async package exists."""
        package_name = normalize_package_name(package_name)
        try:
            session = self._get_session()
            response = await session.head(f"{self.base_url}/gems/{package_name}.json")
            return response.status == 200
        except Exception:
            return False

    async def search_packages(self, query: str, limit: int = 20) -> list[dict]:
        """async search packages."""
        """async search packages."""
        query = normalize_package_name(query)

        url = f"{self.base_url}/search.json"
        params = {"query": query}

        try:
            data = await self._get(url, params=params)
        except Exception:
            return []
        if not data:
            return []

        results = []
        for gem in data[:limit]:
            result = {
                "name": gem.get("name"),
                "version": gem.get("version"),
                "description": gem.get("info"),
                "authors": gem.get("authors"),
                "downloads": gem.get("downloads"),
                "version_downloads": gem.get("version_downloads"),
                "platform": gem.get("platform"),
                "licenses": gem.get("licenses", []),
                "homepage_uri": gem.get("homepage_uri"),
                "documentation_uri": gem.get("documentation_uri"),
                "source_code_uri": gem.get("source_code_uri"),
                "gem_uri": gem.get("gem_uri"),
                "project_uri": gem.get("project_uri"),
            }
            results.append(result)

        return results

    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(
        self, package_name: str, include_versions: bool = True
    ) -> dict | None:
        """get package info async."""
        package_name = normalize_package_name(package_name)

        url = f"{self.base_url}/gems/{package_name}.json"
        data = await self._get(url)
        if not data:
            return None

        versions_info = []
        if include_versions:
            versions_data = await self._get_all_versions(package_name)
            versions_info = self._process_versions(versions_data)

        reverse_deps = await self._get_reverse_dependencies(package_name)

        downloads = await self._get_download_stats(package_name)

        info = {
            "name": data.get("name"),
            "version": data.get("version"),
            "platform": data.get("platform"),
            "authors": data.get("authors"),
            "info": data.get("info"),
            "licenses": data.get("licenses", []),
            "metadata": data.get("metadata", {}),
            "sha": data.get("sha"),
            "project_uri": data.get("project_uri"),
            "gem_uri": data.get("gem_uri"),
            "homepage_uri": data.get("homepage_uri"),
            "wiki_uri": data.get("wiki_uri"),
            "documentation_uri": data.get("documentation_uri"),
            "mailing_list_uri": data.get("mailing_list_uri"),
            "source_code_uri": data.get("source_code_uri"),
            "bug_tracker_uri": data.get("bug_tracker_uri"),
            "changelog_uri": data.get("changelog_uri"),
            "funding_uri": data.get("funding_uri"),
            "downloads": downloads,
            "version_downloads": data.get("version_downloads"),
            "versions": versions_info,
            "reverse_dependencies": reverse_deps,
            "dependencies": await self._get_dependencies(
                package_name, str(data.get("version")) if data.get("version") else ""
            ),
            "system_requirements": self._extract_system_requirements(data),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

        return info

    def get_package_info(self, package_name: str) -> dict:
        """get package info."""
        """get package info."""
        package_name = normalize_package_name(package_name)
        return run_async(self.get_package_info_async(package_name))

    async def get_artifact_hash(self, package_name: str, version: str) -> dict | None:
        """Get RubyGems artifact integrity hash (SHA256 from version sha)."""
        versions_data = await self._get_all_versions(package_name)
        if not versions_data:
            return None
        for v in versions_data:
            if v.get("number") == version:
                sha = v.get("sha")
                if sha:
                    return {"algorithm": "sha256", "hash": sha}
                break
        return None

    async def get_package_version(self, package_name: str, version: str) -> dict | None:
        """async get package version."""
        """async get package version."""
        package_name = normalize_package_name(package_name)

        versions_data = await self._get_all_versions(package_name)
        if not versions_data:
            return None

        for v in versions_data:
            if v.get("number") == version:
                return {
                    "name": package_name,
                    "version": v.get("number"),
                    "platform": v.get("platform"),
                    "prerelease": v.get("prerelease", False),
                    "licenses": v.get("licenses", []),
                    "requirements": v.get("requirements", []),
                    "sha": v.get("sha"),
                    "created_at": v.get("created_at"),
                    "description": v.get("description"),
                    "downloads_count": v.get("downloads_count"),
                    "metadata": v.get("metadata", {}),
                    "dependencies": await self._parse_dependencies(v.get("dependencies", {})),
                    "ruby_version": v.get("ruby_version"),
                    "required_ruby_version": v.get("required_ruby_version"),
                    "required_rubygems_version": v.get("required_rubygems_version"),
                }

        return None

    async def get_versions(
        self,
        package_name: str,
        include_prereleases: bool = True,
        include_yanked: bool = False,
    ) -> list[dict]:
        """get versions."""
        package_name = normalize_package_name(package_name)

        versions_data = await self._get_all_versions(package_name)
        if not versions_data:
            return []

        versions = []
        for v in versions_data:
            if not include_prereleases and v.get("prerelease", False):
                continue

            if not include_yanked and v.get("yanked", False):
                continue

            versions.append(
                {
                    "version": v.get("number"),
                    "platform": v.get("platform"),
                    "prerelease": v.get("prerelease", False),
                    "yanked": v.get("yanked", False),
                    "created_at": v.get("created_at"),
                    "sha": v.get("sha"),
                    "metadata": v.get("metadata", {}),
                    "downloads_count": v.get("downloads_count", 0),
                }
            )

        versions.sort(
            key=lambda x: parse_version_key(x["version"]),
            reverse=True,
        )

        return versions

    async def get_dependencies(
        self,
        package_name: str,
        version: str | None = None,
        include_development: bool = True,
    ) -> dict[str, Any]:
        """get dependencies."""
        package_name = normalize_package_name(package_name)

        if version:
            pkg_data = await self.get_package_version(package_name, version)
        else:
            pkg_data = await self.get_package_info_async(package_name, include_versions=False)

        if not pkg_data:
            return {}

        return pkg_data.get("dependencies", {})

    async def _get_all_versions(self, package_name: str) -> list[dict]:
        package_name = normalize_package_name(package_name)
        url = f"{self.base_url}/versions/{package_name}.json"
        data: Any = await self._get(url)
        if data is None:
            return []
        if isinstance(data, list):
            return data
        return [data]

    async def _get_reverse_dependencies(self, package_name: str) -> list[str]:
        package_name = normalize_package_name(package_name)
        url = f"{self.base_url}/gems/{package_name}/reverse_dependencies.json"
        data = await self._get(url)
        return data if isinstance(data, list) else []

    async def _get_download_stats(self, package_name: str) -> dict[str, int]:
        package_name = normalize_package_name(package_name)
        try:
            url = f"{self.base_url}/downloads/{package_name}.json"
            data = await self._get(url)
            if data:
                return {
                    "total": data.get("total_downloads", 0),
                    "version": data.get("version_downloads", 0),
                }
        except Exception:
            pass
        return {"total": 0, "version": 0}

    async def _get_dependencies(self, package_name: str, version: str) -> dict:
        package_name = normalize_package_name(package_name)
        versions_data = await self._get_all_versions(package_name)

        for v in versions_data:
            if v.get("number") == version:
                return await self._parse_dependencies(v.get("dependencies", {}))

        return {}

    async def _parse_dependencies(self, dependencies: dict) -> dict:
        parsed: dict[str, dict] = {"runtime": {}, "development": {}}

        if "dependencies" in dependencies:
            deps = dependencies["dependencies"]
            for dep in deps:
                name = dep.get("name")
                requirements = dep.get("requirements", "")
                dep_type = "development" if dep.get("type") == "development" else "runtime"

                if name:
                    parsed[dep_type][name] = requirements

        return parsed

    def _process_versions(self, versions_data: list[dict]) -> list[dict]:
        versions = []

        for v in versions_data:
            version_str = v.get("number")
            if not version_str or parse_version(version_str) is None:
                continue

            versions.append(
                {
                    "version": version_str,
                    "platform": v.get("platform"),
                    "prerelease": v.get("prerelease", False),
                    "yanked": v.get("yanked", False),
                    "created_at": v.get("created_at"),
                    "sha": v.get("sha"),
                    "downloads_count": v.get("downloads_count", 0),
                }
            )

        versions.sort(
            key=lambda x: parse_version_key(x["version"]),
            reverse=True,
        )

        return versions

    def _extract_system_requirements(self, data: dict) -> dict[str, Any]:
        requirements = {
            "ruby": None,
            "rubygems": None,
            "platform": data.get("platform"),
            "licenses": data.get("licenses", []),
        }

        metadata = data.get("metadata", {})
        if "required_ruby_version" in metadata:
            requirements["ruby"] = metadata["required_ruby_version"]
        if "required_rubygems_version" in metadata:
            requirements["rubygems"] = metadata["required_rubygems_version"]

        return requirements

    def _parse_ruby_version_requirement(self, spec: str) -> RubyVersionRequirement:
        if spec in self._version_cache:
            return self._version_cache[spec]

        req = RubyVersionRequirement(raw=spec)

        patterns: dict[str, Any] = {
            r"^~>\s*(\d+)\.(\d+)\.(\d+)": lambda m: {
                "operator": "~>",
                "major": int(m[1]),
                "minor": int(m[2]),
                "patch": int(m[3]),
            },
            r"^>=\s*(\d+)\.(\d+)\.(\d+)": lambda m: {
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
        self, package_name: str, version: str, system_info: dict[str, Any]
    ) -> dict[str, Any]:
        """check compatibility."""
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

        required_ruby = pkg_data.get("required_ruby_version")
        if (
            required_ruby
            and "ruby_version" in system_info
            and not self._check_ruby_compatibility(system_info["ruby_version"], required_ruby)
        ):
            errors.append(
                f"Requires Ruby {required_ruby}, but system has {system_info['ruby_version']}"
            )

        required_rubygems = pkg_data.get("required_rubygems_version")
        if (
            required_rubygems
            and "rubygems_version" in system_info
            and not self._check_rubygems_compatibility(
                system_info["rubygems_version"], required_rubygems
            )
        ):
            warnings.append(
                f"Recommends RubyGems {required_rubygems}, but system has {system_info['rubygems_version']}"
            )

        platform = pkg_data.get("platform")
        if (
            platform
            and platform != "ruby"
            and "platform" in system_info
            and not self._check_platform_compatibility(system_info["platform"], platform)
        ):
            errors.append(f"Not compatible with platform: {system_info['platform']}")

        return {
            "compatible": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "requirements": pkg_data.get("system_requirements", {}),
        }

    def _check_ruby_compatibility(self, system_version: str, required: str) -> bool:
        req = self._parse_ruby_version_requirement(required)
        system_v = parse_version(system_version)

        if not system_v or not req.major:
            return True

        minor = req.minor if req.minor is not None else 0
        patch = req.patch if req.patch is not None else 0
        major = req.major

        if req.operator == "~>":
            min_v = parse_version(f"{major}.{minor}.{patch}")
            if req.patch is not None:
                max_v = parse_version(f"{major}.{minor + 1}.0")
            else:
                max_v = parse_version(f"{major + 1}.0.0")

            if min_v is not None and max_v is not None:
                return min_v <= system_v < max_v
            return True
        if req.operator == ">=":
            min_v = parse_version(f"{major}.{minor}.{patch}")
            if min_v is not None:
                return system_v >= min_v
            return True
        exact_v = parse_version(f"{major}.{minor}.{patch}")
        if exact_v is not None:
            return system_v == exact_v
        return True

    def _check_rubygems_compatibility(self, system_version: str, required: str) -> bool:
        return self._check_ruby_compatibility(system_version, required)

    def _check_platform_compatibility(self, system_platform: str, required_platform: str) -> bool:
        if required_platform == "ruby":
            return True

        platform_mappings = {
            "x86_64-linux": ["linux", "x86_64"],
            "x86_64-darwin": ["darwin", "macos", "x86_64"],
            "arm64-darwin": ["darwin", "macos", "arm64"],
            "x64-mingw32": ["windows", "x64"],
            "x86-mingw32": ["windows", "x86"],
        }

        if required_platform in platform_mappings:
            required_parts = platform_mappings[required_platform]
            return any(part in system_platform.lower() for part in required_parts)

        return required_platform.lower() in system_platform.lower()


async def example_usage():
    """async example usage."""
    async with RubyGemsClient() as client:
        await client.search_packages("rails", limit=5)

        info = await client.get_package_info_async("rails", include_versions=True)

        await client.get_package_version("rails", "7.0.0")

        compat = await client.check_compatibility(
            "rails",
            "7.0.0",
            {
                "ruby_version": "3.0.0",
                "rubygems_version": "3.2.0",
                "platform": "x86_64-linux",
            },
        )

        print(f"Gem: {info['name']}")
        print(f"Latest version: {info['version']}")
        print(f"Compatible: {compat['compatible']}")


if __name__ == "__main__":
    asyncio.run(example_usage())
