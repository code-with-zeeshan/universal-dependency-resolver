"""Module docstring."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from packaging import version as packaging_version

from ...core.utils import normalize_package_name, parse_version
from ...settings import (
    ENABLE_CACHE,
    get_ecosystem_config,
)
from ..base_client import BaseDataSourceClient
from .pom_parser import PomParser
from .version_utils import (
    _compare_java_versions,
    _get_element_text,
    _is_maven_version,
    _parse_version_range_syntax,
    _should_include_transitive_dependency,
    _sort_maven_version,
)

logger = logging.getLogger(__name__)


class MavenClient(BaseDataSourceClient):
    def __init__(self):
        maven_config = get_ecosystem_config("maven")

        super().__init__(
            ecosystem="maven",
            base_url=maven_config.get("search_url", "https://search.maven.org/solrsearch/select"),
        )

        self.artifact_url = "https://search.maven.org/artifact"
        self.maven_repo_url = maven_config.get("url", "https://repo1.maven.org/maven2")
        self.additional_repos = []
        self._pom_cache = {} if ENABLE_CACHE else None
        self._pom_parser = PomParser(self)

    def _should_cache(self, url: str) -> bool:
        from ..maven_client import ENABLE_CACHE as _cache_enabled

        if not _cache_enabled or self._pom_cache is None:
            return False
        return "search" not in url

    async def _make_request(self, url: str, params: dict | None = None) -> Any:  # type: ignore[override]
        session = self._get_session()

        cache_key = f"{url}:{params!s}"
        if self._should_cache(url) and cache_key in self._pom_cache:
            cached_data, cached_time = self._pom_cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                logger.debug(f"Cache hit for {url}")
                return cached_data

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with session.get(
                    url, params=params, headers=self._auth_headers or None
                ) as response:
                    if response.status == 404:
                        return None

                    if response.status != 200:
                        raise HTTPException(
                            status_code=response.status,
                            detail=f"Maven API error: {response.status}",
                        )

                    content_type = response.headers.get("Content-Type", "")
                    if "json" in content_type:
                        data = await response.json()
                    else:
                        data = await response.text()

                    if self._should_cache(url):
                        self._pom_cache[cache_key] = (data, datetime.now())
                        if len(self._pom_cache) > 1000:
                            self._clean_cache()

                    return data

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue

        raise HTTPException(
            status_code=500,
            detail=f"Failed after {self.max_retries} attempts: {last_error}",
        )

    def _clean_cache(self):
        if not self._pom_cache:
            return

        current_time = datetime.now()
        expired_keys = [
            key
            for key, (_, timestamp) in self._pom_cache.items()
            if (current_time - timestamp).total_seconds() > self._cache_ttl
        ]

        for key in expired_keys:
            del self._pom_cache[key]

    def _normalize_maven_coordinates(self, group_id: str, artifact_id: str) -> tuple[str, str]:
        artifact_id = normalize_package_name(artifact_id)

        group_parts = group_id.split(".")
        normalized_parts = [normalize_package_name(part) for part in group_parts]
        group_id = ".".join(normalized_parts)

        return group_id, artifact_id

    # -- version_utils wrappers (backward compat) --

    def _is_maven_version(self, version_str: str) -> bool:
        return _is_maven_version(version_str)

    def _sort_maven_version(self, version_str: str) -> tuple:
        return _sort_maven_version(version_str)

    def _compare_java_versions(self, version1: str, version2: str) -> int:
        return _compare_java_versions(version1, version2)

    def _parse_version_range_syntax(self, range_str: str) -> dict:
        return _parse_version_range_syntax(range_str)

    def _should_include_transitive_dependency(self, parent_scope: str, dep_scope: str) -> bool:
        return _should_include_transitive_dependency(parent_scope, dep_scope)

    def _get_element_text(self, parent, tag: str, namespaces: dict) -> str | None:
        return _get_element_text(parent, tag, namespaces)

    # -- pom_parser wrappers (backward compat) --

    def _merge_poms(self, parent_pom: dict, child_pom: dict) -> dict:
        return self._pom_parser._merge_poms(parent_pom, child_pom)

    def _extract_properties(self, root, namespaces) -> dict[str, str]:
        return self._pom_parser._extract_properties(root, namespaces)

    def _substitute_properties(self, value: str, properties: dict[str, str]) -> str:
        return self._pom_parser._substitute_properties(value, properties)

    def _extract_parent_info(self, parent_elem, namespaces) -> dict | None:
        return self._pom_parser._extract_parent_info(parent_elem, namespaces)

    def _parse_repositories(self, root, namespaces, properties) -> list[dict]:
        return self._pom_parser._parse_repositories(root, namespaces, properties)

    def _parse_plugin_repositories(self, root, namespaces, properties) -> list[dict]:
        return self._pom_parser._parse_plugin_repositories(root, namespaces, properties)

    def _parse_dependency_management(
        self, dep_mgmt_elem, namespaces, properties
    ) -> dict[str, dict]:
        return self._pom_parser._parse_dependency_management(dep_mgmt_elem, namespaces, properties)

    def _parse_plugin_management(self, plugin_mgmt_elem, namespaces, properties) -> dict[str, dict]:
        return self._pom_parser._parse_plugin_management(plugin_mgmt_elem, namespaces, properties)

    def _parse_profiles(self, profiles_elem, namespaces, parent_properties) -> dict[str, dict]:
        return self._pom_parser._parse_profiles(profiles_elem, namespaces, parent_properties)

    def _parse_activation(self, activation_elem, namespaces) -> dict:
        return self._pom_parser._parse_activation(activation_elem, namespaces)

    def _parse_dependencies_section(
        self, deps_elem, namespaces, properties, dep_management
    ) -> list[dict]:
        return self._pom_parser._parse_dependencies_section(
            deps_elem, namespaces, properties, dep_management
        )

    def _extract_dependency_info(
        self, dep_elem, namespaces, properties, dep_management
    ) -> dict | None:
        return self._pom_parser._extract_dependency_info(
            dep_elem, namespaces, properties, dep_management
        )

    def _extract_dependency_info_with_exclusions(
        self, dep_elem, namespaces, properties, dep_management
    ) -> dict | None:
        return self._pom_parser._extract_dependency_info_with_exclusions(
            dep_elem, namespaces, properties, dep_management
        )

    def _parse_plugins_section(
        self, plugins_elem, namespaces, properties, plugin_management
    ) -> list[dict]:
        return self._pom_parser._parse_plugins_section(
            plugins_elem, namespaces, properties, plugin_management
        )

    def _extract_plugin_info(
        self, plugin_elem, namespaces, properties, plugin_management
    ) -> dict | None:
        return self._pom_parser._extract_plugin_info(
            plugin_elem, namespaces, properties, plugin_management
        )

    def _parse_configuration(self, config_elem, properties) -> dict:
        return self._pom_parser._parse_configuration(config_elem, properties)

    def _parse_pom_comprehensive(
        self, pom_xml, group_id, artifact_id, version, active_profiles=None
    ) -> dict:
        return self._pom_parser._parse_pom_comprehensive(
            pom_xml, group_id, artifact_id, version, active_profiles
        )

    def _apply_profiles(self, pom_data: dict, active_profiles: list[str]) -> dict:
        return self._pom_parser._apply_profiles(pom_data, active_profiles)

    def _apply_default_profiles(self, pom_data: dict, active_profiles: list[str] | None) -> dict:
        return self._pom_parser._apply_default_profiles(pom_data, active_profiles)

    def _apply_final_property_substitution(self, pom_data: dict) -> dict:
        return self._pom_parser._apply_final_property_substitution(pom_data)

    # -- Public API --

    async def search_packages(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        try:
            params = {"q": query, "rows": limit, "wt": "json"}

            data = await self._make_request(self.base_url, params=params)
            if not data:
                raise HTTPException(status_code=500, detail="Failed to search Maven packages")

            results = []
            for doc in data.get("response", {}).get("docs", []):
                results.append(
                    {
                        "name": f"{doc.get('g')}:{doc.get('a')}",
                        "ecosystem": "maven",
                        "version": doc.get("latestVersion"),
                        "description": doc.get("text", ["No description"])[0],
                        "system_requirements": {"java_versions": ["8+"], "os": ["any"]},
                    }
                )
            return results

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Maven search error: {e!s}")

    # ── Standard interface (used by DataAggregator) ─────────────────────

    async def get_package_info_async(
        self,
        package_name: str,
        include_dependencies: bool = False,
        include_versions: bool = True,
    ) -> dict[str, Any] | None:
        """Standard interface: single package_name, returns None on not-found."""
        group_id, artifact_id = (
            package_name.split(":", 1) if ":" in package_name else (package_name, package_name)
        )
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)

        try:
            session = self._get_session()
            params = {"q": f"g:{group_id} AND a:{artifact_id}", "rows": 1, "wt": "json"}
            async with session.get(self.base_url, params=params) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                docs = data.get("response", {}).get("docs", [])
                if not docs:
                    return None

            doc = docs[0]
            result: dict[str, Any] = {
                "name": f"{group_id}:{artifact_id}",
                "ecosystem": "maven",
                "version": doc.get("latestVersion", "unknown"),
                "description": doc.get("text", [""])[0] if doc.get("text") else "",
                "versions": [],
                "dependencies": {"dependencies": {}},
                "system_requirements": {"java_versions": ["8+"], "os": ["any"]},
                "compatibility_matrix": {"java": {"minimum": "1.8", "recommended": "11"}},
            }

            if include_versions:
                versions = await self.get_package_versions(group_id, artifact_id)
                result["versions"] = versions if versions else []

            if include_dependencies:
                deps = await self.get_dependencies(group_id, artifact_id, result["version"])
                if deps:
                    result["dependencies"]["dependencies"] = {
                        d.get("name", f"{d['group_id']}:{d['artifact_id']}"): d.get("version", "*")
                        for d in deps
                    }

            return result

        except Exception:
            return None

    # ── Legacy interface (backward compat with direct calls) ────────────

    async def get_package_info(self, group_id: str, artifact_id: str) -> dict[str, Any]:
        """Legacy signature. Prefer get_package_info_async for new code."""
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        try:
            session = self._get_session()
            params = {"q": f"g:{group_id} AND a:{artifact_id}", "rows": 1, "wt": "json"}  # type: ignore[misc]
            async with session.get(self.base_url, params=params) as response:  # type: ignore[arg-type]
                if response.status != 200:
                    raise HTTPException(status_code=404, detail="Maven package not found")
                data = await response.json()
                docs = data.get("response", {}).get("docs", [])
                if not docs:
                    raise HTTPException(status_code=404, detail="Maven package not found")

                doc = docs[0]
                return {
                    "name": f"{group_id}:{artifact_id}",
                    "ecosystem": "maven",
                    "info": {
                        "group_id": group_id,
                        "artifact_id": artifact_id,
                        "latest_version": doc.get("latestVersion", "unknown"),
                        "last_updated": doc.get("timestamp", datetime.utcnow().isoformat()),
                        "repository_count": doc.get("repositoryCount", 0),
                        "available_versions": doc.get("versionCount", 0),
                    },
                    "system_requirements": {"java_versions": ["8+"], "os": ["any"]},
                    "compatibility_matrix": {"java": {"minimum": "1.8", "recommended": "11"}},
                }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Maven package info error: {e!s}")

    async def get_package_versions(
        self, group_id: str, artifact_id: str, filters: dict | None = None
    ) -> list[dict]:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        try:
            session = self._get_session()
            params = {
                "q": f"g:{group_id} AND a:{artifact_id}",
                "core": "gav",
                "rows": 100,
                "wt": "json",
            }  # type: ignore[misc]
            async with session.get(self.base_url, params=params) as response:  # type: ignore[arg-type]
                if response.status != 200:
                    raise HTTPException(status_code=404, detail="Maven package versions not found")
                data = await response.json()
                versions: list[Any] = []
                for doc in data.get("response", {}).get("docs", []):
                    version_str = doc.get("v")
                    if not version_str:
                        continue

                    parsed_version = parse_version(version_str)
                    if parsed_version is None and not _is_maven_version(version_str):
                        logger.warning(f"Skipping invalid Maven version: {version_str}")
                        continue

                    version_info = {
                        "version": version_str,
                        "release_date": doc.get("timestamp", datetime.utcnow().isoformat()),
                        "system_requirements": {"java_versions": ["8+"], "os": ["any"]},
                    }

                    if filters:
                        if "version_range" in filters:
                            range_info = self._parse_version_range(filters["version_range"])
                            if not self._version_matches_range(version_str, range_info):
                                continue

                        if "release_type" in filters and (
                            (
                                filters["release_type"] == "stable"
                                and (
                                    "SNAPSHOT" in version_str
                                    or "alpha" in version_str.lower()
                                    or "beta" in version_str.lower()
                                )
                            )
                            or (
                                filters["release_type"] == "snapshot"
                                and "SNAPSHOT" not in version_str
                            )
                        ):
                            continue

                    versions.append(version_info)

                return sorted(
                    versions,
                    key=lambda x: _sort_maven_version(x["version"]),
                    reverse=True,
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Maven versions error: {e!s}")

    async def check_compatibility(
        self, group_id: str, artifact_id: str, version: str, system_info: dict
    ) -> dict:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        try:
            pom_xml = await self._fetch_pom(group_id, artifact_id, version)

            compatibility: dict[str, Any] = {
                "compatible": True,
                "details": {},
                "warnings": [],
                "errors": [],
            }

            if pom_xml:
                root = ET.fromstring(pom_xml)
                namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}

                properties = self._pom_parser._extract_properties(root, namespaces)

                java_version_props = [
                    "maven.compiler.source",
                    "maven.compiler.target",
                    "java.version",
                    "project.build.sourceLevel",
                ]

                required_java = None
                for prop in java_version_props:
                    if prop in properties:
                        required_java = properties[prop]
                        break

                if required_java and "java_version" in system_info:
                    system_java = system_info["java_version"]
                    if _compare_java_versions(system_java, required_java) < 0:
                        compatibility["compatible"] = False
                        compatibility["errors"].append(
                            f"Requires Java {required_java} or higher, but system has Java {system_java}"
                        )
                    else:
                        compatibility["details"]["java_version"] = (
                            f"Compatible (requires Java {required_java}+)"
                        )
                else:
                    compatibility["details"]["java_version"] = "Compatible with Java 8+"

                compatibility["details"]["os"] = "Compatible with any OS"

                profiles = self._pom_parser._parse_profiles(root, namespaces, properties)
                for profile_id, profile in profiles.items():
                    if "activation" in profile and "os" in profile["activation"]:
                        os_req = profile["activation"]["os"]
                        if (
                            os_req.get("name")
                            and system_info.get("os_name")
                            and os_req["name"].lower() not in system_info["os_name"].lower()
                        ):
                            compatibility["warnings"].append(
                                f"Profile '{profile_id}' is OS-specific for {os_req['name']}"
                            )

            return compatibility

        except Exception as e:
            return {
                "compatible": True,
                "details": {
                    "java_version": "Compatible with Java 8+",
                    "os": "Compatible with any OS",
                },
                "warnings": [f"Could not verify compatibility: {e!s}"],
            }

    async def get_dependencies(
        self,
        group_id: str,
        artifact_id: str,
        version: str | None = None,
        active_profiles: list[str] | None = None,
        repositories: list[dict] | None = None,
    ) -> list[dict]:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        try:
            if not version:
                versions = await self.get_package_versions(group_id, artifact_id)
                if not versions:
                    return []
                version = versions[0]["version"]

            effective_pom = await self.get_effective_pom(
                group_id, artifact_id, version, active_profiles, repositories
            )

            return effective_pom.get("dependencies", [])

        except Exception as e:
            print(f"Error fetching dependencies: {e!s}")
            return []

    async def get_effective_pom(
        self,
        group_id: str,
        artifact_id: str,
        version: str,
        active_profiles: list[str] | None = None,
        repositories: list[dict] | None = None,
    ) -> dict:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)

        if repositories is None:
            repositories = [{"id": "central", "url": self.maven_repo_url}]
        else:
            has_central = any(repo.get("id") == "central" for repo in repositories)
            if not has_central:
                repositories.append({"id": "central", "url": self.maven_repo_url})

        pom_data = await self._fetch_and_parse_pom_hierarchy(
            group_id, artifact_id, version, repositories, active_profiles
        )

        return pom_data

    async def _fetch_pom(self, group_id: str, artifact_id: str, version: str) -> str | None:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        group_path = group_id.replace(".", "/")
        pom_url = f"{self.maven_repo_url}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.pom"

        try:
            session = self._get_session()
            async with session.get(pom_url) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except Exception:
            return None

    async def _fetch_and_parse_pom_hierarchy(
        self,
        group_id: str,
        artifact_id: str,
        version: str,
        repositories: list[dict],
        active_profiles: list[str] | None = None,
        child_pom_data: dict | None = None,
    ) -> dict:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)

        cache_key = f"{group_id}:{artifact_id}:{version}"
        if cache_key in self._pom_cache:
            return self._pom_cache[cache_key].copy()

        pom_xml = await self._fetch_pom_from_repos(group_id, artifact_id, version, repositories)
        if not pom_xml:
            return child_pom_data or {"dependencies": []}

        current_pom = self._pom_parser._parse_pom_comprehensive(
            pom_xml, group_id, artifact_id, version, active_profiles
        )

        if current_pom.get("parent"):
            parent = current_pom["parent"]
            parent_pom = await self._fetch_and_parse_pom_hierarchy(
                parent["group_id"],
                parent["artifact_id"],
                parent["version"],
                repositories + current_pom.get("repositories", []),
                active_profiles,
            )

            merged_pom = self._pom_parser._merge_poms(parent_pom, current_pom)
        else:
            merged_pom = current_pom

        if child_pom_data:
            merged_pom = self._pom_parser._merge_poms(merged_pom, child_pom_data)

        merged_pom = self._pom_parser._apply_final_property_substitution(merged_pom)

        self._pom_cache[cache_key] = merged_pom.copy()

        return merged_pom

    async def _fetch_pom_from_repos(
        self, group_id: str, artifact_id: str, version: str, repositories: list[dict]
    ) -> str | None:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        group_path = group_id.replace(".", "/")
        pom_filename = f"{artifact_id}-{version}.pom"
        pom_path = f"{group_path}/{artifact_id}/{version}/{pom_filename}"

        all_repos = repositories.copy()
        for repo_url in self.additional_repos:
            if repo_url:
                all_repos.append({"url": repo_url, "id": f"additional-{len(all_repos)}"})

        if not any(repo.get("id") == "central" for repo in all_repos):
            all_repos.append({"id": "central", "url": self.maven_repo_url})

        for repo in all_repos:
            repo_url = repo.get("url", self.maven_repo_url).rstrip("/")
            pom_url = f"{repo_url}/{pom_path}"

            try:
                pom_content = await self._fetch_pom_content(pom_url)
                if pom_content:
                    return pom_content
            except Exception:
                continue

        return None

    async def _fetch_pom_content(self, url: str) -> str | None:
        session = self._get_session()
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except Exception:
            return None

    def _parse_version_range(self, version_str: str) -> dict[str, Any]:
        if not version_str:
            return {"type": "unspecified"}

        if version_str.startswith(("[", "(")):
            return _parse_version_range_syntax(version_str)
        return {"type": "fixed", "version": version_str}

    async def resolve_version_from_range(
        self, group_id: str, artifact_id: str, version_range: dict
    ) -> str | None:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        if version_range["type"] == "fixed":
            return version_range["version"]

        versions = await self.get_package_versions(group_id, artifact_id)
        if not versions:
            return None

        available_versions = [v["version"] for v in versions]

        if version_range["type"] == "range":
            matching_versions = []

            for v in available_versions:
                if self._version_matches_range(v, version_range):
                    matching_versions.append(v)

            if matching_versions:
                return sorted(
                    matching_versions,
                    key=lambda x: packaging_version.parse(x),
                    reverse=True,
                )[0]

        return None

    def _version_matches_range(self, version_str: str, range_info: dict) -> bool:
        try:
            v = parse_version(version_str)
            if v is None:
                if _is_maven_version(version_str):
                    if "SNAPSHOT" in version_str:
                        base_version = version_str.replace("-SNAPSHOT", "")
                        v = parse_version(base_version)
                        if v is None:
                            return False
                else:
                    return False

            if range_info["min_version"]:
                min_v = parse_version(range_info["min_version"])
                if min_v is None or v is None:
                    return False
                if range_info["min_inclusive"]:
                    if v < min_v:
                        return False
                elif v <= min_v:
                    return False

            if range_info["max_version"]:
                max_v = parse_version(range_info["max_version"])
                if max_v is None or v is None:
                    return False
                if range_info["max_inclusive"]:
                    if v > max_v:
                        return False
                elif v >= max_v:
                    return False

            return True
        except Exception:
            return False

    async def get_transitive_dependencies(
        self,
        group_id: str,
        artifact_id: str,
        version: str,
        scope: str = "compile",
        repositories: list[dict] | None = None,
        visited: set[str] | None = None,
        exclusions: list[dict] | None = None,
    ) -> list[dict]:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        if visited is None:
            visited = set()

        key = f"{group_id}:{artifact_id}:{version}"
        if key in visited:
            return []

        visited.add(key)

        if exclusions:
            for exclusion in exclusions:
                exc_group = exclusion.get("group_id", "*")
                exc_artifact = exclusion.get("artifact_id", "*")

                if (exc_group == "*" or exc_group == group_id) and (
                    exc_artifact == "*" or exc_artifact == artifact_id
                ):
                    return []

        effective_pom = await self.get_effective_pom(
            group_id, artifact_id, version, None, repositories
        )

        all_dependencies = []

        for dep in effective_pom.get("dependencies", []):
            dep_scope = dep.get("scope", "compile")

            if not _should_include_transitive_dependency(scope, dep_scope):
                continue

            all_dependencies.append(dep)

            if dep.get("version") and dep.get("version") != "unspecified":
                transitive = await self.get_transitive_dependencies(
                    dep["group_id"],
                    dep["artifact_id"],
                    dep["version"],
                    dep_scope,
                    repositories + effective_pom.get("repositories", []),
                    visited,
                    dep.get("exclusions", []),
                )
                all_dependencies.extend(transitive)

        return all_dependencies

    async def get_dependency_tree(
        self,
        group_id: str,
        artifact_id: str,
        version: str | None = None,
        max_depth: int = 2,
        visited: set | None = None,
    ) -> dict:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        if visited is None:
            visited = set()

        key = f"{group_id}:{artifact_id}:{version}"
        if key in visited or max_depth <= 0:
            return {
                "name": f"{group_id}:{artifact_id}",
                "version": version,
                "dependencies": [],
            }

        visited.add(key)

        dependencies = await self.get_dependencies(group_id, artifact_id, version)

        tree: dict[str, Any] = {
            "name": f"{group_id}:{artifact_id}",
            "version": version or "latest",
            "dependencies": [],
        }

        for dep in dependencies:
            if dep.get("scope") not in ["test", "provided"] and not dep.get("optional"):
                dep_tree = await self.get_dependency_tree(
                    dep["group_id"],
                    dep["artifact_id"],
                    dep.get("version"),
                    max_depth - 1,
                    visited,
                )
                tree["dependencies"].append(dep_tree)

        return tree
