# crates_client.py
from typing import List, Optional, Dict, Any, Set
from packaging import version
from datetime import datetime
from fastapi import HTTPException
import re
import asyncio
from urllib.parse import quote
import logging
from enum import Enum
from ..core.utils import normalize_package_name, parse_version
from ..settings import (
    CACHE_TTL,
    CACHE_TTL_SHORT,
    get_ecosystem_config,
)
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class DependencyKind(Enum):
    NORMAL = "normal"
    BUILD = "build"
    DEV = "dev"


class CratesClient(BaseDataSourceClient):
    def __init__(
        self,
        user_agent: Optional[str] = None,
        cache_ttl: int = None,
        max_retries: int = None,
        rate_limit_delay: float = None,
    ):
        crates_config = get_ecosystem_config("crates")

        super().__init__(
            ecosystem="crates",
            base_url=crates_config.get("url", "https://crates.io/api/v1"),
            cache_ttl=cache_ttl or crates_config.get("cache_ttl", CACHE_TTL),
        )

        self.download_url = "https://crates.io/api/v1/crates"
        self.cache_ttl_short = CACHE_TTL_SHORT

    async def search_packages(
        self, query: str, limit: int = 10, page: int = 1, sort: str = "relevance"
    ) -> List[Dict[str, Any]]:
        query = normalize_package_name(query)
        try:
            params = {
                "q": query,
                "per_page": min(limit, 100),
                "page": page,
                "sort": sort,
            }

            data = await self._get(f"{self.base_url}/crates", params=params)
            if not data:
                return []

            results = []
            for crate in data.get("crates", []):
                msrv = self._extract_msrv(crate)

                results.append(
                    {
                        "name": crate["name"],
                        "ecosystem": "crates",
                        "version": crate["max_version"],
                        "description": crate.get("description", "No description"),
                        "downloads": crate.get("downloads", 0),
                        "recent_downloads": crate.get("recent_downloads", 0),
                        "homepage": crate.get("homepage"),
                        "repository": crate.get("repository"),
                        "documentation": crate.get("documentation"),
                        "keywords": crate.get("keywords", []),
                        "categories": crate.get("categories", []),
                        "system_requirements": {
                            "rust_versions": [msrv or "1.60+"],
                            "os": self._extract_supported_os(crate),
                        },
                        "created_at": crate.get("created_at"),
                        "updated_at": crate.get("updated_at"),
                    }
                )

            return results

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Crates search error: {str(e)}"
            )

    async def get_package_info(self, package_name: str) -> Dict[str, Any]:
        package_name = normalize_package_name(package_name)
        try:
            data = await self._get(f"{self.base_url}/crates/{quote(package_name)}")
            if not data:
                raise HTTPException(status_code=404, detail="Crates package not found")

            crate = data["crate"]
            versions_data = data.get("versions", [])

            latest_stable = None
            for v in versions_data:
                if not v.get("yanked", False) and "-" not in v["num"]:
                    latest_stable = v["num"]
                    break

            msrv = self._extract_msrv(crate)

            # Build lightweight version list from the versions payload already returned
            versions = []
            seen = set()
            for v in versions_data:
                ver = v["num"]
                if ver not in seen:
                    seen.add(ver)
                    versions.append(
                        {
                            "version": ver,
                            "release_date": v.get("created_at"),
                            "yanked": v.get("yanked", False),
                        }
                    )

            return {
                "name": crate["name"],
                "ecosystem": "crates",
                "version": latest_stable or crate["max_version"],
                "versions": versions[:200],  # cap at 200 to avoid huge payloads
                "info": {
                    "name": crate["name"],
                    "latest_version": crate["max_version"],
                    "latest_stable_version": latest_stable or crate["max_version"],
                    "description": crate.get("description", "No description"),
                    "homepage": crate.get("homepage"),
                    "repository": crate.get("repository"),
                    "documentation": crate.get("documentation"),
                    "downloads": crate.get("downloads", 0),
                    "recent_downloads": crate.get("recent_downloads", 0),
                    "keywords": crate.get("keywords", []),
                    "categories": crate.get("categories", []),
                    "created_at": crate.get("created_at"),
                    "updated_at": crate.get("updated_at"),
                    "owners": await self._get_crate_owners(package_name),
                    "reverse_dependencies": await self._get_reverse_dependencies(
                        package_name
                    ),
                },
                "system_requirements": {
                    "rust_versions": [msrv or "1.60+"],
                    "os": self._extract_supported_os(crate),
                },
                "compatibility_matrix": {
                    "rust": {"minimum": msrv or "1.60", "recommended": "stable"}
                },
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Crates package info error: {str(e)}"
            )

    async def get_package_versions(
        self, package_name: str, filters: Optional[Dict] = None
    ) -> List[Dict]:
        package_name = normalize_package_name(package_name)
        try:
            data = await self._get(
                f"{self.base_url}/crates/{quote(package_name)}/versions"
            )
            if not data:
                raise HTTPException(
                    status_code=404, detail="Crates package versions not found"
                )

            versions = []
            for version_data in data["versions"]:
                version_str = version_data["num"]

                parsed_version = parse_version(version_str)
                if parsed_version is None:
                    logger.warning(f"Skipping invalid crates version: {version_str}")
                    continue

                if filters:
                    if filters.get("exclude_yanked", True) and version_data.get(
                        "yanked", False
                    ):
                        continue

                    if (
                        filters.get("exclude_prerelease", False)
                        and parsed_version.is_prerelease
                    ):
                        continue

                    if "version_range" in filters:
                        if not self._version_matches_range(
                            version_str, filters["version_range"]
                        ):
                            continue

                    if "min_rust_version" in filters:
                        crate_msrv = await self._get_version_msrv(
                            package_name, version_str
                        )
                        if crate_msrv and not self._rust_version_compatible(
                            filters["min_rust_version"], crate_msrv
                        ):
                            continue

                # Only fetch features/msrv for the first 50 versions when no filters
                features = {}
                rust_version = None
                if not filters or len(versions) < 50:
                    try:
                        features = await self._get_version_features(
                            package_name, version_str
                        )
                    except Exception:
                        features = {}
                    try:
                        rust_version = await self._get_version_msrv(
                            package_name, version_str
                        )
                    except Exception:
                        rust_version = None

                versions.append(
                    {
                        "version": version_str,
                        "release_date": version_data["created_at"],
                        "updated_at": version_data["updated_at"],
                        "yanked": version_data.get("yanked", False),
                        "yanked_reason": version_data.get("yank_message"),
                        "downloads": version_data.get("downloads", 0),
                        "features": features,
                        "license": version_data.get("license"),
                        "rust_version": rust_version,
                        "system_requirements": {
                            "rust_versions": [rust_version or "1.60+"],
                            "os": ["any"],
                        },
                    }
                )

            return sorted(
                versions,
                key=lambda x: version.parse(x["version"]) or parse_version("0.0.0"),
                reverse=True,
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Crates versions error: {str(e)}"
            )

    async def get_dependencies(
        self,
        package_name: str,
        version: Optional[str] = None,
        include_optional: bool = True,
        include_dev: bool = False,
        include_build: bool = False,
    ) -> Dict[str, List[Dict]]:
        package_name = normalize_package_name(package_name)
        try:
            if not version:
                package_info = await self.get_package_info(package_name)
                version = package_info["info"]["latest_version"]

            url = f"{self.base_url}/crates/{quote(package_name)}/{quote(version)}/dependencies"
            data = await self._get(url)

            if not data:
                return {"normal": [], "dev": [], "build": []}

            dependencies = {"normal": [], "dev": [], "build": []}

            for dep in data.get("dependencies", []):
                dep_kind = dep.get("kind", "normal")

                if dep_kind == "dev" and not include_dev:
                    continue
                if dep_kind == "build" and not include_build:
                    continue
                if dep.get("optional", False) and not include_optional:
                    continue

                normalized_dep_name = normalize_package_name(dep["crate_id"])

                dep_info = {
                    "name": normalized_dep_name,
                    "version_requirement": dep["req"],
                    "features": dep.get("features", []),
                    "optional": dep.get("optional", False),
                    "default_features": dep.get("default_features", True),
                    "target": dep.get("target"),
                    "kind": dep_kind,
                    "ecosystem": "crates",
                }

                resolved_version = await self._resolve_version_requirement(
                    normalized_dep_name, dep["req"]
                )
                if resolved_version:
                    dep_info["resolved_version"] = resolved_version

                dependencies[dep_kind].append(dep_info)

            return dependencies

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Crates dependencies error: {str(e)}"
            )

    async def get_dependency_tree(
        self,
        package_name: str,
        version: Optional[str] = None,
        max_depth: int = 3,
        visited: Optional[Set[str]] = None,
    ) -> Dict:
        package_name = normalize_package_name(package_name)
        if visited is None:
            visited = set()

        key = f"{package_name}@{version or 'latest'}"
        if key in visited or max_depth <= 0:
            return {"name": package_name, "version": version, "dependencies": {}}

        visited.add(key)

        if not version:
            package_info = await self.get_package_info(package_name)
            version = package_info["info"]["latest_version"]

        deps = await self.get_dependencies(
            package_name, version, include_dev=False, include_build=False
        )

        tree = {
            "name": package_name,
            "version": version,
            "dependencies": {"normal": [], "build": []},
        }

        for dep_kind in ["normal", "build"]:
            for dep in deps.get(dep_kind, []):
                if dep.get("optional", False):
                    continue

                dep_version = dep.get("resolved_version")
                if dep_version:
                    dep_tree = await self.get_dependency_tree(
                        dep["name"], dep_version, max_depth - 1, visited
                    )
                    tree["dependencies"][dep_kind].append(dep_tree)

        return tree

    async def check_compatibility(
        self, package_name: str, version: str, system_info: Dict
    ) -> Dict:
        package_name = normalize_package_name(package_name)
        try:
            await self._get_version_metadata(package_name, version)
            dependencies = await self.get_dependencies(package_name, version)

            compatibility = {
                "compatible": True,
                "details": {},
                "warnings": [],
                "errors": [],
            }

            msrv = await self._get_version_msrv(package_name, version)
            if msrv and "rust_version" in system_info:
                system_rust = system_info["rust_version"]
                if not self._rust_version_compatible(system_rust, msrv):
                    compatibility["compatible"] = False
                    compatibility["errors"].append(
                        f"Requires Rust {msrv} or newer, but system has {system_rust}"
                    )
                else:
                    compatibility["details"]["rust_version"] = (
                        f"Compatible (requires Rust {msrv}+)"
                    )
            else:
                compatibility["details"]["rust_version"] = "Compatible with Rust 1.60+"

            target_deps = []
            for dep_list in dependencies.values():
                for dep in dep_list:
                    if dep.get("target"):
                        target_deps.append(dep)

            if target_deps and "target_triple" in system_info:
                system_target = system_info["target_triple"]
                for dep in target_deps:
                    if not self._target_matches(system_target, dep["target"]):
                        compatibility["warnings"].append(
                            f"Dependency '{dep['name']}' may not be available for target '{system_target}'"
                        )

            if "enabled_features" in system_info:
                available_features = await self._get_version_features(
                    package_name, version
                )
                for feature in system_info["enabled_features"]:
                    if feature not in available_features:
                        compatibility["errors"].append(
                            f"Feature '{feature}' not available"
                        )
                        compatibility["compatible"] = False

            system_deps = self._extract_system_dependencies(dependencies)
            if system_deps:
                compatibility["details"]["system_dependencies"] = system_deps
                if "installed_libraries" in system_info:
                    for lib in system_deps:
                        if lib not in system_info["installed_libraries"]:
                            compatibility["warnings"].append(
                                f"May require system library '{lib}' to be installed"
                            )

            return compatibility

        except Exception as e:
            logger.error(f"Compatibility check error: {str(e)}")
            return {
                "compatible": True,
                "details": {"error": "Could not verify compatibility"},
                "warnings": [f"Compatibility check failed: {str(e)}"],
            }

    async def _get_crate_owners(self, package_name: str) -> List[Dict[str, str]]:
        package_name = normalize_package_name(package_name)
        try:
            data = await self._get(
                f"{self.base_url}/crates/{quote(package_name)}/owners"
            )
            if not data:
                return []

            return [
                {
                    "id": owner.get("id"),
                    "login": owner.get("login"),
                    "kind": owner.get("kind", "user"),
                }
                for owner in data.get("users", [])
            ]
        except Exception:
            return []

    async def _get_reverse_dependencies(self, package_name: str) -> int:
        package_name = normalize_package_name(package_name)
        try:
            data = await self._get(
                f"{self.base_url}/crates/{quote(package_name)}/reverse_dependencies"
            )
            if not data:
                return 0
            return data.get("meta", {}).get("total", 0)
        except Exception:
            return 0

    async def _get_version_metadata(self, package_name: str, version: str) -> Dict:
        package_name = normalize_package_name(package_name)
        try:
            f"https://crates.io/api/v1/crates/{quote(package_name)}/{quote(version)}/download"
            return {}
        except Exception:
            return {}

    async def _get_version_msrv(self, package_name: str, version: str) -> Optional[str]:
        package_name = normalize_package_name(package_name)
        try:
            versions = await self.get_package_versions(package_name)
            for v in versions:
                if v["version"] == version:
                    release_date = datetime.fromisoformat(
                        v["release_date"].replace("Z", "+00:00")
                    )
                    if release_date.year < 2018:
                        return "1.0"
                    elif release_date.year < 2019:
                        return "1.31"
                    elif release_date.year < 2021:
                        return "1.45"
                    elif release_date.year < 2022:
                        return "1.56"
                    else:
                        return "1.60"
            return None
        except Exception:
            return None

    async def _get_version_features(self, package_name: str, version: str) -> List[str]:
        package_name = normalize_package_name(package_name)
        return ["default"]

    async def _resolve_version_requirement(
        self, package_name: str, requirement: str
    ) -> Optional[str]:
        package_name = normalize_package_name(package_name)
        try:
            versions = await self.get_package_versions(
                package_name, {"exclude_yanked": True}
            )

            for v in versions:
                if self._version_matches_requirement(v["version"], requirement):
                    return v["version"]

            return None
        except Exception:
            return None

    def _version_matches_requirement(self, version: str, requirement: str) -> bool:
        requirement = requirement.strip()

        if requirement == version:
            return True

        if requirement.startswith("^"):
            req_version = requirement[1:]
            return self._caret_matches(version, req_version)

        if requirement.startswith("~"):
            req_version = requirement[1:]
            return self._tilde_matches(version, req_version)

        if requirement == "*":
            return True

        if requirement.startswith((">=", "<=", ">", "<", "=")):
            return self._comparison_matches(version, requirement)

        return self._caret_matches(version, requirement)

    def _caret_matches(self, version: str, requirement: str) -> bool:
        try:
            v = parse_version(version)
            r = parse_version(requirement)

            if v is None or r is None:
                return False

            if r.major > 0:
                return v.major == r.major and v >= r
            elif r.minor > 0:
                return v.major == 0 and v.minor == r.minor and v >= r
            else:
                return v.major == 0 and v.minor == 0 and v.micro == r.micro
        except Exception:
            return False

    def _tilde_matches(self, version: str, requirement: str) -> bool:
        try:
            v = parse_version(version)
            r = parse_version(requirement)

            if v is None or r is None:
                return False

            return v.major == r.major and v.minor == r.minor and v >= r
        except Exception:
            return False

    def _comparison_matches(self, version: str, requirement: str) -> bool:
        match = re.match(r"([><=]+)\s*(.+)", requirement)
        if not match:
            return False

        operator, req_version = match.groups()

        try:
            v = parse_version(version)
            r = parse_version(req_version)

            if v is None or r is None:
                return False

            if operator == ">=":
                return v >= r
            elif operator == "<=":
                return v <= r
            elif operator == ">":
                return v > r
            elif operator == "<":
                return v < r
            elif operator == "=":
                return v == r

        except Exception:
            pass

        return False

    def _version_matches_range(self, version: str, range_spec: str) -> bool:
        for part in range_spec.split(","):
            part = part.strip()
            if part and not self._version_matches_requirement(version, part):
                return False
        return True

    def _rust_version_compatible(
        self, system_version: str, required_version: str
    ) -> bool:
        try:
            sys_parts = system_version.split(".")
            req_parts = required_version.split(".")

            sys_major_minor = float(f"{sys_parts[0]}.{sys_parts[1]}")
            req_major_minor = float(f"{req_parts[0]}.{req_parts[1]}")

            return sys_major_minor >= req_major_minor
        except Exception:
            return True

    def _target_matches(self, system_target: str, requirement: str) -> bool:
        if requirement.startswith("cfg(") and requirement.endswith(")"):
            cfg_expr = requirement[4:-1]

            if "target_os" in cfg_expr:
                if "windows" in cfg_expr and "windows" not in system_target:
                    return False
                if "linux" in cfg_expr and "linux" not in system_target:
                    return False
                if "macos" in cfg_expr and "darwin" not in system_target:
                    return False

            if "target_arch" in cfg_expr:
                if "x86_64" in cfg_expr and "x86_64" not in system_target:
                    return False
                if "aarch64" in cfg_expr and "aarch64" not in system_target:
                    return False

        return True

    def _extract_msrv(self, crate_data: Dict) -> Optional[str]:
        keywords = crate_data.get("keywords", [])
        for keyword in keywords:
            if keyword.startswith("rust-"):
                match = re.match(r"rust-(\d+\.\d+)", keyword)
                if match:
                    return match.group(1)

        description = crate_data.get("description", "")
        msrv_match = re.search(
            r"(?:MSRV|Rust\s+version)[:\s]+(\d+\.\d+(?:\.\d+)?)", description, re.I
        )
        if msrv_match:
            return msrv_match.group(1)

        return None

    def _extract_supported_os(self, crate_data: Dict) -> List[str]:
        supported_os = []

        keywords = crate_data.get("keywords", [])
        os_keywords = ["windows", "linux", "macos", "unix", "wasm"]

        for keyword in keywords:
            for os_kw in os_keywords:
                if os_kw in keyword.lower():
                    supported_os.append(os_kw)

        if not supported_os:
            supported_os = ["any"]

        return list(set(supported_os))

    def _extract_system_dependencies(
        self, dependencies: Dict[str, List[Dict]]
    ) -> List[str]:
        system_deps = []

        sys_crate_mapping = {
            "openssl-sys": "openssl",
            "libsqlite3-sys": "sqlite3",
            "libgit2-sys": "libgit2",
            "curl-sys": "curl",
            "zlib-sys": "zlib",
            "bzip2-sys": "bzip2",
            "lzma-sys": "xz",
            "libssh2-sys": "libssh2",
            "libz-sys": "zlib",
            "freetype-sys": "freetype",
            "alsa-sys": "alsa-lib",
            "x11": "libx11",
            "xcb": "libxcb",
        }

        for dep_list in dependencies.values():
            for dep in dep_list:
                dep_name = dep["name"]
                if dep_name in sys_crate_mapping:
                    system_deps.append(sys_crate_mapping[dep_name])
                elif dep_name.endswith("-sys"):
                    lib_name = dep_name[:-4]
                    system_deps.append(lib_name)

        return list(set(system_deps))


async def example_usage():
    client = CratesClient()

    try:
        await client.search_packages("serde", limit=5, sort="downloads")

        await client.get_package_info("tokio")

        await client.get_package_versions(
            "reqwest",
            filters={
                "exclude_yanked": True,
                "exclude_prerelease": True,
                "version_range": ">=0.11, <0.12",
            },
        )

        await client.get_dependencies(
            "actix-web", version="4.0.0", include_dev=True, include_build=True
        )

        await client.get_dependency_tree("rocket", max_depth=2)

        await client.check_compatibility(
            "diesel",
            "2.0.0",
            {
                "rust_version": "1.65.0",
                "target_triple": "x86_64-unknown-linux-gnu",
                "enabled_features": ["postgres", "chrono"],
                "installed_libraries": ["postgresql", "openssl"],
            },
        )

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(example_usage())
