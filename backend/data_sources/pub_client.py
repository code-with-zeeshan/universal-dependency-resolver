from typing import Dict, List, Optional, Any
from packaging import version
import logging
from urllib.parse import quote
from ..core.utils import normalize_package_name, parse_version
from ..settings import (
    CACHE_TTL,
    get_ecosystem_config,
)
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class PubClient(BaseDataSourceClient):
    def __init__(
        self,
        cache_ttl: Optional[int] = None,
        max_retries: Optional[int] = None,
        rate_limit_delay: Optional[float] = None,
    ):
        pub_config = get_ecosystem_config("pub")
        super().__init__(
            ecosystem="pub",
            base_url=pub_config.get("url", "https://pub.dev/api"),
            cache_ttl=cache_ttl or pub_config.get("cache_ttl", CACHE_TTL),
        )
        self.download_url = "https://pub.dev/api"

    async def get_package_info(self, package_name: str) -> Dict[str, Any]:
        package_name = normalize_package_name(package_name)
        try:
            data = await self._get(
                f"{self.download_url}/packages/{quote(package_name)}"
            )
            if not data:
                return None  # type: ignore[return-value]

            latest_version = data.get("latest", {}).get("version") or data.get(
                "versions", [{}]
            )[0].get("version")

            versions: List[Any] = []
            deps_map = {}
            for v in data.get("versions", []):
                version_str = v.get("version", "")
                if parse_version(version_str) is None:
                    continue
                pubspec = v.get("pubspec", {})
                pub_deps = pubspec.get("dependencies", {})
                if isinstance(pub_deps, dict):
                    deps_map[version_str] = dict(pub_deps)
                versions.append(
                    {
                        "version": version_str,
                        "published": v.get("published", ""),
                        "pubspec": pubspec,
                    }
                )

            # Build aggregated dependencies (latest version's deps)
            deps: Dict[str, Any] = {"dependencies": {}}
            latest_pubspec = None
            if data.get("latest", {}).get("pubspec"):
                latest_pubspec = data["latest"]["pubspec"]
            elif versions and versions[0].get("pubspec"):
                latest_pubspec = versions[0]["pubspec"]
            if latest_pubspec:
                for dep_name, dep_ver in latest_pubspec.get("dependencies", {}).items():
                    if dep_name == "flutter" or dep_name.startswith("flutter_"):
                        continue
                    dep_str = str(dep_ver) if not isinstance(dep_ver, str) else dep_ver
                    deps["dependencies"][dep_name] = dep_str
                for dep_name, dep_ver in latest_pubspec.get(
                    "dev_dependencies", {}
                ).items():
                    dep_str = str(dep_ver) if not isinstance(dep_ver, str) else dep_ver
                    deps.setdefault("dev_dependencies", {})[dep_name] = dep_str

            return {
                "name": data.get("name"),
                "version": latest_version,
                "description": data.get("description", ""),
                "homepage": data.get("homepage", ""),
                "repository": data.get("repository", ""),
                "documentation": data.get("documentation", ""),
                "latest_version": latest_version,
                "versions": versions,
                "dependencies": deps,
            }
        except Exception as e:
            logger.error(f"Pub.dev error for {package_name}: {e}")
            return None  # type: ignore[return-value]

    async def get_package_versions(
        self, package_name: str, filters: Optional[Dict] = None
    ) -> List[Dict]:
        package_name = normalize_package_name(package_name)
        try:
            data = await self._get(
                f"{self.download_url}/packages/{quote(package_name)}"
            )
            if not data:
                return []

            versions: List[Any] = []
            for v in data.get("versions", []):
                version_str = v.get("version", "")
                if parse_version(version_str) is None:
                    continue
                versions.append(
                    {
                        "version": version_str,
                        "published": v.get("published", ""),
                        "pubspec": v.get("pubspec", {}),
                    }
                )

            return sorted(
                versions,
                key=lambda x: version.parse(x["version"]) or parse_version("0.0.0")  ,  # type: ignore[arg-type,return-value]
                reverse=True,
            )
        except Exception as e:
            logger.error(f"Pub.dev versions error for {package_name}: {e}")
            return []
