# data_sources/apk_client.py
from typing import Dict, List, Optional, Any
import logging
import re
import tarfile
from io import BytesIO
from backend.core.cache import cached
from backend.core.utils import normalize_package_name, parse_version, run_async
from backend.settings import (
    CACHE_TTL,
    get_ecosystem_config,
)
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class APKClient(BaseDataSourceClient):
    def __init__(self):
        apk_config = get_ecosystem_config("apk")

        super().__init__(
            ecosystem="apk",
            base_url="https://dl-cdn.alpinelinux.org/alpine",
            cache_ttl=apk_config.get("cache_ttl", CACHE_TTL),
            rate_limit=apk_config.get("rate_limit", 600),
        )

        self.repositories = apk_config.get(
            "repositories",
            [
                "https://dl-cdn.alpinelinux.org/alpine/v3.18/main",
                "https://dl-cdn.alpinelinux.org/alpine/v3.18/community",
            ],
        )

        self.branches = apk_config.get("branches", ["v3.18", "v3.17", "edge"])
        self.repos_types = apk_config.get("repos", ["main", "community", "testing"])
        self._index_cache: Dict[str, Any] = {}

    def package_exists(self, package_name: str) -> bool:
        package_name = normalize_package_name(package_name)
        try:
            result = run_async(self.get_package_info_async(package_name))
            return result is not None
        except Exception:
            return False

    async def search_packages(self, query: str, limit: int = 20) -> List[Dict]:
        query = normalize_package_name(query)
        results = []
        seen = set()

        try:
            for branch in self.branches[:1]:
                for repo_type in self.repos_types[:2]:
                    packages = await self._get_apkindex(branch, repo_type)

                    for pkg_name, pkg_info in packages.items():
                        if query in pkg_name or (
                            pkg_info.get("description")
                            and query in pkg_info["description"].lower()
                        ):
                            if pkg_name not in seen:
                                seen.add(pkg_name)
                                results.append(
                                    {
                                        "name": pkg_name,
                                        "version": pkg_info.get("version", ""),
                                        "description": pkg_info.get("description", ""),
                                        "branch": branch,
                                        "repository": repo_type,
                                    }
                                )

                                if len(results) >= limit:
                                    return results
        except Exception:
            pass

        return results

    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(self, package_name: str) -> Optional[Dict]:
        package_name = normalize_package_name(package_name)

        package_data = None
        versions_list = []

        for branch in self.branches:
            for repo_type in self.repos_types:
                packages = await self._get_apkindex(branch, repo_type)

                if packages and package_name in packages:
                    pkg_data = packages[package_name]
                    versions_list.append(
                        {
                            "version": pkg_data.get("version", ""),
                            "branch": branch,
                            "repository": repo_type,
                            "architecture": pkg_data.get("architecture", "x86_64"),
                        }
                    )

                    if not package_data:
                        package_data = pkg_data

        if not package_data:
            return None

        dependencies = self._parse_dependencies(package_data)

        info = {
            "name": package_name,
            "version": package_data.get("version", ""),
            "versions": versions_list,
            "description": package_data.get("description", ""),
            "url": package_data.get("url", ""),
            "license": package_data.get("license", ""),
            "maintainer": package_data.get("maintainer", ""),
            "architecture": package_data.get("architecture", "x86_64"),
            "size": package_data.get("size", 0),
            "installed_size": package_data.get("installed_size", 0),
            "dependencies": dependencies,
            "system_requirements": {
                "alpine": {"min_version": self._extract_alpine_version(versions_list)},
                "architecture": package_data.get("architecture", "x86_64"),
            },
            "ecosystem": "apk",
        }

        return info

    def get_package_info(self, package_name: str) -> Optional[Dict]:
        package_name = normalize_package_name(package_name)
        return run_async(self.get_package_info_async(package_name))

    async def get_versions(self, package_name: str) -> List[Dict]:
        package_name = normalize_package_name(package_name)
        versions = []
        seen_versions = set()

        for branch in self.branches:
            for repo_type in self.repos_types:
                packages = await self._get_apkindex(branch, repo_type)

                if packages and package_name in packages:
                    pkg_data = packages[package_name]
                    version = pkg_data.get("version", "")

                    if version and version not in seen_versions:
                        seen_versions.add(version)
                        versions.append(
                            {
                                "version": version,
                                "branch": branch,
                                "repository": repo_type,
                                "architecture": pkg_data.get("architecture", "x86_64"),
                                "build_time": pkg_data.get("build_time"),
                            }
                        )

        versions.sort(
            key=lambda x: parse_version(x["version"].split("-")[0])
            or parse_version("0.0.0"),
            reverse=True,
        )

        return versions

    async def get_dependencies(
        self, package_name: str, version: Optional[str] = None
    ) -> Dict:
        package_name = normalize_package_name(package_name)

        package_data = None
        for branch in self.branches:
            for repo_type in self.repos_types:
                packages = await self._get_apkindex(branch, repo_type)

                if packages and package_name in packages:
                    pkg_data = packages[package_name]
                    if not version or pkg_data.get("version") == version:
                        package_data = pkg_data
                        break
            if package_data:
                break

        if not package_data:
            return {}

        return self._parse_dependencies(package_data)

    async def _get_apkindex(self, branch: str, repository: str) -> Dict[str, Dict]:
        cache_key = f"apkindex:{branch}:{repository}"

        if cache_key in self._index_cache:
            return self._index_cache[cache_key]

        base_url = f"https://dl-cdn.alpinelinux.org/alpine/{branch}/{repository}"
        index_url = f"{base_url}/x86_64/APKINDEX.tar.gz"

        try:
            session = self._get_session()
            async with session.get(index_url) as response:
                if response.status != 200:
                    logger.error(
                        f"Failed to fetch APKINDEX from {index_url}: {response.status}"
                    )
                    return {}

                content = await response.read()

                with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as tar:
                    for member in tar.getmembers():
                        if member.name == "APKINDEX":
                            f = tar.extractfile(member)
                            if f:
                                apkindex_content = f.read().decode(
                                    "utf-8", errors="ignore"
                                )
                                packages = self._parse_apkindex(apkindex_content)
                                self._index_cache[cache_key] = packages
                                return packages

                return {}

        except Exception as e:
            logger.error(f"Error fetching APKINDEX: {e}")
            return {}

    def _parse_apkindex(self, content: str) -> Dict[str, Dict]:
        packages = {}
        current_package = {}

        for line in content.split("\n"):
            line = line.strip()

            if not line:
                if "P" in current_package:
                    pkg_name = current_package["P"]
                    packages[pkg_name] = self._convert_apkindex_entry(current_package)
                current_package = {}
                continue

            if ":" in line:
                field, value = line.split(":", 1)
                current_package[field] = value

        if "P" in current_package:
            pkg_name = current_package["P"]
            packages[pkg_name] = self._convert_apkindex_entry(current_package)

        return packages

    def _convert_apkindex_entry(self, entry: Dict[str, str]) -> Dict[str, Any]:
        field_map = {
            "P": "name",
            "V": "version",
            "A": "architecture",
            "S": "size",
            "I": "installed_size",
            "T": "description",
            "U": "url",
            "L": "license",
            "m": "maintainer",
            "t": "build_time",
            "D": "depends",
            "p": "provides",
            "r": "replaces",
        }

        converted = {}
        for apk_field, std_field in field_map.items():
            if apk_field in entry:
                value = entry[apk_field]

                if std_field in ["size", "installed_size", "build_time"]:
                    try:
                        value = int(value)
                    except Exception:
                        value = 0

                converted[std_field] = value

        return converted

    def _parse_dependencies(self, package_data: Dict) -> Dict[str, List[Dict]]:
        dependencies = {"depends": [], "provides": [], "replaces": []}

        if "depends" in package_data:
            deps_str = package_data["depends"]
            for dep in deps_str.split():
                dep_info = self._parse_dependency_spec(dep)
                if dep_info:
                    dependencies["depends"].append(dep_info)

        if "provides" in package_data:
            provides_str = package_data["provides"]
            for prov in provides_str.split():
                prov_info = self._parse_dependency_spec(prov)
                if prov_info:
                    dependencies["provides"].append(prov_info)

        if "replaces" in package_data:
            replaces_str = package_data["replaces"]
            for repl in replaces_str.split():
                repl_info = self._parse_dependency_spec(repl)
                if repl_info:
                    dependencies["replaces"].append(repl_info)

        return dependencies

    def _parse_dependency_spec(self, dep_spec: str) -> Optional[Dict[str, str]]:
        if dep_spec.startswith("!"):
            return None

        match = re.match(r"^([a-z0-9][a-z0-9+_.-]*)(?:([><=~]+)(.+))?$", dep_spec)
        if match:
            name = match.group(1)
            operator = match.group(2) or ""
            version = match.group(3) or ""

            return {
                "name": name,
                "version_spec": f"{operator}{version}" if operator else "",
            }

        return None

    def _extract_alpine_version(self, versions_list: List[Dict]) -> Optional[str]:
        min_version = None

        for ver_info in versions_list:
            branch = ver_info.get("branch", "")
            match = re.match(r"v(\d+\.\d+)", branch)
            if match:
                version = match.group(1)
                if not min_version or parse_version(version) < parse_version(
                    min_version
                ):
                    min_version = version

        return min_version
