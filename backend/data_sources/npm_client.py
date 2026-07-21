"""Module docstring."""

# npm_client.py
import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import quote

from ..core.utils import normalize_package_name, parse_version, parse_version_key
from ..settings import (
    CACHE_TTL,
    NPM_CONCURRENCY,
    get_ecosystem_config,
)
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """DependencyType."""

    DEPENDENCIES = "dependencies"
    DEV_DEPENDENCIES = "devDependencies"
    PEER_DEPENDENCIES = "peerDependencies"
    OPTIONAL_DEPENDENCIES = "optionalDependencies"
    BUNDLED_DEPENDENCIES = "bundledDependencies"


@dataclass
class VersionRequirement:
    """VersionRequirement."""

    """VersionRequirement."""
    raw: str
    operator: str | None = None
    major: int | None = None
    minor: int | None = None
    patch: int | None = None
    prerelease: str | None = None


# Concurrency limit: shared across all NPM client instances.
# Controls how many simultaneous requests are made to the npm registry.
# Configurable via NPM_CONCURRENCY env var (default: 10).
# Rate limiting (429 handling, RPM tracking) is handled by BaseDataSourceClient._throttle().
_NPM_SEMAPHORE = asyncio.Semaphore(NPM_CONCURRENCY)


class NPMClient(BaseDataSourceClient):
    """NPMClient."""

    def __init__(
        self,
        registry_url: str | None = None,
        cache_ttl: int | None = None,
        max_retries: int | None = None,
        timeout: int | None = None,
    ):
        """Initialize."""
        npm_config = get_ecosystem_config("npm")
        registry_url = (registry_url or npm_config.get("url", "https://registry.npmjs.org")).rstrip(
            "/"
        )
        self.registry_url = registry_url
        super().__init__(
            ecosystem="npm",
            base_url=registry_url,
            cache_ttl=cache_ttl or npm_config.get("cache_ttl", CACHE_TTL),
        )

        self.search_url = "https://registry.npmjs.org/-/v1/search"
        self.downloads_url = "https://api.npmjs.org/downloads"
        self._semver_cache: dict[str, VersionRequirement] = {}

    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> dict[str, Any] | None:
        async with _NPM_SEMAPHORE:
            return await super()._make_request(method, url, **kwargs)

    async def cached_get(
        self, cache_key: str, url: str, ttl: int | None = None, headers: dict | None = None
    ) -> dict | None:
        """Cached get."""
        async with _NPM_SEMAPHORE:
            return await super().cached_get(cache_key, url, ttl=ttl, headers=headers)

    async def search_packages(
        self,
        query: str,
        limit: int = 20,
        quality: float | None = None,
        popularity: float | None = None,
        maintenance: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search packages."""
        query = normalize_package_name(query)
        params = {"text": query, "size": min(limit, 250)}

        data = await self._make_request("GET", self.search_url, params=params)
        if not data:
            return []

        results = []
        for obj in data.get("objects", []):
            package = obj.get("package", {})
            score = obj.get("score", {})

            detail = score.get("detail", {})
            if quality and detail.get("quality", 0) < quality:
                continue
            if popularity and detail.get("popularity", 0) < popularity:
                continue
            if maintenance and detail.get("maintenance", 0) < maintenance:
                continue

            result = {
                "name": package.get("name"),
                "version": package.get("version"),
                "description": package.get("description"),
                "keywords": package.get("keywords", []),
                "date": package.get("date"),
                "publisher": self._extract_publisher(package.get("publisher")),
                "maintainers": package.get("maintainers", []),
                "repository": self._extract_repository(package.get("links", {})),
                "npm_url": package.get("links", {}).get("npm"),
                "homepage": package.get("links", {}).get("homepage"),
                "bugs": package.get("links", {}).get("bugs"),
                "license": package.get("license"),
                "scope": package.get("scope"),
                "score": {
                    "final": score.get("final", 0),
                    "quality": detail.get("quality", 0),
                    "popularity": detail.get("popularity", 0),
                    "maintenance": detail.get("maintenance", 0),
                },
                "searchScore": obj.get("searchScore", 0),
            }

            results.append(result)

        return results

    async def get_package_info(
        self,
        package_name: str,
        include_readme: bool = True,
        include_versions: bool = True,
        include_extended: bool = True,
    ) -> dict[str, Any] | None:
        """Get package info."""
        package_name = normalize_package_name(package_name)
        encoded_name = quote(package_name, safe="@/")
        url = f"{self.registry_url}/{encoded_name}"

        # Use compact install metadata format during resolution (~10x smaller payload)
        # Full format is only needed for rich analysis (descriptions, readmes, etc.)
        extra_headers = {}
        accept_header = "application/vnd.npm.install-v1+json" if not include_extended else None
        if accept_header:
            extra_headers = {"Accept": accept_header}
        cache_key = f"packument:{package_name}:{'' if include_extended else 'compact'}"
        data = await self.cached_get(cache_key, url, headers=extra_headers)
        if not data:
            return None

        latest_version = data.get("dist-tags", {}).get("latest")
        if not latest_version:
            return None

        latest_data = data.get("versions", {}).get(latest_version, {})

        downloads = await self._get_download_stats(package_name) if include_extended else {}

        types_info = (
            await self._check_typescript_support(package_name, latest_data)
            if include_extended
            else {"has_types": False, "types_package": None, "included": False}
        )

        vulnerabilities = []

        versions_info = []
        if include_versions:
            versions_info = self._process_versions(data.get("versions", {}), data.get("time", {}))

        categorized_deps = self._categorize_dependencies(latest_data)
        # Include peerDependencies in the dependency flow so they participate
        # in resolution. The aggregator marks them with peer=True so the
        # orchestrator can decide policy (hard constraints vs advisory).
        info = {
            "name": data.get("name"),
            "version": latest_version,
            "description": data.get("description"),
            "keywords": data.get("keywords", []),
            "homepage": data.get("homepage"),
            "bugs": data.get("bugs"),
            "license": data.get("license"),
            "author": self._format_person(data.get("author")),  # type: ignore[arg-type]
            "maintainers": [self._format_person(m) for m in data.get("maintainers", [])],
            "repository": self._extract_repository_info(data.get("repository")),  # type: ignore[arg-type]
            "readme": data.get("readme") if include_readme else None,
            "readmeFilename": data.get("readmeFilename"),
            "dist_tags": data.get("dist-tags", {}),
            "versions": versions_info,
            "time": {
                "created": data.get("time", {}).get("created"),
                "modified": data.get("time", {}).get("modified"),
            },
            "users": data.get("users", {}),
            "downloads": downloads,
            "typescript": types_info,
            "vulnerabilities": vulnerabilities,
            "dependencies": categorized_deps,
            "peer_dependencies": categorized_deps.get("peerDependencies", {}),
            "latest_version_info": {
                "dependencies": categorized_deps,
                "engines": latest_data.get("engines", {}),
                "bin": latest_data.get("bin"),
                "scripts": latest_data.get("scripts", {}),
                "dist": latest_data.get("dist", {}),
                "deprecated": latest_data.get("deprecated"),
                "funding": latest_data.get("funding"),
                "exports": latest_data.get("exports"),
                "type": latest_data.get("type"),
                "main": latest_data.get("main"),
                "module": latest_data.get("module"),
                "browser": latest_data.get("browser"),
                "files": latest_data.get("files", []),
                "directories": latest_data.get("directories", {}),
                "cpu": latest_data.get("cpu", []),
                "os": latest_data.get("os", []),
                "workspaces": latest_data.get("workspaces"),
                "publishConfig": latest_data.get("publishConfig", {}),
            },
            "system_requirements": self._extract_detailed_requirements(latest_data),
        }

        return info

    async def get_artifact_hash(self, package_name: str, version: str) -> dict | None:
        """Get npm package artifact integrity hash (sha512 from dist.integrity)."""
        encoded_name = quote(package_name, safe="@/")
        url = f"{self.registry_url}/{encoded_name}/{version}"
        data = await self._make_request("GET", url)
        if not data:
            return None
        dist = data.get("dist", {})
        integrity = dist.get("integrity")
        if integrity:
            return {"algorithm": "sha512", "hash": integrity.replace("sha512-", "")}
        shasum = dist.get("shasum")
        if shasum:
            return {"algorithm": "sha1", "hash": shasum}
        return None

    async def get_package_version(self, package_name: str, version: str) -> dict[str, Any] | None:
        """Async get package version."""
        """async get package version."""
        package_name = normalize_package_name(package_name)
        encoded_name = quote(package_name, safe="@/")
        url = f"{self.registry_url}/{encoded_name}/{version}"

        data = await self._make_request("GET", url)
        if not data:
            return None

        return {
            "name": data.get("name"),
            "version": data.get("version"),
            "description": data.get("description"),
            "main": data.get("main"),
            "module": data.get("module"),
            "browser": data.get("browser"),
            "type": data.get("type"),
            "dependencies": self._categorize_dependencies(data),
            "engines": data.get("engines", {}),
            "dist": data.get("dist", {}),
            "deprecated": data.get("deprecated"),
            "cpu": data.get("cpu", []),
            "os": data.get("os", []),
            "system_requirements": self._extract_detailed_requirements(data),
        }

    async def get_versions(
        self,
        package_name: str,
        include_prereleases: bool = True,
        include_deprecated: bool = False,
    ) -> list[dict[str, Any]]:
        """Get versions."""
        package_name = normalize_package_name(package_name)
        info = await self.get_package_info(
            package_name, include_readme=False, include_versions=True
        )
        if not info:
            return []

        versions: list[Any] = []
        for version_info in info.get("versions", []):
            if not include_prereleases and self._is_prerelease(version_info["version"]):
                continue

            if not include_deprecated and version_info.get("deprecated"):
                continue

            versions.append(version_info)

        return versions

    async def resolve_version(self, package_name: str, version_spec: str) -> str | None:
        """Async resolve version."""
        """async resolve version."""
        package_name = normalize_package_name(package_name)
        versions = await self.get_versions(package_name, include_deprecated=False)
        if not versions:
            return None

        requirement = self._parse_version_requirement(version_spec)

        matching_versions = []
        for v in versions:
            if self._version_matches_requirement(v["version"], requirement):
                matching_versions.append(v["version"])

        if not matching_versions:
            return None

        return max(
            matching_versions,
            key=parse_version_key,
        )

    async def get_dependencies(
        self,
        package_name: str,
        version: str | None = None,
        types: list[DependencyType] | None = None,
        include_transitive: bool = False,
        max_depth: int = 3,
    ) -> dict[str, Any]:
        """Get dependencies."""
        package_name = normalize_package_name(package_name)
        if version:
            pkg_data = await self.get_package_version(package_name, version)
        else:
            info = await self.get_package_info(
                package_name, include_readme=False, include_versions=False
            )
            if not info:
                return {}
            pkg_data = info.get("latest_version_info", {})

        if not pkg_data:
            return {}

        deps = pkg_data.get("dependencies", {})

        if types:
            type_names = [t.value for t in types]
            deps = {k: v for k, v in deps.items() if k in type_names}

        result = {"direct": deps, "transitive": {}}

        if include_transitive:
            visited: set[str] = set()
            result["transitive"] = await self._resolve_transitive_dependencies(
                deps.get("dependencies", {}), visited, max_depth
            )

        return result

    async def _resolve_transitive_dependencies(
        self,
        dependencies: dict[str, str],
        visited: set[str],
        max_depth: int,
        current_depth: int = 0,
    ) -> dict[str, dict]:
        if current_depth >= max_depth:
            return {}

        transitive = {}

        for dep_name, version_spec in dependencies.items():
            normalized_dep_name = normalize_package_name(dep_name)
            if normalized_dep_name in visited:
                continue

            visited.add(normalized_dep_name)

            resolved_version = await self.resolve_version(normalized_dep_name, version_spec)
            if not resolved_version:
                continue

            dep_info = await self.get_package_version(normalized_dep_name, resolved_version)
            if not dep_info:
                continue

            dep_deps = dep_info.get("dependencies", {}).get("dependencies", {})

            transitive[dep_name] = {
                "version": resolved_version,
                "dependencies": dep_deps,
            }

            if dep_deps:
                sub_transitive = await self._resolve_transitive_dependencies(
                    dep_deps, visited, max_depth, current_depth + 1
                )
                transitive.update(sub_transitive)

        return transitive

    async def check_compatibility(
        self, package_name: str, version: str, system_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Check compatibility."""
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

        engines = pkg_data.get("engines", {})
        if (
            "node" in engines
            and "node_version" in system_info
            and not self._check_node_compatibility(system_info["node_version"], engines["node"])
        ):
            errors.append(
                f"Requires Node.js {engines['node']}, but system has {system_info['node_version']}"
            )

        if (
            "npm" in engines
            and "npm_version" in system_info
            and not self._check_npm_compatibility(system_info["npm_version"], engines["npm"])
        ):
            warnings.append(
                f"Recommends npm {engines['npm']}, but system has {system_info['npm_version']}"
            )

        supported_os = pkg_data.get("os", [])
        if (
            supported_os
            and "os" in system_info
            and not self._check_os_compatibility(system_info["os"], supported_os)
        ):
            errors.append(f"Not compatible with OS: {system_info['os']}")

        supported_cpu = pkg_data.get("cpu", [])
        if (
            supported_cpu
            and "cpu" in system_info
            and not self._check_cpu_compatibility(system_info["cpu"], supported_cpu)
        ):
            errors.append(f"Not compatible with CPU architecture: {system_info['cpu']}")

        if self._has_native_dependencies(pkg_data) and not system_info.get(
            "has_build_tools", False
        ):
            warnings.append("Package contains native dependencies requiring C++ build tools")

        peer_deps = pkg_data.get("dependencies", {}).get("peerDependencies", {})
        if peer_deps and "installed_packages" in system_info:
            for peer_name, peer_version in peer_deps.items():
                if peer_name not in system_info["installed_packages"]:
                    warnings.append(f"Peer dependency missing: {peer_name}@{peer_version}")
                else:
                    installed_version = system_info["installed_packages"][peer_name]
                    if not self._version_satisfies(installed_version, peer_version):
                        warnings.append(
                            f"Peer dependency version mismatch: {peer_name} requires {peer_version}, but {installed_version} is installed"
                        )

        return {
            "compatible": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "requirements": pkg_data.get("system_requirements", {}),
        }

    async def get_dependency_tree(
        self, package_name: str, version: str | None = None, max_depth: int = 3
    ) -> dict[str, Any]:
        """Get dependency tree."""
        package_name = normalize_package_name(package_name)
        tree = {
            "name": package_name,
            "version": version or "latest",
            "dependencies": {},
        }

        if not version:
            info = await self.get_package_info(
                package_name, include_readme=False, include_versions=False
            )
            if not info:
                return tree
            version = info["version"]
            tree["version"] = version

        visited: set[str] = set()
        tree["dependencies"] = await self._build_dependency_tree(
            package_name, version, visited, max_depth
        )

        return tree

    async def _build_dependency_tree(
        self,
        package_name: str,
        version: str,
        visited: set[str],
        max_depth: int,
        current_depth: int = 0,
    ) -> dict[str, Any]:
        package_name = normalize_package_name(package_name)
        if current_depth >= max_depth:
            return {}

        key = f"{package_name}@{version}"
        if key in visited:
            return {"circular": True}

        visited.add(key)

        pkg_data = await self.get_package_version(package_name, version)
        if not pkg_data:
            return {}

        tree: dict[str, Any] = {}
        deps = pkg_data.get("dependencies", {}).get("dependencies", {})

        for dep_name, version_spec in deps.items():
            normalized_dep_name = normalize_package_name(dep_name)
            resolved_version = await self.resolve_version(normalized_dep_name, version_spec)
            if not resolved_version:
                tree[dep_name] = {"version": version_spec, "resolved": False}
                continue

            tree[dep_name] = {
                "version": resolved_version,
                "resolved": True,
                "dependencies": await self._build_dependency_tree(
                    normalized_dep_name,
                    resolved_version,
                    visited,
                    max_depth,
                    current_depth + 1,
                ),
            }

        return tree

    async def analyze_package(
        self, package_name: str, version: str | None = None
    ) -> dict[str, Any]:
        """Analyze package."""
        package_name = normalize_package_name(package_name)
        info = await self.get_package_info(package_name)
        if not info:
            return {}

        if not version:
            version = info["version"]

        pkg_data = await self.get_package_version(package_name, version)
        if not pkg_data:
            return {}

        analysis = {
            "name": package_name,
            "version": version,
            "metadata": {
                "description": info.get("description"),
                "license": info.get("license"),
                "author": info.get("author"),
                "homepage": info.get("homepage"),
                "repository": info.get("repository"),
            },
            "metrics": {
                "size": pkg_data.get("dist", {}).get("unpackedSize", 0),
                "files_count": pkg_data.get("dist", {}).get("fileCount", 0),
                "has_readme": bool(info.get("readme")),
                "has_license": bool(info.get("license")),
                "has_repository": bool(info.get("repository")),
                "has_homepage": bool(info.get("homepage")),
                "has_types": info.get("typescript", {}).get("has_types", False),
                "last_publish": info.get("time", {}).get("modified"),
                "versions_count": len(info.get("versions", [])),
                "maintainers_count": len(info.get("maintainers", [])),
                "keywords_count": len(info.get("keywords", [])),
                "weekly_downloads": info.get("downloads", {}).get("weekly", 0),
            },
            "dependencies_analysis": {
                "direct_count": len(pkg_data.get("dependencies", {}).get("dependencies", {})),
                "dev_count": len(pkg_data.get("dependencies", {}).get("devDependencies", {})),
                "peer_count": len(pkg_data.get("dependencies", {}).get("peerDependencies", {})),
                "optional_count": len(
                    pkg_data.get("dependencies", {}).get("optionalDependencies", {})
                ),
                "has_native": self._has_native_dependencies(pkg_data),
                "has_deprecated": await self._has_deprecated_dependencies(pkg_data),
            },
            "security": {
                "vulnerabilities": info.get("vulnerabilities", []),
                "has_vulnerabilities": len(info.get("vulnerabilities", [])) > 0,
            },
            "compatibility": {
                "node_versions": pkg_data.get("engines", {}).get("node"),
                "npm_versions": pkg_data.get("engines", {}).get("npm"),
                "platforms": {
                    "os": pkg_data.get("os", ["any"]),
                    "cpu": pkg_data.get("cpu", ["any"]),
                },
            },
            "quality_score": self._calculate_quality_score(info, pkg_data),
        }

        return analysis

    async def _get_download_stats(self, package_name: str) -> dict[str, int]:
        package_name = normalize_package_name(package_name)
        try:
            endpoints = {
                "daily": f"/point/last-day/{quote(package_name)}",
                "weekly": f"/point/last-week/{quote(package_name)}",
                "monthly": f"/point/last-month/{quote(package_name)}",
                "yearly": f"/point/last-year/{quote(package_name)}",
            }

            stats = {}
            for period, endpoint in endpoints.items():
                url = f"{self.downloads_url}{endpoint}"
                data = await self._make_request("GET", url)
                if data:
                    stats[period] = data.get("downloads", 0)
                else:
                    stats[period] = 0

            return stats
        except Exception:
            return {"daily": 0, "weekly": 0, "monthly": 0, "yearly": 0}

    async def _check_typescript_support(
        self, package_name: str, latest_data: dict
    ) -> dict[str, Any]:
        types_info = {"has_types": False, "types_package": None, "included": False}

        if latest_data.get("types") or latest_data.get("typings"):
            types_info["has_types"] = True
            types_info["included"] = True
            return types_info

        normalized_name = normalize_package_name(package_name)
        types_package_name = f"@types/{normalized_name.replace('@', '').replace('/', '__')}"
        types_exists = await self._package_exists(types_package_name)

        if types_exists:
            types_info["has_types"] = True
            types_info["types_package"] = types_package_name  # type: ignore[assignment]

        return types_info

    async def _package_exists(self, package_name: str) -> bool:
        package_name = normalize_package_name(package_name)
        info = await self.get_package_info(
            package_name, include_readme=False, include_versions=False
        )
        return info is not None

    async def _has_deprecated_dependencies(self, pkg_data: dict[str, Any]) -> bool:
        deps = pkg_data.get("dependencies", {}).get("dependencies", {})

        for dep_name, version_spec in deps.items():
            resolved_version = await self.resolve_version(dep_name, version_spec)
            if resolved_version:
                dep_info = await self.get_package_version(dep_name, resolved_version)
                if dep_info and dep_info.get("deprecated"):
                    return True

        return False

    def _calculate_quality_score(self, info: dict[str, Any], pkg_data: dict[str, Any]) -> float:
        score = 0.0
        max_score = 10.0

        if info.get("readme"):
            score += 1.0
        if info.get("homepage"):
            score += 0.5
        if info.get("repository"):
            score += 0.5
        if info.get("license"):
            score += 1.0

        if info.get("keywords") and len(info["keywords"]) > 0:
            score += 0.5
        if pkg_data.get("scripts", {}).get("test"):
            score += 1.0
        if info.get("typescript", {}).get("has_types"):
            score += 1.0

        if info.get("time", {}).get("modified"):
            last_modified = datetime.fromisoformat(info["time"]["modified"].replace("Z", "+00:00"))
            days_since_update = (datetime.now(last_modified.tzinfo) - last_modified).days
            if days_since_update < 365:
                score += 1.0
            elif days_since_update < 730:
                score += 0.5

        weekly_downloads = info.get("downloads", {}).get("weekly", 0)
        if weekly_downloads > 1000000:
            score += 2.0
        elif weekly_downloads > 10000:
            score += 1.5
        elif weekly_downloads > 1000:
            score += 1.0
        elif weekly_downloads > 100:
            score += 0.5

        if not info.get("vulnerabilities"):
            score += 1.0

        return min(score / max_score, 1.0)

    def _process_versions(
        self, versions_data: dict[str, Any], time_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        versions: list[Any] = []
        for version, data in versions_data.items():
            if parse_version(version) is None:
                logger.warning(f"Skipping invalid npm version: {version}")
                continue

            engines = data.get("engines", {})
            if not isinstance(engines, dict):
                engines = {}
            versions.append(
                {
                    "version": version,
                    "deprecated": data.get("deprecated"),
                    "published": time_data.get(version),
                    "node": engines.get("node"),
                    "npm": engines.get("npm"),
                    "dist": {
                        "tarball": data.get("dist", {}).get("tarball"),
                        "shasum": data.get("dist", {}).get("shasum"),
                        "integrity": data.get("dist", {}).get("integrity"),
                        "size": data.get("dist", {}).get("unpackedSize", 0),
                        "fileCount": data.get("dist", {}).get("fileCount", 0),
                    },
                    "hasNativeDeps": self._has_native_dependencies(data),
                    "dependencies": data.get("dependencies", {}),
                    "peerDependencies": data.get("peerDependencies", {}),
                    "optionalDependencies": data.get("optionalDependencies", {}),
                }
            )

        versions.sort(
            key=lambda x: parse_version_key(x["version"]),
            reverse=True,
        )

        return versions

    def _categorize_dependencies(self, version_data: dict[str, Any]) -> dict[str, dict]:
        return {
            "dependencies": version_data.get("dependencies", {}),
            "devDependencies": version_data.get("devDependencies", {}),
            "peerDependencies": version_data.get("peerDependencies", {}),
            "optionalDependencies": version_data.get("optionalDependencies", {}),
            "bundledDependencies": version_data.get("bundledDependencies", []),
        }

    def _extract_detailed_requirements(self, version_data: dict[str, Any]) -> dict[str, Any]:
        requirements: dict[str, Any] = {
            "node": None,
            "npm": None,
            "os": [],
            "cpu": [],
            "build_tools_required": False,
            "python_required": False,
            "native_modules": [],
        }

        engines = version_data.get("engines", {})
        if "node" in engines:
            requirements["node"] = {  # type: ignore[assignment]
                "spec": engines["node"],
                "minimum": self._extract_min_version(engines["node"]),
            }
        if "npm" in engines:
            requirements["npm"] = {  # type: ignore[assignment]
                "spec": engines["npm"],
                "minimum": self._extract_min_version(engines["npm"]),
            }

        requirements["os"] = version_data.get("os", ["any"])
        requirements["cpu"] = version_data.get("cpu", ["any"])

        deps = version_data.get("dependencies", {})
        native_indicators = [
            "node-gyp",
            "prebuild",
            "prebuild-install",
            "node-pre-gyp",
            "bindings",
            "nan",
            "node-addon-api",
        ]

        for dep in deps:
            if any(indicator in dep.lower() for indicator in native_indicators):
                requirements["build_tools_required"] = True
                requirements["native_modules"].append(dep)  # type: ignore[union-attr]

        if requirements["build_tools_required"]:
            requirements["python_required"] = True

        scripts = version_data.get("scripts", {})
        if any("node-gyp" in script or "prebuild" in script for script in scripts.values()):
            requirements["build_tools_required"] = True

        return requirements

    def _parse_version_requirement(self, spec: str) -> VersionRequirement:
        if spec in self._semver_cache:
            return self._semver_cache[spec]

        req = VersionRequirement(raw=spec)

        patterns = {
            r"^(\d+)\.(\d+)\.(\d+)$": lambda m: {
                "major": int(m[1]),
                "minor": int(m[2]),
                "patch": int(m[3]),
            },
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
            r"^>=?(\d+)\.(\d+)\.(\d+)": lambda m: {
                "operator": ">=",
                "major": int(m[1]),
                "minor": int(m[2]),
                "patch": int(m[3]),
            },
            r"^<=?(\d+)\.(\d+)\.(\d+)": lambda m: {
                "operator": "<=",
                "major": int(m[1]),
                "minor": int(m[2]),
                "patch": int(m[3]),
            },
            r"^\*|^$": lambda m: {"operator": "*"},
        }

        for pattern, handler in patterns.items():
            match = re.match(pattern, spec.strip())
            if match:
                result_dict = handler(match)
                if isinstance(result_dict, dict):
                    for key, value in result_dict.items():
                        setattr(req, key, value)
                break

        self._semver_cache[spec] = req
        return req

    def _version_matches_requirement(self, version: str, requirement: VersionRequirement) -> bool:
        try:
            v = parse_version(version)
            if v is None:
                return False

            if requirement.operator == "*":
                return True

            if requirement.operator == "^":
                req_v_str = f"{requirement.major}.{requirement.minor}.{requirement.patch}"
                req_v = parse_version(req_v_str)
                if req_v is None:
                    return False

                if requirement.major is not None and requirement.major > 0:
                    return v >= req_v and v.major == requirement.major
                if requirement.minor is not None and requirement.minor > 0:
                    return v >= req_v and v.major == 0 and v.minor == requirement.minor
                return v == req_v

            if requirement.operator == "~":
                req_v_str = f"{requirement.major}.{requirement.minor}.{requirement.patch}"
                req_v = parse_version(req_v_str)
                next_minor_str = (
                    f"{requirement.major}.{requirement.minor + 1}.0"
                    if requirement.minor is not None
                    else None
                )
                next_minor = parse_version(next_minor_str) if next_minor_str else None

                if req_v is None or next_minor is None:
                    return False

                return v >= req_v and v < next_minor

            if requirement.operator == ">=":
                req_v_str = f"{requirement.major}.{requirement.minor}.{requirement.patch}"
                req_v = parse_version(req_v_str)
                if req_v is None:
                    return False
                return v >= req_v

            if requirement.operator == "<=":
                req_v_str = f"{requirement.major}.{requirement.minor}.{requirement.patch}"
                req_v = parse_version(req_v_str)
                if req_v is None:
                    return False
                return v <= req_v

            req_v_str = f"{requirement.major}.{requirement.minor}.{requirement.patch}"
            req_v = parse_version(req_v_str)
            if req_v is None:
                return False
            return v == req_v

        except Exception:
            return False

    def _version_satisfies(self, installed: str, required: str) -> bool:
        req = self._parse_version_requirement(required)
        return self._version_matches_requirement(installed, req)

    def _check_node_compatibility(self, system_version: str, required: str) -> bool:
        return self._version_satisfies(system_version, required)

    def _check_npm_compatibility(self, system_version: str, required: str) -> bool:
        return self._version_satisfies(system_version, required)

    def _check_os_compatibility(self, system_os: str, supported: list[str]) -> bool:
        if not supported or "any" in supported:
            return True

        blocked = [os[1:] for os in supported if os.startswith("!")]
        allowed = [os for os in supported if not os.startswith("!")]

        if system_os in blocked:
            return False

        return not (allowed and system_os not in allowed)

    def _check_cpu_compatibility(self, system_cpu: str, supported: list[str]) -> bool:
        if not supported or "any" in supported:
            return True

        blocked = [cpu[1:] for cpu in supported if cpu.startswith("!")]
        allowed = [cpu for cpu in supported if not cpu.startswith("!")]

        if system_cpu in blocked:
            return False

        return not (allowed and system_cpu not in allowed)

    def _extract_min_version(self, version_spec: str) -> str | None:
        match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version_spec)
        if match:
            return match.group(0)
        return None

    def _has_native_dependencies(self, version_data: dict[str, Any]) -> bool:
        if version_data.get("gypfile"):
            return True

        deps = version_data.get("dependencies", {})
        native_packages = [
            "node-gyp",
            "prebuild",
            "prebuild-install",
            "node-pre-gyp",
            "bindings",
            "nan",
            "node-addon-api",
        ]

        return any(pkg in deps for pkg in native_packages)

    def _is_prerelease(self, version: str) -> bool:
        return bool(re.search(r"-(alpha|beta|rc|pre|dev|canary|next)", version))

    def _format_person(self, person: str | dict[str, Any]) -> dict[str, str]:
        if isinstance(person, str):
            match = re.match(r"^([^<]+?)(?:\s*<([^>]+)>)?(?:\s*\(([^)]+)\))?$", person)
            if match:
                return {
                    "name": match.group(1).strip(),
                    "email": match.group(2),
                    "url": match.group(3),
                }
            return {"name": person}
        if isinstance(person, dict):
            return {
                "name": person.get("name", ""),
                "email": person.get("email"),
                "url": person.get("url"),
            }
        return {}

    def _extract_publisher(self, publisher: str | dict[str, Any]) -> dict[str, str]:
        if isinstance(publisher, dict):
            return {
                "username": publisher.get("username", ""),
                "email": publisher.get("email"),
            }
        return {"username": str(publisher) if publisher else ""}

    def _extract_repository(self, links: dict[str, Any]) -> str | None:
        repo = links.get("repository")
        if repo:
            return repo

        for key in ["homepage", "bugs"]:
            url = links.get(key, "")
            if "github.com" in url or "gitlab.com" in url or "bitbucket.org" in url:
                match = re.match(r"(https?://[^/]+/[^/]+/[^/]+)", url)
                if match:
                    return match.group(1)

        return None

    def _extract_repository_info(self, repository: str | dict[str, Any]) -> dict[str, str]:
        if isinstance(repository, str):
            return {"type": "git", "url": repository}
        if isinstance(repository, dict):
            return {
                "type": repository.get("type", "git"),
                "url": repository.get("url", ""),
                "directory": repository.get("directory"),
            }
        return {}


async def example_usage():
    """Async example usage."""
    async with NPMClient() as client:
        await client.search_packages("react", limit=10, quality=0.8, popularity=0.5)

        await client.get_package_info("express", include_readme=True)

        await client.resolve_version("lodash", "^4.17.0")

        await client.get_dependency_tree("axios", max_depth=2)

        await client.check_compatibility(
            "node-sass",
            "7.0.0",
            {
                "node_version": "16.0.0",
                "npm_version": "8.0.0",
                "os": "darwin",
                "cpu": "x64",
                "has_build_tools": True,
            },
        )

        analysis = await client.analyze_package("webpack")

        print(f"Quality score: {analysis['quality_score']}")


if __name__ == "__main__":
    asyncio.run(example_usage())
