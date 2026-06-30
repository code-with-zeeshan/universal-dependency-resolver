# data_sources/apt_client.py
from typing import Dict, List, Optional, Any
import logging
import re
import gzip
from io import BytesIO
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


class APTClient(BaseDataSourceClient):
    def __init__(self):
        apt_config = get_ecosystem_config("apt")

        super().__init__(
            ecosystem="apt",
            base_url=apt_config.get("repositories", ["http://deb.debian.org/debian"])[
                0
            ],
            cache_ttl=apt_config.get("cache_ttl", CACHE_TTL),
            rate_limit=apt_config.get("rate_limit", 600),
        )

        self.repositories = apt_config.get(
            "repositories",
            [
                "http://deb.debian.org/debian",
                "http://archive.ubuntu.com/ubuntu",
                "http://security.debian.org/debian-security",
            ],
        )

        self.main_repo = self.repositories[0]
        self.distributions = apt_config.get(
            "distributions", ["stable", "testing", "unstable"]
        )
        self.components = apt_config.get("components", ["main", "contrib", "non-free"])
        self._packages_cache: Dict[str, Any] = {}

    def package_exists(self, package_name: str) -> bool:
        package_name = normalize_package_name(package_name)
        try:
            result = run_async(self.get_package_info_async(package_name))
            return result is not None
        except Exception:
            return False

    async def search_packages(self, query: str, limit: int = 20) -> List[Dict]:
        query = normalize_package_name(query)
        results: List[Dict] = []

        try:
            packages = await self._get_packages_list("stable", "main")
        except Exception:
            return results
        if not packages:
            return results

        for pkg_name, pkg_info in packages.items():
            if query in pkg_name or (
                pkg_info.get("description") and query in pkg_info["description"].lower()
            ):
                results.append(
                    {
                        "name": pkg_name,
                        "version": pkg_info.get("version", ""),
                        "description": pkg_info.get("description", ""),
                        "section": pkg_info.get("section", ""),
                        "priority": pkg_info.get("priority", ""),
                    }
                )

                if len(results) >= limit:
                    break

        return results

    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(self, package_name: str) -> Optional[Dict]:
        package_name = normalize_package_name(package_name)

        package_data = None
        versions_list = []

        for dist in self.distributions:
            for component in self.components:
                packages = await self._get_packages_list(dist, component)
                if packages and package_name in packages:
                    pkg_data = packages[package_name]
                    versions_list.append(
                        {
                            "version": pkg_data.get("version", ""),
                            "distribution": dist,
                            "component": component,
                            "architecture": pkg_data.get("architecture", "all"),
                        }
                    )

                    if not package_data:
                        package_data = pkg_data

        if not package_data:
            return None

        dependencies = self._parse_dependencies(package_data)
        system_requirements = self._extract_system_requirements(package_data)

        info = {
            "name": package_name,
            "version": package_data.get("version", ""),
            "versions": versions_list,
            "description": package_data.get("description", ""),
            "homepage": package_data.get("homepage", ""),
            "maintainer": package_data.get("maintainer", ""),
            "section": package_data.get("section", ""),
            "priority": package_data.get("priority", ""),
            "architecture": package_data.get("architecture", "all"),
            "size": package_data.get("size", 0),
            "installed_size": package_data.get("installed-size", 0),
            "dependencies": dependencies,
            "system_requirements": system_requirements,
            "ecosystem": "apt",
        }

        return info

    def get_package_info(self, package_name: str) -> Optional[Dict]:
        package_name = normalize_package_name(package_name)
        return run_async(self.get_package_info_async(package_name))

    async def get_versions(self, package_name: str) -> List[Dict]:
        package_name = normalize_package_name(package_name)
        versions: List[Any] = []
        for dist in self.distributions:
            for component in self.components:
                packages = await self._get_packages_list(dist, component)
                if packages and package_name in packages:
                    pkg_data = packages[package_name]
                    versions.append(
                        {
                            "version": pkg_data.get("version", ""),
                            "distribution": dist,
                            "component": component,
                            "architecture": pkg_data.get("architecture", "all"),
                            "upload_time": None,
                        }
                    )

        versions.sort(
            key=lambda x: parse_version_key(x["version"].split("-")[0]),
            reverse=True,
        )

        return versions

    async def get_dependencies(
        self, package_name: str, version: Optional[str] = None
    ) -> Dict:
        package_name = normalize_package_name(package_name)

        package_data = None
        for dist in self.distributions:
            for component in self.components:
                packages = await self._get_packages_list(dist, component)
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

    async def _get_packages_list(
        self, distribution: str, component: str
    ) -> Dict[str, Dict]:
        cache_key = f"packages:{distribution}:{component}"

        if cache_key in self._packages_cache:
            return self._packages_cache[cache_key]

        url = f"{self.main_repo}/dists/{distribution}/{component}/binary-amd64/Packages.gz"

        try:
            session = self._get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(
                        f"Failed to fetch Packages from {url}: {response.status}"
                    )
                    return {}

                content = await response.read()
                with gzip.GzipFile(fileobj=BytesIO(content)) as gz:
                    packages_content = gz.read().decode("utf-8", errors="ignore")

                packages = self._parse_packages_file(packages_content)
                self._packages_cache[cache_key] = packages

                return packages

        except Exception as e:
            logger.error(f"Error fetching packages list: {e}")
            return {}

    def _parse_packages_file(self, content: str) -> Dict[str, Dict]:
        packages: Dict[str, Any] = {}
        current_package: Dict[str, Any] = {}
        current_field = None

        for line in content.split("\n"):
            if not line.strip():
                if "package" in current_package:
                    pkg_name = current_package["package"]
                    packages[pkg_name] = current_package
                current_package = {}
                current_field = None
                continue

            if line.startswith(" "):
                if current_field:
                    current_package[current_field] += "\n" + line.strip()
            else:
                match = re.match(r"^([^:]+):\s*(.*)$", line)
                if match:
                    field_name = match.group(1).lower()
                    field_value = match.group(2)
                    current_package[field_name] = field_value
                    current_field = field_name

        if "package" in current_package:
            pkg_name = current_package["package"]
            packages[pkg_name] = current_package

        return packages

    def _parse_dependencies(self, package_data: Dict) -> Dict[str, List[Dict]]:
        dependencies: Dict[str, List[Dict]] = {
            "depends": [],
            "recommends": [],
            "suggests": [],
            "enhances": [],
            "conflicts": [],
            "breaks": [],
            "provides": [],
            "replaces": [],
        }

        dep_fields = [
            "depends",
            "recommends",
            "suggests",
            "enhances",
            "conflicts",
            "breaks",
            "provides",
            "replaces",
        ]

        for field in dep_fields:
            if field in package_data:
                deps_str = package_data[field]
                parsed_deps = self._parse_dependency_string(deps_str)
                dependencies[field] = parsed_deps

        return dependencies

    def _parse_dependency_string(self, deps_str: str) -> List[Dict]:
        dependencies: List[Dict] = []
        for dep_group in deps_str.split(","):
            dep_group = dep_group.strip()

            or_deps = []
            for or_dep in dep_group.split("|"):
                or_dep = or_dep.strip()

                match = re.match(r"^([a-z0-9][a-z0-9+.-]+)(?:\s*\(([^)]+)\))?", or_dep)
                if match:
                    dep_name = match.group(1)
                    version_spec = match.group(2) if match.group(2) else ""

                    or_deps.append({"name": dep_name, "version_spec": version_spec})

            if len(or_deps) == 1:
                dependencies.append(or_deps[0])
            elif or_deps:
                dependencies.append({"or_dependencies": or_deps})

        return dependencies

    def _extract_system_requirements(self, package_data: Dict) -> Dict[str, Any]:
        requirements = {
            "architecture": package_data.get("architecture", "all"),
            "essential": package_data.get("essential", "no") == "yes",
            "priority": package_data.get("priority", "optional"),
        }

        if "depends" in package_data:
            deps_str = package_data["depends"].lower()

            libc_match = re.search(r"libc6\s*\(>=\s*([^)]+)\)", deps_str)
            if libc_match:
                requirements["libc_version"] = libc_match.group(1)

            kernel_match = re.search(r"linux-[a-z-]+\s*\(>=\s*([^)]+)\)", deps_str)
            if kernel_match:
                requirements["kernel_version"] = kernel_match.group(1)

        return requirements
