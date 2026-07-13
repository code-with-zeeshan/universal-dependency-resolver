"""Gradle Plugin Portal client with Maven Central fallback."""

import logging
import xml.etree.ElementTree as ET
from typing import Any

from packaging import version as packaging_version

from ..settings import CACHE_TTL, get_ecosystem_config
from .base_client import BaseDataSourceClient

logger = logging.getLogger(__name__)


class GradleClient(BaseDataSourceClient):
    """Client for Gradle dependencies.

    Tries the Gradle Plugin Portal first for plugin dependencies.
    Falls back to Maven Central (repo1.maven.org) for regular
    Maven dependencies declared in build.gradle files.
    """

    def __init__(
        self,
        cache_ttl: int | None = None,
        max_retries: int | None = None,
    ):
        """Initialize."""
        config = get_ecosystem_config("gradle")
        super().__init__(
            ecosystem="gradle",
            base_url=config.get("url", "https://plugins.gradle.org/api"),
            cache_ttl=cache_ttl or config.get("cache_ttl", CACHE_TTL),
        )
        self.maven_repo_url = "https://repo1.maven.org/maven2"

    async def get_package_info(
        self, package_name: str, include_dependencies: bool = True, include_versions: bool = True
    ) -> dict[str, Any] | None:
        # Split group:artifact and keep dots intact (significant in Maven coordinates)
        """get package info."""
        group, artifact = (
            package_name.split(":", 1) if ":" in package_name else (package_name, package_name)
        )
        # Only lowercase — dots and dashes are semantically distinct in Maven
        group = group.lower()
        artifact = artifact.lower()

        # Try Gradle Plugin Portal first
        try:
            data = await self._get(f"{self.base_url}/g/{group}/a/{artifact}")
            if data:
                versions = data.get("versions", [])
                return {
                    "name": package_name,
                    "version": versions[0] if versions else "unknown",
                    "versions": [{"version": v} for v in versions],
                    "dependencies": {"dependencies": {}},
                    "ecosystem": "gradle",
                }
        except Exception as exc:
            logger.debug("Gradle Plugin Portal lookup failed for %s: %s", package_name, exc)

        # Fall back to Maven Central for non-plugin dependencies
        return await self._fetch_from_maven_central(group, artifact, package_name)

    async def _fetch_from_maven_central(
        self, group: str, artifact: str, full_name: str
    ) -> dict[str, Any] | None:
        group_path = group.replace(".", "/")
        metadata_url = f"{self.maven_repo_url}/{group_path}/{artifact}/maven-metadata.xml"

        try:
            import aiohttp

            session = self._get_session()
            timeout = aiohttp.ClientTimeout(total=15)
            async with session.get(metadata_url, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()
        except Exception as exc:
            logger.debug("Maven Central metadata fetch failed for %s: %s", full_name, exc)
            return None

        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return None

        version_elements = root.findall(".//version")
        versions = [v.text for v in version_elements if v.text]

        if not versions:
            return None

        # Sort using packaging.version for best-effort comparison
        try:
            sorted_versions = sorted(
                set(versions),
                key=lambda v: packaging_version.parse(
                    v.replace("-", ".").replace("_", ".")
                    if packaging_version.parse(v) is not None
                    else v
                ),
                reverse=True,
            )
        except Exception:
            sorted_versions = sorted(set(versions), reverse=True)

        latest = sorted_versions[0]
        return {
            "name": full_name,
            "version": latest,
            "versions": sorted_versions,
            "dependencies": {"dependencies": {}},
            "ecosystem": "gradle",
        }

    async def get_package_versions(
        self, package_name: str, filters: dict | None = None
    ) -> list[dict]:
        """get package versions."""
        info = await self.get_package_info(package_name, include_versions=True)
        raw = info.get("versions", []) if info else []
        return [{"version": v} if isinstance(v, str) else v for v in raw]
