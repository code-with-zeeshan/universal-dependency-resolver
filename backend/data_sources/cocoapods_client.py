# data_sources/cocoapods_client.py
from typing import Dict, List, Optional, Any
import logging
from urllib.parse import quote
from backend.core.cache import cached
from backend.core.utils import normalize_package_name, parse_version, run_async
from backend.settings import (
    CACHE_TTL,
    get_ecosystem_config,
)
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class CocoaPodsClient(BaseDataSourceClient):
    def __init__(self):
        cocoapods_config = get_ecosystem_config("cocoapods")

        base_url = cocoapods_config.get("url", "https://trunk.cocoapods.org/api/v1")
        super().__init__(
            ecosystem="cocoapods",
            base_url=base_url,
        )

        self.specs_url = cocoapods_config.get("specs_url", "https://cdn.cocoapods.org")

    async def package_exists(self, package_name: str) -> bool:
        package_name = self._normalize_pod_name(package_name)
        try:
            session = self._get_session()
            response = await session.get(
                f"{self.base_url}/pods/{quote(package_name)}",
                headers={"User-Agent": self.user_agent},
            )
            return response.status == 200
        except Exception:
            return False

    async def search_packages(self, query: str, limit: int = 20) -> List[Dict]:
        query = normalize_package_name(query)

        url = f"{self.base_url}/pods"
        params = {"query": query}

        try:
            data = await self._get(url, params=params)
        except Exception:
            return []
        if not data:
            return []

        results = []
        for pod in data[:limit]:
            results.append(
                {
                    "name": pod.get("name", ""),
                    "version": pod.get("version", ""),
                    "summary": pod.get("summary", ""),
                    "platforms": pod.get("platforms", {}),
                    "authors": pod.get("authors", {}),
                }
            )

        return results

    @cached(ttl=CACHE_TTL)
    async def get_package_info_async(self, package_name: str) -> Optional[Dict]:
        package_name = self._normalize_pod_name(package_name)

        url = f"{self.base_url}/pods/{quote(package_name)}"
        data = await self._get(url)

        if not data:
            return None

        versions = data.get("versions", [])
        latest_version = versions[0] if versions else None

        if not latest_version:
            return None

        spec_data = await self._get_podspec(package_name, latest_version)

        dependencies = self._parse_dependencies(spec_data) if spec_data else {}
        system_requirements = (
            self._extract_system_requirements(spec_data) if spec_data else {}
        )

        info = {
            "name": data.get("name", package_name),
            "version": latest_version,
            "versions": self._process_versions(versions),
            "summary": data.get("summary", ""),
            "description": spec_data.get("description", "") if spec_data else "",
            "homepage": spec_data.get("homepage", "") if spec_data else "",
            "source": spec_data.get("source", {}) if spec_data else {},
            "license": spec_data.get("license", "") if spec_data else "",
            "authors": spec_data.get("authors", {}) if spec_data else {},
            "platforms": spec_data.get("platforms", {}) if spec_data else {},
            "dependencies": dependencies,
            "system_requirements": system_requirements,
            "ecosystem": "cocoapods",
        }

        return info

    def get_package_info(self, package_name: str) -> Optional[Dict]:
        package_name = self._normalize_pod_name(package_name)
        return run_async(self.get_package_info_async(package_name))

    async def get_versions(self, package_name: str) -> List[Dict]:
        package_name = self._normalize_pod_name(package_name)

        url = f"{self.base_url}/pods/{quote(package_name)}"
        data = await self._get(url)

        if not data:
            return []

        versions = data.get("versions", [])
        return self._process_versions(versions)

    async def get_dependencies(
        self, package_name: str, version: Optional[str] = None
    ) -> Dict:
        package_name = self._normalize_pod_name(package_name)

        if not version:
            pod_info = await self.get_package_info_async(package_name)
            if not pod_info:
                return {}
            version = pod_info["version"]

        spec_data = await self._get_podspec(package_name, version)
        if not spec_data:
            return {}

        return self._parse_dependencies(spec_data)

    async def _get_podspec(self, pod_name: str, version: str) -> Optional[Dict]:
        name_prefix = pod_name[0].upper()
        spec_url = f"{self.specs_url}/Specs/{name_prefix}/{pod_name}/{version}/{pod_name}.podspec.json"

        spec_data = await self._get(spec_url)

        if not spec_data:
            alt_url = f"{self.base_url}/pods/{quote(pod_name)}/specs/{version}"
            spec_data = await self._get(alt_url)

        return spec_data

    def _process_versions(self, versions: List[str]) -> List[Dict]:
        processed = []

        for ver in versions:
            processed.append(
                {
                    "version": ver,
                    "stable": not any(
                        pre in ver for pre in ["alpha", "beta", "rc", "pre"]
                    ),
                    "upload_time": None,
                }
            )

        processed.sort(
            key=lambda x: parse_version(x["version"]) or parse_version("0.0.0"),  # type: ignore[arg-type,return-value]
            reverse=True,
        )

        return processed

    def _parse_dependencies(self, spec_data: Dict) -> Dict[str, List[Dict]]:
        dependencies: Dict[str, List[Dict]] = {
            "dependencies": [],
            "development_dependencies": [],
        }

        if "dependencies" in spec_data:
            for dep_name, dep_spec in spec_data["dependencies"].items():
                dep_info = {
                    "name": dep_name,
                    "version_spec": self._parse_version_spec(dep_spec),
                }
                dependencies["dependencies"].append(dep_info)

        if "subspecs" in spec_data:
            for subspec in spec_data["subspecs"]:
                if "dependencies" in subspec:
                    for dep_name, dep_spec in subspec["dependencies"].items():
                        dep_info = {
                            "name": dep_name,
                            "version_spec": self._parse_version_spec(dep_spec),
                            "subspec": subspec.get("name", ""),
                        }
                        dependencies["dependencies"].append(dep_info)

        if "test_spec" in spec_data:
            test_spec = spec_data["test_spec"]
            if isinstance(test_spec, dict) and "dependencies" in test_spec:
                for dep_name, dep_spec in test_spec["dependencies"].items():
                    dep_info = {
                        "name": dep_name,
                        "version_spec": self._parse_version_spec(dep_spec),
                    }
                    dependencies["development_dependencies"].append(dep_info)

        return dependencies

    def _parse_version_spec(self, spec: Any) -> str:
        if isinstance(spec, str):
            return spec
        elif isinstance(spec, list):
            return ", ".join(spec)
        elif isinstance(spec, dict):
            return str(spec)
        else:
            return ""

    def _extract_system_requirements(self, spec_data: Dict) -> Dict[str, Any]:
        requirements: Dict[str, Any] = {}
        if "platforms" in spec_data:
            platforms = spec_data["platforms"]
            if isinstance(platforms, dict):
                for platform, min_version in platforms.items():
                    requirements[f"{platform}_deployment_target"] = min_version

        if "swift_version" in spec_data:
            requirements["swift"] = {"version": spec_data["swift_version"]}
        elif "swift_versions" in spec_data:
            requirements["swift"] = {"versions": spec_data["swift_versions"]}

        if "frameworks" in spec_data:
            requirements["frameworks"] = spec_data["frameworks"]

        if "libraries" in spec_data:
            requirements["libraries"] = spec_data["libraries"]

        if "compiler_flags" in spec_data:
            requirements["compiler_flags"] = spec_data["compiler_flags"]

        if "requires_arc" in spec_data:
            requirements["requires_arc"] = spec_data["requires_arc"]

        return requirements

    def _normalize_pod_name(self, name: str) -> str:
        return name.strip()
