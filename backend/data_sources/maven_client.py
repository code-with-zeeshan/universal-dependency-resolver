# maven_client.py
import asyncio
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict, Any, Tuple, Set
from packaging import version
from datetime import datetime
from fastapi import HTTPException
from ..core.utils import normalize_package_name, parse_version
import re
from ..settings import (
    ENABLE_CACHE,
    get_ecosystem_config,
)
from .base_client import BaseDataSourceClient

import logging

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

    def _should_cache(self, url: str) -> bool:
        if not ENABLE_CACHE or self._pom_cache is None:
            return False
        return "search" not in url

    async def _make_request(self, url: str, params: Optional[Dict] = None) -> Any:
        session = self._get_session()

        cache_key = f"{url}:{str(params)}"
        if self._should_cache(url) and cache_key in self._pom_cache:
            cached_data, cached_time = self._pom_cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                logger.debug(f"Cache hit for {url}")
                return cached_data

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with session.get(url, params=params) as response:
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

    def _normalize_maven_coordinates(
        self, group_id: str, artifact_id: str
    ) -> Tuple[str, str]:
        artifact_id = normalize_package_name(artifact_id)

        group_parts = group_id.split(".")
        normalized_parts = [normalize_package_name(part) for part in group_parts]
        group_id = ".".join(normalized_parts)

        return group_id, artifact_id

    async def search_packages(
        self, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        try:
            params = {"q": query, "rows": limit, "wt": "json"}

            data = await self._make_request(self.base_url, params=params)
            if not data:
                raise HTTPException(
                    status_code=500, detail="Failed to search Maven packages"
                )

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
            raise HTTPException(status_code=500, detail=f"Maven search error: {str(e)}")

    async def get_package_info(self, group_id: str, artifact_id: str) -> Dict[str, Any]:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        try:
            session = self._get_session()
            params = {"q": f"g:{group_id} AND a:{artifact_id}", "rows": 1, "wt": "json"}
            async with session.get(self.base_url, params=params) as response:
                if response.status != 200:
                    raise HTTPException(
                        status_code=404, detail="Maven package not found"
                    )
                data = await response.json()
                docs = data.get("response", {}).get("docs", [])
                if not docs:
                    raise HTTPException(
                        status_code=404, detail="Maven package not found"
                    )

                doc = docs[0]
                return {
                    "name": f"{group_id}:{artifact_id}",
                    "ecosystem": "maven",
                    "info": {
                        "group_id": group_id,
                        "artifact_id": artifact_id,
                        "latest_version": doc.get("latestVersion", "unknown"),
                        "last_updated": doc.get(
                            "timestamp", datetime.utcnow().isoformat()
                        ),
                        "repository_count": doc.get("repositoryCount", 0),
                        "available_versions": doc.get("versionCount", 0),
                    },
                    "system_requirements": {"java_versions": ["8+"], "os": ["any"]},
                    "compatibility_matrix": {
                        "java": {"minimum": "1.8", "recommended": "11"}
                    },
                }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Maven package info error: {str(e)}"
            )

    async def get_package_versions(
        self, group_id: str, artifact_id: str, filters: Optional[Dict] = None
    ) -> List[Dict]:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        try:
            session = self._get_session()
            params = {
                "q": f"g:{group_id} AND a:{artifact_id}",
                "core": "gav",
                "rows": 100,
                "wt": "json",
            }
            async with session.get(self.base_url, params=params) as response:
                if response.status != 200:
                    raise HTTPException(
                        status_code=404, detail="Maven package versions not found"
                    )
                data = await response.json()
                versions = []

                for doc in data.get("response", {}).get("docs", []):
                    version_str = doc.get("v")
                    if not version_str:
                        continue

                    parsed_version = parse_version(version_str)
                    if parsed_version is None and not self._is_maven_version(
                        version_str
                    ):
                        logger.warning(f"Skipping invalid Maven version: {version_str}")
                        continue

                    version_info = {
                        "version": version_str,
                        "release_date": doc.get(
                            "timestamp", datetime.utcnow().isoformat()
                        ),
                        "system_requirements": {"java_versions": ["8+"], "os": ["any"]},
                    }

                    if filters:
                        if "version_range" in filters:
                            range_info = self._parse_version_range(
                                filters["version_range"]
                            )
                            if not self._version_matches_range(version_str, range_info):
                                continue

                        if "release_type" in filters:
                            if filters["release_type"] == "stable" and (
                                "SNAPSHOT" in version_str
                                or "alpha" in version_str.lower()
                                or "beta" in version_str.lower()
                            ):
                                continue
                            elif (
                                filters["release_type"] == "snapshot"
                                and "SNAPSHOT" not in version_str
                            ):
                                continue

                    versions.append(version_info)

                return sorted(
                    versions,
                    key=lambda x: self._sort_maven_version(x["version"]),
                    reverse=True,
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Maven versions error: {str(e)}"
            )

    def _is_maven_version(self, version_str: str) -> bool:
        return bool(re.match(r"^\d+(\.\d+)*(-\w+)?$", version_str))

    def _sort_maven_version(self, version_str: str) -> tuple:
        parsed = parse_version(version_str)
        if parsed:
            return (parsed, 0)

        if "SNAPSHOT" in version_str:
            base_version = version_str.replace("-SNAPSHOT", "")
            parsed_base = parse_version(base_version)
            if parsed_base:
                return (parsed_base, 1)

        return (parse_version("0.0.0"), 2, version_str)

    async def check_compatibility(
        self, group_id: str, artifact_id: str, version: str, system_info: Dict
    ) -> Dict:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        try:
            pom_xml = await self._fetch_pom(group_id, artifact_id, version)

            compatibility = {
                "compatible": True,
                "details": {},
                "warnings": [],
                "errors": [],
            }

            if pom_xml:
                root = ET.fromstring(pom_xml)
                namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}

                properties = self._extract_properties(root, namespaces)

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
                    if self._compare_java_versions(system_java, required_java) < 0:
                        compatibility["compatible"] = False
                        compatibility["errors"].append(
                            f"Requires Java {required_java} or higher, but system has Java {system_java}"
                        )
                    else:
                        compatibility["details"][
                            "java_version"
                        ] = f"Compatible (requires Java {required_java}+)"
                else:
                    compatibility["details"]["java_version"] = "Compatible with Java 8+"

                compatibility["details"]["os"] = "Compatible with any OS"

                profiles = self._parse_profiles(root, namespaces, properties)
                for profile_id, profile in profiles.items():
                    if "activation" in profile and "os" in profile["activation"]:
                        os_req = profile["activation"]["os"]
                        if os_req.get("name") and system_info.get("os_name"):
                            if (
                                os_req["name"].lower()
                                not in system_info["os_name"].lower()
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
                "warnings": [f"Could not verify compatibility: {str(e)}"],
            }

    def _compare_java_versions(self, version1: str, version2: str) -> int:
        def extract_major(v):
            v = v.split("_")[0]
            parts = v.split(".")
            if parts[0] == "1" and len(parts) > 1:
                return int(parts[1])
            return int(parts[0])

        try:
            major1 = extract_major(version1)
            major2 = extract_major(version2)
            return (major1 > major2) - (major1 < major2)
        except Exception:
            return 0

    async def get_dependencies(
        self,
        group_id: str,
        artifact_id: str,
        version: Optional[str] = None,
        active_profiles: Optional[List[str]] = None,
        repositories: Optional[List[Dict]] = None,
    ) -> List[Dict]:
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
            print(f"Error fetching dependencies: {str(e)}")
            return []

    async def get_effective_pom(
        self,
        group_id: str,
        artifact_id: str,
        version: str,
        active_profiles: Optional[List[str]] = None,
        repositories: Optional[List[Dict]] = None,
    ) -> Dict:
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

    async def _fetch_pom(
        self, group_id: str, artifact_id: str, version: str
    ) -> Optional[str]:
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
        repositories: List[Dict],
        active_profiles: Optional[List[str]] = None,
        child_pom_data: Optional[Dict] = None,
    ) -> Dict:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)

        cache_key = f"{group_id}:{artifact_id}:{version}"
        if cache_key in self._pom_cache:
            return self._pom_cache[cache_key].copy()

        pom_xml = await self._fetch_pom_from_repos(
            group_id, artifact_id, version, repositories
        )
        if not pom_xml:
            return child_pom_data or {"dependencies": []}

        current_pom = self._parse_pom_comprehensive(
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

            merged_pom = self._merge_poms(parent_pom, current_pom)
        else:
            merged_pom = current_pom

        if child_pom_data:
            merged_pom = self._merge_poms(merged_pom, child_pom_data)

        merged_pom = self._apply_final_property_substitution(merged_pom)

        self._pom_cache[cache_key] = merged_pom.copy()

        return merged_pom

    async def _fetch_pom_from_repos(
        self, group_id: str, artifact_id: str, version: str, repositories: List[Dict]
    ) -> Optional[str]:
        group_id, artifact_id = self._normalize_maven_coordinates(group_id, artifact_id)
        group_path = group_id.replace(".", "/")
        pom_filename = f"{artifact_id}-{version}.pom"
        pom_path = f"{group_path}/{artifact_id}/{version}/{pom_filename}"

        all_repos = repositories.copy()
        for repo_url in self.additional_repos:
            if repo_url:
                all_repos.append(
                    {"url": repo_url, "id": f"additional-{len(all_repos)}"}
                )

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

    async def _fetch_pom_content(self, url: str) -> Optional[str]:
        session = self._get_session()
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except Exception:
            return None

    def _merge_poms(self, parent_pom: Dict, child_pom: Dict) -> Dict:
        merged = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "exclusions": {},
            "modules": [],
        }

        merged["properties"] = {
            **parent_pom.get("properties", {}),
            **child_pom.get("properties", {}),
        }

        merged["dependency_management"] = {
            **parent_pom.get("dependency_management", {}),
            **child_pom.get("dependency_management", {}),
        }

        parent_deps = {
            f"{d['group_id']}:{d['artifact_id']}": d
            for d in parent_pom.get("dependencies", [])
        }
        child_deps = {
            f"{d['group_id']}:{d['artifact_id']}": d
            for d in child_pom.get("dependencies", [])
        }

        for key, dep in parent_deps.items():
            merged_dep = dep.copy()
            if key in merged["dependency_management"]:
                merged_dep.update(merged["dependency_management"][key])
            merged["dependencies"].append(merged_dep)

        for key, dep in child_deps.items():
            if key not in parent_deps:
                merged["dependencies"].append(dep)
            else:
                for i, merged_dep in enumerate(merged["dependencies"]):
                    if f"{merged_dep['group_id']}:{merged_dep['artifact_id']}" == key:
                        merged["dependencies"][i] = dep
                        break

        repo_ids = set()
        for repo in parent_pom.get("repositories", []) + child_pom.get(
            "repositories", []
        ):
            if repo.get("id") not in repo_ids:
                merged["repositories"].append(repo)
                repo_ids.add(repo.get("id"))

        plugin_repo_ids = set()
        for repo in parent_pom.get("plugin_repositories", []) + child_pom.get(
            "plugin_repositories", []
        ):
            if repo.get("id") not in plugin_repo_ids:
                merged["plugin_repositories"].append(repo)
                plugin_repo_ids.add(repo.get("id"))

        merged["plugin_management"] = {
            **parent_pom.get("plugin_management", {}),
            **child_pom.get("plugin_management", {}),
        }

        parent_plugins = {
            f"{p['group_id']}:{p['artifact_id']}": p
            for p in parent_pom.get("plugins", [])
        }
        child_plugins = {
            f"{p['group_id']}:{p['artifact_id']}": p
            for p in child_pom.get("plugins", [])
        }

        for key, plugin in parent_plugins.items():
            merged["plugins"].append(plugin)

        for key, plugin in child_plugins.items():
            if key not in parent_plugins:
                merged["plugins"].append(plugin)
            else:
                for i, merged_plugin in enumerate(merged["plugins"]):
                    if (
                        f"{merged_plugin['group_id']}:{merged_plugin['artifact_id']}"
                        == key
                    ):
                        merged["plugins"][i] = plugin
                        break

        merged["profiles"] = {
            **parent_pom.get("profiles", {}),
            **child_pom.get("profiles", {}),
        }
        merged["modules"] = child_pom.get("modules", [])

        for key in child_pom:
            if key not in merged:
                merged[key] = child_pom[key]

        return merged

    def _parse_pom_comprehensive(
        self,
        pom_xml: str,
        group_id: str,
        artifact_id: str,
        version: str,
        active_profiles: Optional[List[str]] = None,
    ) -> Dict:
        try:
            root = ET.fromstring(pom_xml)
            namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}

            pom_data = {
                "properties": {},
                "dependency_management": {},
                "dependencies": [],
                "repositories": [],
                "plugin_repositories": [],
                "plugins": [],
                "plugin_management": {},
                "profiles": {},
                "parent": None,
                "modules": [],
            }

            pom_data["properties"] = self._extract_properties(root, namespaces)

            pom_data["properties"].update(
                {
                    "project.groupId": group_id,
                    "project.artifactId": artifact_id,
                    "project.version": version,
                    "project.packaging": self._get_element_text(
                        root, "packaging", namespaces
                    )
                    or "jar",
                    "pom.groupId": group_id,
                    "pom.artifactId": artifact_id,
                    "pom.version": version,
                }
            )

            parent_elem = root.find(".//maven:parent", namespaces) or root.find(
                ".//parent"
            )
            if parent_elem is not None:
                pom_data["parent"] = self._extract_parent_info(parent_elem, namespaces)

            pom_data["repositories"] = self._parse_repositories(
                root, namespaces, pom_data["properties"]
            )
            pom_data["plugin_repositories"] = self._parse_plugin_repositories(
                root, namespaces, pom_data["properties"]
            )

            dep_mgmt_elem = root.find(
                ".//maven:dependencyManagement", namespaces
            ) or root.find(".//dependencyManagement")
            if dep_mgmt_elem is not None:
                pom_data["dependency_management"] = self._parse_dependency_management(
                    dep_mgmt_elem, namespaces, pom_data["properties"]
                )

            plugin_mgmt_elem = root.find(
                ".//maven:build/maven:pluginManagement", namespaces
            ) or root.find(".//build/pluginManagement")
            if plugin_mgmt_elem is not None:
                pom_data["plugin_management"] = self._parse_plugin_management(
                    plugin_mgmt_elem, namespaces, pom_data["properties"]
                )

            profiles_elem = root.find(".//maven:profiles", namespaces) or root.find(
                ".//profiles"
            )
            if profiles_elem is not None:
                pom_data["profiles"] = self._parse_profiles(
                    profiles_elem, namespaces, pom_data["properties"]
                )

            deps_elem = root.find(".//maven:dependencies", namespaces) or root.find(
                ".//dependencies"
            )
            if deps_elem is not None:
                main_deps = self._parse_dependencies_section(
                    deps_elem,
                    namespaces,
                    pom_data["properties"],
                    pom_data["dependency_management"],
                )
                pom_data["dependencies"].extend(main_deps)

            plugins_elem = root.find(
                ".//maven:build/maven:plugins", namespaces
            ) or root.find(".//build/plugins")
            if plugins_elem is not None:
                pom_data["plugins"] = self._parse_plugins_section(
                    plugins_elem,
                    namespaces,
                    pom_data["properties"],
                    pom_data["plugin_management"],
                )

            modules = root.findall(".//maven:module", namespaces) or root.findall(
                ".//module"
            )
            pom_data["modules"] = [
                self._substitute_properties(m.text.strip(), pom_data["properties"])
                for m in modules
                if m.text
            ]

            if active_profiles:
                pom_data = self._apply_profiles(pom_data, active_profiles)

            pom_data = self._apply_default_profiles(pom_data, active_profiles)

            return pom_data

        except ET.ParseError as e:
            print(f"XML Parse error: {str(e)}")
            return {"dependencies": []}

    def _extract_properties(self, root, namespaces) -> Dict[str, str]:
        properties = {}
        props_elem = root.find(".//maven:properties", namespaces) or root.find(
            ".//properties"
        )

        if props_elem is not None:
            for prop in props_elem:
                tag = prop.tag.split("}")[-1] if "}" in prop.tag else prop.tag
                if prop.text:
                    properties[tag] = prop.text.strip()

        return properties

    def _substitute_properties(self, value: str, properties: Dict[str, str]) -> str:
        if not value or "${" not in value:
            return value

        pattern = re.compile(r"\$\{([^}]+)\}")

        def replace_property(match):
            prop_name = match.group(1)
            if prop_name in properties:
                return self._substitute_properties(properties[prop_name], properties)
            return match.group(0)

        max_iterations = 10
        for _ in range(max_iterations):
            new_value = pattern.sub(replace_property, value)
            if new_value == value:
                break
            value = new_value

        return value

    def _extract_parent_info(self, parent_elem, namespaces) -> Optional[Dict]:
        try:
            group_id = self._get_element_text(parent_elem, "groupId", namespaces)
            artifact_id = self._get_element_text(parent_elem, "artifactId", namespaces)
            version = self._get_element_text(parent_elem, "version", namespaces)

            if group_id and artifact_id:
                return {
                    "name": f"{group_id}:{artifact_id}",
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "version": version or "unspecified",
                    "scope": "parent",
                    "optional": False,
                    "type": "parent",
                }
        except Exception:
            pass
        return None

    def _parse_repositories(self, root, namespaces, properties) -> List[Dict]:
        repositories = []

        repos_elem = root.find(".//maven:repositories", namespaces) or root.find(
            ".//repositories"
        )
        if repos_elem is not None:
            for repo in repos_elem.findall(
                ".//maven:repository", namespaces
            ) or repos_elem.findall(".//repository"):
                repo_info = {
                    "id": self._substitute_properties(
                        self._get_element_text(repo, "id", namespaces), properties
                    ),
                    "url": self._substitute_properties(
                        self._get_element_text(repo, "url", namespaces), properties
                    ),
                    "layout": self._get_element_text(repo, "layout", namespaces)
                    or "default",
                }

                releases_elem = repo.find(".//maven:releases", namespaces) or repo.find(
                    ".//releases"
                )
                if releases_elem is not None:
                    repo_info["releases"] = {
                        "enabled": self._get_element_text(
                            releases_elem, "enabled", namespaces
                        )
                        != "false",
                        "updatePolicy": self._get_element_text(
                            releases_elem, "updatePolicy", namespaces
                        )
                        or "daily",
                        "checksumPolicy": self._get_element_text(
                            releases_elem, "checksumPolicy", namespaces
                        )
                        or "warn",
                    }

                snapshots_elem = repo.find(
                    ".//maven:snapshots", namespaces
                ) or repo.find(".//snapshots")
                if snapshots_elem is not None:
                    repo_info["snapshots"] = {
                        "enabled": self._get_element_text(
                            snapshots_elem, "enabled", namespaces
                        )
                        == "true",
                        "updatePolicy": self._get_element_text(
                            snapshots_elem, "updatePolicy", namespaces
                        )
                        or "daily",
                        "checksumPolicy": self._get_element_text(
                            snapshots_elem, "checksumPolicy", namespaces
                        )
                        or "warn",
                    }

                repositories.append(repo_info)

        return repositories

    def _parse_plugin_repositories(self, root, namespaces, properties) -> List[Dict]:
        repositories = []

        repos_elem = root.find(".//maven:pluginRepositories", namespaces) or root.find(
            ".//pluginRepositories"
        )
        if repos_elem is not None:
            for repo in repos_elem.findall(
                ".//maven:pluginRepository", namespaces
            ) or repos_elem.findall(".//pluginRepository"):
                repo_info = {
                    "id": self._substitute_properties(
                        self._get_element_text(repo, "id", namespaces), properties
                    ),
                    "url": self._substitute_properties(
                        self._get_element_text(repo, "url", namespaces), properties
                    ),
                    "layout": self._get_element_text(repo, "layout", namespaces)
                    or "default",
                }
                repositories.append(repo_info)

        return repositories

    def _parse_dependency_management(
        self, dep_mgmt_elem, namespaces, properties
    ) -> Dict[str, Dict]:
        dep_management = {}

        deps_elem = dep_mgmt_elem.find(
            ".//maven:dependencies", namespaces
        ) or dep_mgmt_elem.find(".//dependencies")
        if deps_elem is not None:
            for dep in deps_elem.findall(
                ".//maven:dependency", namespaces
            ) or deps_elem.findall(".//dependency"):
                dep_info = self._extract_dependency_info(
                    dep, namespaces, properties, {}
                )
                if dep_info:
                    key = f"{dep_info['group_id']}:{dep_info['artifact_id']}"
                    dep_management[key] = dep_info

        return dep_management

    def _parse_plugin_management(
        self, plugin_mgmt_elem, namespaces, properties
    ) -> Dict[str, Dict]:
        plugin_management = {}

        plugins_elem = plugin_mgmt_elem.find(
            ".//maven:plugins", namespaces
        ) or plugin_mgmt_elem.find(".//plugins")
        if plugins_elem is not None:
            for plugin in plugins_elem.findall(
                ".//maven:plugin", namespaces
            ) or plugins_elem.findall(".//plugin"):
                plugin_info = self._extract_plugin_info(
                    plugin, namespaces, properties, {}
                )
                if plugin_info:
                    key = f"{plugin_info['group_id']}:{plugin_info['artifact_id']}"
                    plugin_management[key] = plugin_info

        return plugin_management

    def _parse_profiles(
        self, profiles_elem, namespaces, parent_properties
    ) -> Dict[str, Dict]:
        profiles = {}

        for profile in profiles_elem.findall(
            ".//maven:profile", namespaces
        ) or profiles_elem.findall(".//profile"):
            profile_id = self._get_element_text(profile, "id", namespaces)
            if not profile_id:
                continue

            profile_data = {
                "id": profile_id,
                "properties": {},
                "dependencies": [],
                "dependency_management": {},
                "activeByDefault": False,
                "activation": {},
            }

            activation_elem = profile.find(
                ".//maven:activation", namespaces
            ) or profile.find(".//activation")
            if activation_elem is not None:
                active_by_default = self._get_element_text(
                    activation_elem, "activeByDefault", namespaces
                )
                profile_data["activeByDefault"] = active_by_default == "true"
                profile_data["activation"] = self._parse_activation(
                    activation_elem, namespaces
                )

            props_elem = profile.find(
                ".//maven:properties", namespaces
            ) or profile.find(".//properties")
            if props_elem is not None:
                profile_props = self._extract_properties(profile, namespaces)
                all_props = {**parent_properties, **profile_props}
                for key, value in profile_props.items():
                    profile_data["properties"][key] = self._substitute_properties(
                        value, all_props
                    )

            deps_elem = profile.find(
                ".//maven:dependencies", namespaces
            ) or profile.find(".//dependencies")
            if deps_elem is not None:
                all_props = {**parent_properties, **profile_data["properties"]}
                profile_data["dependencies"] = self._parse_dependencies_section(
                    deps_elem, namespaces, all_props, {}
                )

            dep_mgmt_elem = profile.find(
                ".//maven:dependencyManagement", namespaces
            ) or profile.find(".//dependencyManagement")
            if dep_mgmt_elem is not None:
                all_props = {**parent_properties, **profile_data["properties"]}
                profile_data[
                    "dependency_management"
                ] = self._parse_dependency_management(
                    dep_mgmt_elem, namespaces, all_props
                )

            profiles[profile_id] = profile_data

        return profiles

    def _parse_activation(self, activation_elem, namespaces) -> Dict:
        activation = {}

        jdk = self._get_element_text(activation_elem, "jdk", namespaces)
        if jdk:
            activation["jdk"] = jdk

        os_elem = activation_elem.find(
            ".//maven:os", namespaces
        ) or activation_elem.find(".//os")
        if os_elem is not None:
            activation["os"] = {
                "name": self._get_element_text(os_elem, "name", namespaces),
                "family": self._get_element_text(os_elem, "family", namespaces),
                "arch": self._get_element_text(os_elem, "arch", namespaces),
                "version": self._get_element_text(os_elem, "version", namespaces),
            }

        prop_elem = activation_elem.find(
            ".//maven:property", namespaces
        ) or activation_elem.find(".//property")
        if prop_elem is not None:
            activation["property"] = {
                "name": self._get_element_text(prop_elem, "name", namespaces),
                "value": self._get_element_text(prop_elem, "value", namespaces),
            }

        return activation

    def _parse_dependencies_section(
        self, deps_elem, namespaces, properties, dep_management
    ) -> List[Dict]:
        dependencies = []

        for dep in deps_elem.findall(
            ".//maven:dependency", namespaces
        ) or deps_elem.findall(".//dependency"):
            dep_info = self._extract_dependency_info_with_exclusions(
                dep, namespaces, properties, dep_management
            )
            if dep_info:
                dependencies.append(dep_info)

        return dependencies

    def _extract_dependency_info(
        self, dep_elem, namespaces, properties, dep_management
    ) -> Optional[Dict]:
        try:
            group_id = self._get_element_text(dep_elem, "groupId", namespaces)
            artifact_id = self._get_element_text(dep_elem, "artifactId", namespaces)
            version = self._get_element_text(dep_elem, "version", namespaces)
            scope = self._get_element_text(dep_elem, "scope", namespaces) or "compile"
            optional = (
                self._get_element_text(dep_elem, "optional", namespaces) == "true"
            )
            dep_type = self._get_element_text(dep_elem, "type", namespaces) or "jar"
            classifier = self._get_element_text(dep_elem, "classifier", namespaces)

            group_id = (
                self._substitute_properties(group_id, properties) if group_id else None
            )
            artifact_id = (
                self._substitute_properties(artifact_id, properties)
                if artifact_id
                else None
            )
            version = (
                self._substitute_properties(version, properties) if version else None
            )

            if group_id and artifact_id:
                group_id, artifact_id = self._normalize_maven_coordinates(
                    group_id, artifact_id
                )

            if group_id and artifact_id:
                dep_key = f"{group_id}:{artifact_id}"
                if dep_key in dep_management and not version:
                    managed_dep = dep_management[dep_key]
                    version = managed_dep.get("version", version)
                    scope = scope or managed_dep.get("scope", "compile")

                version_info = self._parse_version_range(version) if version else None

                return {
                    "name": f"{group_id}:{artifact_id}",
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "version": version or "unspecified",
                    "version_range": version_info,
                    "scope": scope,
                    "optional": optional,
                    "type": "dependency",
                    "classifier": classifier,
                    "packaging": dep_type,
                }
        except Exception as e:
            print(f"Error extracting dependency: {str(e)}")
        return None

    def _extract_dependency_info_with_exclusions(
        self, dep_elem, namespaces, properties, dep_management
    ) -> Optional[Dict]:
        dep_info = self._extract_dependency_info(
            dep_elem, namespaces, properties, dep_management
        )

        if dep_info:
            exclusions = []
            exclusions_elem = dep_elem.find(
                ".//maven:exclusions", namespaces
            ) or dep_elem.find(".//exclusions")

            if exclusions_elem is not None:
                for exclusion in exclusions_elem.findall(
                    ".//maven:exclusion", namespaces
                ) or exclusions_elem.findall(".//exclusion"):
                    exc_group_id = self._get_element_text(
                        exclusion, "groupId", namespaces
                    )
                    exc_artifact_id = self._get_element_text(
                        exclusion, "artifactId", namespaces
                    )

                    if exc_group_id or exc_artifact_id:
                        exclusions.append(
                            {
                                "group_id": self._substitute_properties(
                                    exc_group_id, properties
                                )
                                if exc_group_id
                                else "*",
                                "artifact_id": self._substitute_properties(
                                    exc_artifact_id, properties
                                )
                                if exc_artifact_id
                                else "*",
                            }
                        )

            if exclusions:
                dep_info["exclusions"] = exclusions

        return dep_info

    def _parse_plugins_section(
        self, plugins_elem, namespaces, properties, plugin_management
    ) -> List[Dict]:
        plugins = []

        for plugin in plugins_elem.findall(
            ".//maven:plugin", namespaces
        ) or plugins_elem.findall(".//plugin"):
            plugin_info = self._extract_plugin_info(
                plugin, namespaces, properties, plugin_management
            )
            if plugin_info:
                plugins.append(plugin_info)

        return plugins

    def _extract_plugin_info(
        self, plugin_elem, namespaces, properties, plugin_management
    ) -> Optional[Dict]:
        try:
            group_id = (
                self._get_element_text(plugin_elem, "groupId", namespaces)
                or "org.apache.maven.plugins"
            )
            artifact_id = self._get_element_text(plugin_elem, "artifactId", namespaces)
            version = self._get_element_text(plugin_elem, "version", namespaces)

            group_id = self._substitute_properties(group_id, properties)
            artifact_id = self._substitute_properties(artifact_id, properties)
            version = (
                self._substitute_properties(version, properties) if version else None
            )

            if group_id and artifact_id:
                plugin_key = f"{group_id}:{artifact_id}"
                if plugin_key in plugin_management and not version:
                    managed_plugin = plugin_management[plugin_key]
                    version = managed_plugin.get("version", version)

                plugin_info = {
                    "name": f"{group_id}:{artifact_id}",
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "version": version or "unspecified",
                    "type": "plugin",
                    "dependencies": [],
                }

                deps_elem = plugin_elem.find(
                    ".//maven:dependencies", namespaces
                ) or plugin_elem.find(".//dependencies")
                if deps_elem is not None:
                    plugin_info["dependencies"] = self._parse_dependencies_section(
                        deps_elem, namespaces, properties, {}
                    )

                config_elem = plugin_elem.find(
                    ".//maven:configuration", namespaces
                ) or plugin_elem.find(".//configuration")
                if config_elem is not None:
                    plugin_info["configuration"] = self._parse_configuration(
                        config_elem, properties
                    )

                executions = []
                for exec_elem in plugin_elem.findall(
                    ".//maven:execution", namespaces
                ) or plugin_elem.findall(".//execution"):
                    execution = {
                        "id": self._get_element_text(exec_elem, "id", namespaces)
                        or "default",
                        "phase": self._get_element_text(exec_elem, "phase", namespaces),
                        "goals": [
                            g.text.strip()
                            for g in (
                                exec_elem.findall(".//maven:goal", namespaces)
                                or exec_elem.findall(".//goal")
                            )
                            if g.text
                        ],
                    }
                    executions.append(execution)

                if executions:
                    plugin_info["executions"] = executions

                return plugin_info

        except Exception as e:
            print(f"Error extracting plugin: {str(e)}")
        return None

    def _parse_configuration(self, config_elem, properties) -> Dict:
        config = {}

        for child in config_elem:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if len(child) == 0:
                if child.text:
                    config[tag] = self._substitute_properties(
                        child.text.strip(), properties
                    )
            else:
                config[tag] = self._parse_configuration(child, properties)

        return config

    def _parse_version_range(self, version_str: str) -> Dict[str, Any]:
        if not version_str:
            return {"type": "unspecified"}

        if version_str.startswith("[") or version_str.startswith("("):
            return self._parse_version_range_syntax(version_str)
        else:
            return {"type": "fixed", "version": version_str}

    def _parse_version_range_syntax(self, range_str: str) -> Dict[str, Any]:
        range_info = {
            "type": "range",
            "raw": range_str,
            "min_version": None,
            "max_version": None,
            "min_inclusive": False,
            "max_inclusive": False,
        }

        range_str = range_str.strip()

        if range_str.startswith("["):
            range_info["min_inclusive"] = True
        elif range_str.startswith("("):
            range_info["min_inclusive"] = False

        if range_str.endswith("]"):
            range_info["max_inclusive"] = True
        elif range_str.endswith(")"):
            range_info["max_inclusive"] = False

        inner = range_str[1:-1]
        parts = inner.split(",")

        if len(parts) == 1:
            range_info["min_version"] = parts[0].strip()
            range_info["max_version"] = parts[0].strip()
        elif len(parts) == 2:
            if parts[0].strip():
                range_info["min_version"] = parts[0].strip()
            if parts[1].strip():
                range_info["max_version"] = parts[1].strip()

        return range_info

    async def resolve_version_from_range(
        self, group_id: str, artifact_id: str, version_range: Dict
    ) -> Optional[str]:
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
                    matching_versions, key=lambda x: version.parse(x), reverse=True
                )[0]

        return None

    def _version_matches_range(self, version_str: str, range_info: Dict) -> bool:
        try:
            v = parse_version(version_str)
            if v is None:
                if self._is_maven_version(version_str):
                    if "SNAPSHOT" in version_str:
                        base_version = version_str.replace("-SNAPSHOT", "")
                        v = parse_version(base_version)
                        if v is None:
                            return False
                else:
                    return False

            if range_info["min_version"]:
                min_v = parse_version(range_info["min_version"])
                if min_v is None:
                    return False
                if range_info["min_inclusive"]:
                    if v < min_v:
                        return False
                else:
                    if v <= min_v:
                        return False

            if range_info["max_version"]:
                max_v = parse_version(range_info["max_version"])
                if max_v is None:
                    return False
                if range_info["max_inclusive"]:
                    if v > max_v:
                        return False
                else:
                    if v >= max_v:
                        return False

            return True
        except Exception:
            return False

    def _apply_profiles(self, pom_data: Dict, active_profiles: List[str]) -> Dict:
        for profile_id in active_profiles:
            if profile_id in pom_data.get("profiles", {}):
                profile = pom_data["profiles"][profile_id]

                pom_data["properties"].update(profile.get("properties", {}))

                pom_data["dependencies"].extend(profile.get("dependencies", []))

                if "dependency_management" in profile:
                    pom_data["dependency_management"].update(
                        profile["dependency_management"]
                    )

                pom_data["repositories"].extend(profile.get("repositories", []))

                pom_data["plugins"].extend(profile.get("plugins", []))

                if "plugin_management" in profile:
                    pom_data["plugin_management"].update(profile["plugin_management"])

        return pom_data

    def _apply_default_profiles(
        self, pom_data: Dict, active_profiles: Optional[List[str]]
    ) -> Dict:
        if active_profiles:
            return pom_data

        for profile_id, profile in pom_data.get("profiles", {}).items():
            if profile.get("activeByDefault", False):
                pom_data["properties"].update(profile.get("properties", {}))
                pom_data["dependencies"].extend(profile.get("dependencies", []))
                if "dependency_management" in profile:
                    pom_data["dependency_management"].update(
                        profile["dependency_management"]
                    )
                pom_data["repositories"].extend(profile.get("repositories", []))
                pom_data["plugins"].extend(profile.get("plugins", []))
                if "plugin_management" in profile:
                    pom_data["plugin_management"].update(profile["plugin_management"])

        return pom_data

    def _apply_final_property_substitution(self, pom_data: Dict) -> Dict:
        for dep in pom_data.get("dependencies", []):
            for key in ["group_id", "artifact_id", "version"]:
                if key in dep and dep[key]:
                    dep[key] = self._substitute_properties(
                        dep[key], pom_data["properties"]
                    )

        for plugin in pom_data.get("plugins", []):
            for key in ["group_id", "artifact_id", "version"]:
                if key in plugin and plugin[key]:
                    plugin[key] = self._substitute_properties(
                        plugin[key], pom_data["properties"]
                    )

        return pom_data

    async def get_transitive_dependencies(
        self,
        group_id: str,
        artifact_id: str,
        version: str,
        scope: str = "compile",
        repositories: Optional[List[Dict]] = None,
        visited: Optional[Set[str]] = None,
        exclusions: Optional[List[Dict]] = None,
    ) -> List[Dict]:
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

            if not self._should_include_transitive_dependency(scope, dep_scope):
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

    def _should_include_transitive_dependency(
        self, parent_scope: str, dep_scope: str
    ) -> bool:
        scope_rules = {
            "compile": ["compile", "runtime"],
            "runtime": ["runtime"],
            "test": ["compile", "runtime", "test"],
            "provided": [],
            "system": [],
        }

        allowed_scopes = scope_rules.get(parent_scope, [])
        return dep_scope in allowed_scopes

    async def get_dependency_tree(
        self,
        group_id: str,
        artifact_id: str,
        version: Optional[str] = None,
        max_depth: int = 2,
        visited: Optional[set] = None,
    ) -> Dict:
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

        tree = {
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

    def _get_element_text(self, parent, tag, namespaces) -> Optional[str]:
        elem = parent.find(f".//maven:{tag}", namespaces)
        if elem is not None and elem.text:
            return elem.text.strip()

        elem = parent.find(f".//{tag}")
        if elem is not None and elem.text:
            return elem.text.strip()

        return None
