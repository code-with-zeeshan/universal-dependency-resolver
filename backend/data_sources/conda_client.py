"""Module docstring."""

# conda_client.py
import io
import json
import logging
import re
import tarfile
from datetime import datetime
from typing import Any

import aiohttp
import yaml  # type: ignore[import-untyped]

from ..core.utils import (
    normalize_package_name,
    parse_version,
    parse_version_key,
    run_async,
)
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class CondaClient(BaseDataSourceClient):
    def __init__(self):
        super().__init__(
            ecosystem="conda",
            base_url="https://api.anaconda.org",
        )

        channels = {
            "defaults": "https://repo.anaconda.com/pkgs/main",
            "conda-forge": "https://conda.anaconda.org/conda-forge",
            "pytorch": "https://conda.anaconda.org/pytorch",
            "nvidia": "https://conda.anaconda.org/nvidia",
            "bioconda": "https://conda.anaconda.org/bioconda",
            "r": "https://conda.anaconda.org/r",
        }
        self.channels = channels.copy()
        self.repodata_urls = {
            channel: f"{url}/{{platform}}/repodata.json" for channel, url in channels.items()
        }
        self._repodata_cache = {}
        self._dependency_cache = {}

    async def package_exists(self, package_name: str) -> bool:
        package_name = normalize_package_name(package_name)
        try:
            session = self._get_session()
            response = await session.get(
                f"https://api.anaconda.org/package/conda-forge/{package_name}"
            )
            return response.status == 200
        except Exception:
            return False

    async def get_package_info_async(self, package_name: str) -> dict | None:
        package_name = normalize_package_name(package_name)
        try:
            package_info = None
            for channel_name, channel_url in self.channels.items():
                info = await self._fetch_from_anaconda_api(package_name, channel_name)
                if info:
                    package_info = info
                    package_info["channel_name"] = channel_name
                    break

            if not package_info:
                return None

            processed_info = await self._process_package_data_enhanced(package_info)

            return processed_info

        except Exception as e:
            logger.error(f"Error fetching Conda package {package_name}: {e}")
            return None

    def get_package_info(self, package_name: str) -> dict | None:
        package_name = normalize_package_name(package_name)
        return run_async(self.get_package_info_async(package_name))

    async def _fetch_from_anaconda_api(self, package_name: str, channel: str) -> dict | None:
        package_name = normalize_package_name(package_name)
        try:
            api_url = f"https://api.anaconda.org/package/{channel}/{package_name}"

            session = self._get_session()
            async with session.get(api_url) as response:
                if response.status != 200:
                    return None

                data = await response.json()

                files_url = f"{api_url}/files"
                async with session.get(files_url) as files_response:
                    if files_response.status == 200:
                        files_data = await files_response.json()
                        data["files"] = files_data

                return data

        except Exception as e:
            logger.debug(f"Package {package_name} not found in {channel}: {e}")
            return None

    async def _process_package_data_enhanced(self, data: dict) -> dict:
        latest_version = data.get("latest_version")
        files = data.get("files", [])
        if not latest_version and files:
            # Derive latest from files list
            all_vers = sorted(
                set(f.get("version") for f in files if f.get("version")),
                key=parse_version_key,
                reverse=True,
            )
            latest_version = all_vers[0] if all_vers else None
        channel_name = data.get("channel_name", "conda-forge")

        versions_info = []

        version_map = {}
        for file_info in files:
            version_str = file_info.get("version")
            parsed_version = parse_version(version_str)
            if parsed_version is None:
                logger.warning(f"Skipping invalid conda version: {version_str}")
                continue

            if version_str not in version_map:
                attrs = file_info.get("attrs", {})
                depends = attrs.get("depends", [])
                deps: dict[str, Any] = {}
                for dep_str in depends:
                    dep_name, constraint = self._parse_conda_dependency(dep_str)
                    if dep_name:
                        deps[dep_name] = constraint

                version_map[version_str] = {
                    "version": version_str,
                    "parsed_version": parsed_version,
                    "builds": [],
                    "platforms": set(),
                    "python_versions": set(),
                    "dependencies": deps if deps else None,
                }

            attrs = file_info.get("attrs", {})
            platform = attrs.get("subdir", "noarch")
            version_map[version_str]["platforms"].add(platform)

            if "py" in attrs.get("build", ""):
                py_match = re.search(r"py(\d)(\d+)", attrs.get("build", ""))
                if py_match:
                    py_version = f"{py_match.group(1)}.{py_match.group(2)}"
                    version_map[version_str]["python_versions"].add(py_version)

            version_map[version_str]["builds"].append(
                {
                    "build": attrs.get("build"),
                    "build_number": attrs.get("build_number"),
                    "size": file_info.get("size"),
                    "upload_time": file_info.get("upload_time"),
                    "md5": file_info.get("md5"),
                    "sha256": file_info.get("sha256"),
                    "filename": file_info.get("basename"),
                }
            )

        for version_data in version_map.values():
            version_data["platforms"] = list(version_data["platforms"])
            version_data["python_versions"] = list(version_data["python_versions"])
            version_data.pop("parsed_version", None)
            versions_info.append(version_data)

        versions_info.sort(
            key=lambda x: parse_version_key(x["version"]),
            reverse=True,
        )

        dependencies = self._extract_deps_from_files(files)

        system_requirements = self._extract_system_requirements(data, files)

        return {
            "name": data.get("name"),
            "version": latest_version,
            "versions": versions_info,
            "summary": data.get("summary"),
            "description": data.get("description"),
            "home": data.get("home"),
            "dev_url": data.get("dev_url"),
            "doc_url": data.get("doc_url"),
            "license": data.get("license"),
            "owner": data.get("owner", {}).get("login"),
            "channel": channel_name,
            "dependencies": dependencies,
            "system_requirements": system_requirements,
            "platforms": list(set(f["attrs"].get("subdir", "noarch") for f in files)),
        }

    def _extract_deps_from_files(self, files: list) -> dict:
        deps: dict[str, Any] = {
            "required": {},
            "build": {},
            "run": {},
            "host": {},
            "test": {},
        }
        for file_info in files:
            attrs = file_info.get("attrs", {})
            depends = attrs.get("depends", [])
            for dep_str in depends:
                dep_name, constraint = self._parse_conda_dependency(dep_str)
                if dep_name:
                    deps["run"][dep_name] = constraint
        return deps

    async def _extract_dependencies_from_repodata(
        self, package_name: str, version: str, channel: str
    ) -> dict:
        package_name = normalize_package_name(package_name)
        cache_key = f"{channel}:{package_name}:{version}"

        if cache_key in self._dependency_cache:
            cached_data, timestamp = self._dependency_cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self._cache_ttl:
                return cached_data

        dependencies = await self._extract_dependencies_from_package_metadata(
            package_name, version, channel
        )

        self._dependency_cache[cache_key] = (
            dependencies,
            datetime.now(),
        )
        return dependencies

    async def _fetch_repodata(self, channel: str, platform: str) -> dict | None:
        cache_key = f"{channel}:{platform}"

        if cache_key in self._repodata_cache:
            cached_data, timestamp = self._repodata_cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self._cache_ttl:
                return cached_data

        try:
            if channel in self.repodata_urls:
                url = self.repodata_urls[channel].format(platform=platform)
            else:
                base_url = self.channels.get(channel, f"https://conda.anaconda.org/{channel}")
                url = f"{base_url}/{platform}/repodata.json"

            logger.debug(f"Fetching repodata from: {url}")

            session = self._get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    self._repodata_cache[cache_key] = (data, datetime.now())
                    return data

        except Exception as e:
            logger.warning(f"Failed to fetch repodata from {channel}/{platform}: {e}")

        return None

    async def _extract_dependencies_from_package_metadata(
        self, package_name: str, version: str, channel: str
    ) -> dict:
        dependencies: dict[str, Any] = {
            "required": {},
            "build": {},
            "run": {},
            "host": {},
            "test": {},
        }

        try:
            info = await self._fetch_from_anaconda_api(package_name, channel)
            if not info or "files" not in info:
                return dependencies

            for file_info in info["files"]:
                if file_info.get("version") != version:
                    continue
                attrs = file_info.get("attrs", {})
                depends = attrs.get("depends", [])
                for dep_str in depends:
                    dep_name, constraint = self._parse_conda_dependency(dep_str)
                    if dep_name:
                        dependencies["run"][dep_name] = constraint

                reqs = attrs.get("requirements", {})
                if isinstance(reqs, dict):
                    for req_type, req_list in reqs.items():
                        if req_type in dependencies and isinstance(req_list, list):
                            for dep in req_list:
                                dep_name, constraint = self._parse_conda_dependency(dep)
                                if dep_name:
                                    dependencies[req_type][dep_name] = constraint
        except Exception as e:
            logger.error(f"Error extracting dependencies from package metadata: {e}")

        return dependencies

    async def _download_and_extract_metadata(self, url: str) -> dict | None:
        try:
            headers = {"Range": "bytes=0-1048576"}

            session = self._get_session()
            async with session.get(url, headers=headers) as response:
                if response.status in [200, 206]:
                    content = await response.read()

                    import bz2

                    try:
                        decompressed = bz2.decompress(content)

                        tar_buffer = io.BytesIO(decompressed)
                        with tarfile.open(fileobj=tar_buffer, mode="r") as tar:
                            try:
                                member = tar.getmember("info/index.json")
                                f = tar.extractfile(member)
                                if f:
                                    metadata = json.loads(f.read().decode("utf-8"))
                                    return metadata
                            except KeyError:
                                try:
                                    member = tar.getmember("info/recipe/meta.yaml")
                                    f = tar.extractfile(member)
                                    if f:
                                        metadata = yaml.safe_load(f.read().decode("utf-8"))
                                        return self._parse_recipe_metadata(metadata)
                                except KeyError:
                                    pass
                    except Exception as e:
                        logger.debug(f"Failed to extract metadata from package: {e}")

        except Exception as e:
            logger.error(f"Error downloading package metadata: {e}")

        return None

    def _parse_recipe_metadata(self, recipe: dict) -> dict:
        metadata = {}

        requirements = recipe.get("requirements", {})
        depends = []

        if isinstance(requirements, dict):
            for req_type in ["build", "host", "run"]:
                if req_type in requirements:
                    req_list = requirements[req_type]
                    if isinstance(req_list, list):
                        depends.extend(req_list)
        elif isinstance(requirements, list):
            depends = requirements

        if depends:
            metadata["depends"] = depends

        about = recipe.get("about", {})
        metadata["name"] = recipe.get("package", {}).get("name", "")
        metadata["version"] = recipe.get("package", {}).get("version", "")
        metadata["home"] = about.get("home", "")
        metadata["license"] = about.get("license", "")
        metadata["summary"] = about.get("summary", "")

        return metadata

    def _parse_conda_dependency(self, dep_string: str) -> tuple[str | None, str]:
        if not dep_string or not isinstance(dep_string, str):
            return None, ""

        dep_string = dep_string.strip()

        match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*([><=!]+)\s*(.+)$", dep_string)
        if match:
            return match.group(1), f"{match.group(2)}{match.group(3)}"

        match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s+([0-9].*)$", dep_string)
        if match:
            version_part = match.group(2)
            if "*" in version_part:
                base_version = version_part.replace(".*", "")
                parsed_base = parse_version(base_version)
                if parsed_base:
                    try:
                        next_major = f"{parsed_base.major}.{parsed_base.minor + 1}"
                        return match.group(1), f">={base_version},<{next_major}"
                    except Exception:
                        return match.group(1), f"=={version_part}"
                else:
                    return match.group(1), f"=={version_part}"
            else:
                return match.group(1), f"=={version_part}"

        match = re.match(r"^([a-zA-Z0-9_\-\.]+)$", dep_string)
        if match:
            return match.group(1), "*"

        return dep_string, "*"

    def _extract_system_requirements(self, data: dict, files: list[dict]) -> dict:
        requirements: dict[str, Any] = {}
        package_name = data.get("name", "").lower()
        package_name = data.get("name", "").lower()
        description = (data.get("description", "") + " " + data.get("summary", "")).lower()

        cuda_indicators = [
            "cudatoolkit",
            "cudnn",
            "cuda-toolkit",
            "pytorch-cuda",
            "tensorflow-gpu",
            "jaxlib-cuda",
            "cupy-cuda",
        ]

        cuda_detected = False
        cuda_versions = set()

        for indicator in cuda_indicators:
            if indicator in package_name:
                cuda_detected = True
                cuda_match = re.search(r"cuda(\d+)", package_name)
                if cuda_match:
                    cuda_ver = cuda_match.group(1)
                    if len(cuda_ver) == 3:
                        cuda_versions.add(f"{cuda_ver[:2]}.{cuda_ver[2]}")
                    elif len(cuda_ver) == 2:
                        cuda_versions.add(f"{cuda_ver}.x")
                break

        for file_info in files:
            build = file_info.get("attrs", {}).get("build", "")
            if "cuda" in build:
                cuda_detected = True
                cuda_match = re.search(r"cuda(\d+)_", build)
                if not cuda_match:
                    cuda_match = re.search(r"cu(\d+)", build)

                if cuda_match:
                    cuda_ver = cuda_match.group(1)
                    if len(cuda_ver) == 3:
                        cuda_versions.add(f"{cuda_ver[:2]}.{cuda_ver[2]}")
                    elif len(cuda_ver) == 2:
                        cuda_versions.add(f"{cuda_ver}.x")

        if cuda_detected:
            requirements["gpu"] = {
                "required": True,
                "cuda": True,
                "description": "NVIDIA GPU with CUDA support required",
            }

            if cuda_versions:
                sorted_versions = sorted(cuda_versions)
                requirements["gpu"]["cuda_version"] = sorted_versions[0]
                requirements["gpu"]["cuda_versions_supported"] = list(sorted_versions)

        platforms = list(set(f.get("attrs", {}).get("subdir", "noarch") for f in files))
        if platforms and "noarch" not in platforms:
            requirements["platform"] = {"supported": platforms}

        python_versions = set()
        for file_info in files:
            attrs = file_info.get("attrs", {})
            build = attrs.get("build", "")

            py_match = re.search(r"py(\d)(\d+)", build)
            if py_match:
                python_versions.add(f"{py_match.group(1)}.{py_match.group(2)}")

            depends = attrs.get("depends", [])
            if isinstance(depends, list):
                for dep in depends:
                    if dep.startswith("python "):
                        py_constraint = dep.replace("python ", "").strip()
                        version_match = re.search(r"(\d+\.\d+)", py_constraint)
                        if version_match:
                            python_versions.add(version_match.group(1))

        if python_versions:
            requirements["python"] = {"supported_versions": sorted(list(python_versions))}

        if "mkl" in package_name or any(
            "mkl" in f.get("attrs", {}).get("build", "") for f in files
        ):
            requirements["mkl"] = {
                "required": True,
                "description": "Intel Math Kernel Library required",
            }

        if "openmp" in description or "libgomp" in description:
            requirements["openmp"] = {
                "required": True,
                "description": "OpenMP support required",
            }

        return requirements

    async def search(self, query: str, limit: int = 20) -> list[dict]:
        query = normalize_package_name(query)

        try:
            search_url = "https://api.anaconda.org/search"
            params = {"q": query, "type": "conda", "limit": limit}

            session = self._get_session()
            async with session.get(search_url, params=params) as response:  # type: ignore[arg-type]
                if response.status != 200:
                    return []

                data = await response.json()

                results = []
                for item in data:
                    results.append(
                        {
                            "name": item.get("name"),
                            "channel": item.get("channel_name"),
                            "version": item.get("latest_version"),
                            "description": item.get("summary"),
                            "platforms": item.get("platforms", []),
                            "owner": item.get("owner", {}).get("login"),
                        }
                    )

                return results

        except Exception as e:
            logger.error(f"Error searching Conda: {e}")
            return []

    async def get_versions(self, package_name: str) -> list[dict]:
        package_name = normalize_package_name(package_name)
        info = await self.get_package_info_async(package_name)
        if not info:
            return []

        return info.get("versions", [])

    async def get_dependencies(self, package_name: str, version: str | None = None) -> dict:
        package_name = normalize_package_name(package_name)
        if not version:
            info = await self.get_package_info_async(package_name)
            if not info:
                return {}
            version = info.get("version")

        cache_key = f"deps:{package_name}:{version}"
        if cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            if (datetime.now() - timestamp).total_seconds() < self._cache_ttl:
                return cached_data

        info = await self.get_package_info_async(package_name)
        if not info:
            return {}

        channel = info.get("channel", "conda-forge")

        dependencies = await self._extract_dependencies_from_repodata(
            package_name,
            version,  # type: ignore[arg-type]
            channel,
        )

        self._cache[cache_key] = (dependencies, datetime.now())

        return dependencies
